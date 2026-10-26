"""Sustained-barking alert: dog candidates in nearly every 5-second window for 30 seconds in a row.

Detection is a rule over the model's per-window candidates, not a judgement that the dog is distressed. The alert creates a
pending care suggestion that offers calm music; nothing plays until the guardian approves it (and the device is virtual).
A phone notification goes out through ntfy only when a topic is configured; it carries a short sentence and the app
address, never audio, video or the recording itself.
"""
import json
import logging
import threading
from datetime import timedelta

import requests
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ..database import (CareSuggestionLog, ObservationLog, OutingLog, OutingObservation, SustainedBarkAlert, utcnow)
from ..settings import settings
from .care import current_audio_evidence
from .observations import care_context

log = logging.getLogger('petmind.alerts')

SUSTAINED_SECONDS = 29.5      # six 5-second windows
MIN_CANDIDATE_SHARE = 5 / 6   # one quiet window inside the stretch does not break it
MAX_GAP_SECONDS = 8.0         # a longer hole between recordings means the stretch is not continuous
COOLDOWN = timedelta(minutes=5)
SCAN_LIMIT = 12
DELIVER_IN_BACKGROUND = True
PROVIDER = 'sustained-bark-rule'


def find_sustained(items, need_seconds=SUSTAINED_SECONDS, share=MIN_CANDIDATE_SHARE, max_gap=MAX_GAP_SECONDS):
    """items: newest first, each {'observed_at': datetime, 'window_s': float, 'candidate': bool}.

    Returns {'seconds', 'windows', 'candidate_windows'} when the newest windows, back to `need_seconds`, are continuous,
    the newest one is itself a candidate (the barking is still going on) and enough of them are candidates."""
    picked, seconds = [], 0.0
    for item in items:
        if picked and (picked[-1]['observed_at'] - item['observed_at']).total_seconds() > picked[-1]['window_s'] + max_gap:
            return None
        picked.append(item)
        seconds += item['window_s']
        if seconds >= need_seconds:
            break
    if seconds < need_seconds or not picked[0]['candidate']:
        return None
    candidates = sum(item['candidate'] for item in picked)
    if candidates < len(picked) * share:
        return None
    return {'seconds': seconds, 'windows': len(picked), 'candidate_windows': candidates}


def recent_items(db, outing_id):
    rows = db.execute(select(ObservationLog).join(OutingObservation, OutingObservation.observation_id == ObservationLog.id)
                      .where(OutingObservation.outing_id == outing_id)
                      .order_by(ObservationLog.observed_at.desc()).limit(SCAN_LIMIT)).scalars().all()
    items = []
    for row in rows:
        audio = current_audio_evidence(db, row.id)
        items.append({'id': row.id, 'observed_at': row.observed_at, 'window_s': json.loads(row.context_json).get('window_s') or 0,
                      'candidate': bool(audio and audio['dog_candidate_windows'])})
    return items


def after_device_clip(db, outing_id, pet_id):
    """Called after a clip from the collector was stored. Never raises: an alert problem must not fail the upload."""
    try:
        outing = db.get(OutingLog, outing_id)
        if outing is None or outing.ended_at is not None:
            return None
        recent = db.scalars(select(SustainedBarkAlert).where(SustainedBarkAlert.outing_id == outing_id)
                            .order_by(SustainedBarkAlert.created_at.desc())).first()
        if recent is not None and utcnow() - recent.created_at < COOLDOWN:
            return None
        items = recent_items(db, outing_id)
        found = find_sustained(items)
        if found is None:
            return None
        return raise_alert(db, pet_id, outing_id, items[0]['id'], found)
    except Exception:  # noqa: BLE001 - see docstring
        log.exception('sustained bark check failed')
        db.rollback()
        return None


def raise_alert(db, pet_id, outing_id, observation_id, found):
    observation = db.get(ObservationLog, observation_id)
    seconds = round(found['seconds'])
    summary = (f"개 짖음 소리 후보가 약 {seconds}초 동안 이어지고 있습니다(5초 구간 {found['windows']}개 중 {found['candidate_windows']}개). "
               '원본을 듣고 실제 짖음인지 확인한 뒤, 필요하면 잔잔한 음악을 승인할 수 있습니다. 승인하기 전에는 아무 소리도 재생되지 않습니다.')
    reasons = [f"최근 {found['windows']}개 구간 중 {found['candidate_windows']}개에서 YAMNet Bark 후보가 이어졌습니다.",
               '모델 후보는 실제 짖음의 확정이 아니며 이유나 감정을 판단하지 않습니다.']
    retrieval = {'mode': 'sustained_bark_alert', 'status': 'ok', 'records': [], 'stats': {}, 'care_history': [], 'tool_calls': [],
                 'care_steps': ['원본 소리와 전후 장면을 확인해 주세요.', '반려견 소리로 확인되면 승인 전에 주변 자극(방문·소음)을 기록해 주세요.']}
    suggestion = CareSuggestionLog(observation_id=observation.id, pet_id=pet_id, state='care_option', summary=summary,
                                   reasons_json=json.dumps(reasons, ensure_ascii=False),
                                   recommended_actions_json=json.dumps(['music']), music_style='calm_piano', severity='attention',
                                   status='pending', provider=PROVIDER, context_json=care_context(observation).model_dump_json(),
                                   retrieval_json=json.dumps(retrieval, ensure_ascii=False), cited_ids_json=json.dumps([observation.id]),
                                   question='지속 짖음 알림')
    db.add(suggestion)
    db.flush()
    alert = SustainedBarkAlert(pet_id=pet_id, outing_id=outing_id, suggestion_id=suggestion.id, window_seconds=seconds,
                               candidate_windows=found['candidate_windows'], notify_status='pending' if settings.ntfy_topic else 'not_configured')
    db.add(alert)
    db.commit()
    db.refresh(alert)
    if settings.ntfy_topic:
        message = {'topic': settings.ntfy_topic, 'title': 'PetMind · 짖음 후보가 이어지고 있습니다',
                   'message': f'개 짖음 소리 후보가 약 {seconds}초 이어졌습니다. 앱에서 원본을 확인하고 음악 재생을 승인할 수 있습니다.',
                   'priority': 4, 'tags': ['dog']}
        if settings.public_url:
            message['click'] = settings.public_url
        sessions = sessionmaker(bind=db.get_bind())
        if DELIVER_IN_BACKGROUND:
            threading.Thread(target=deliver, args=(sessions, alert.id, message), daemon=True).start()
        else:
            deliver(sessions, alert.id, message)
    return alert


def http_post(url, **kwargs):
    return requests.post(url, **kwargs)


def deliver(sessions, alert_id, message):
    """Publish through ntfy's JSON endpoint and record the outcome on the alert row."""
    status, detail = 'sent', ''
    try:
        response = http_post(settings.ntfy_server.rstrip('/'), json=message, timeout=(3, 5))
        response.raise_for_status()
    except requests.RequestException as exc:
        status, detail = 'failed', type(exc).__name__
    with sessions() as db:
        alert = db.get(SustainedBarkAlert, alert_id)
        if alert is not None:
            alert.notify_status, alert.notify_detail = status, detail
            db.commit()


def alert_to_out(row):
    return {'id': row.id, 'pet_id': row.pet_id, 'outing_id': row.outing_id, 'suggestion_id': row.suggestion_id,
            'window_seconds': row.window_seconds, 'candidate_windows': row.candidate_windows,
            'notify_status': row.notify_status, 'created_at': row.created_at.isoformat() + 'Z'}
