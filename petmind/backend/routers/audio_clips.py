"""Local single-household prototype: explicit retention and separate training opt-in.

pet_id scopes records, not authentication. Do not expose this API to the Internet.
"""
import hashlib
import html
import io
import json
import math
import pickle
import uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from urllib.parse import quote

import numpy as np
import soundfile as sf
import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from ..database import AudioClipLog, get_db, utcnow
from ..schemas import ObservationIn, StrictModel
from ..services.observations import save
from ..settings import ROOT, audio_lstm_checkpoint_path, settings

router = APIRouter(prefix='/audio-clips', tags=['user audio'])
FOLDER = settings.audio_storage_dir
MAX_BYTES = 12 * 1024 * 1024


def path_for(row):
    path = (FOLDER/row.filename).resolve()
    if not path.is_relative_to(FOLDER.resolve()):
        raise HTTPException(409, '음원 저장 경로가 올바르지 않습니다.')
    return path


def purge_expired(db):
    from ..services.event_video import delete_for_audio
    for row in db.scalars(select(AudioClipLog).where(AudioClipLog.deleted_at.is_(None), AudioClipLog.expires_at <= utcnow())):
        path_for(row).unlink(missing_ok=True)
        delete_for_audio(db, row.id)
        row.deleted_at = utcnow()
        row.training_consent = 0
        row.verified_at = None
    db.commit()


def require_clip(db, clip_id, pet_id):
    purge_expired(db)
    row = db.get(AudioClipLog, clip_id)
    if row is None or row.pet_id != pet_id:
        raise HTTPException(404, '음원 기록을 찾을 수 없습니다.')
    return row


def to_out(row):
    review = json.loads(row.review_json)
    analysis = json.loads(row.analysis_json)
    capture_kind = analysis.get('capture', {}).get('kind')
    score = analysis.get('dog_score')
    threshold = (analysis.get('audio_model') or analysis.get('audio_lstm') or {}).get('threshold', .5)
    reason = 'uncertain' if score is None or abs(score-threshold) <= .1 else 'routine_sample'
    original_available = (row.deleted_at is None and row.expires_at > utcnow()
                          and path_for(row).is_file())
    return {'id': row.id, 'pet_id': row.pet_id, 'observation_id': row.observation_id,
            'duration_s': row.duration_s, 'training_consent': bool(row.training_consent),
            'expires_at': row.expires_at.isoformat()+'Z', 'deleted': row.deleted_at is not None,
            'analysis': analysis, 'review': review, 'verified': row.verified_at is not None,
            'review_priority': reason, 'audio_available': original_available,
            'source_note': (('공개·생성 자료 시연: ' if analysis['demo_source'].startswith('AI TTS') else '공개 자료 시연: ')+analysis['demo_source'] if analysis.get('demo_source') else
                            '장치 수집 음원' if capture_kind == 'device' else
                            '원본 파일 재생 음원' if capture_kind == 'file_replay' else
                            '사용자 업로드 음원')+'; 소리 발생 위치·감정은 자동 확정하지 않습니다.'}


def predict_yamnet(content: bytes, duration_s: float) -> dict:
    """Convert the local Bark-only service into the existing audio evidence contract."""
    response = requests.post(settings.yamnet_url, data=content,
                             headers={'Content-Type': 'audio/wav'}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get('model') != 'YAMNet Bark (direct score; no LSTM)' or payload.get('threshold') != .05:
        raise ValueError('unexpected YAMNet model or threshold')
    raw_windows = payload.get('windows')
    if not isinstance(raw_windows, list) or len(raw_windows) != math.ceil(duration_s/5):
        raise ValueError('YAMNet returned the wrong number of windows')
    windows = []
    for index, row in enumerate(raw_windows):
        start, end, score = row['start_s'], row['end_s'], row['bark_score']
        if (not all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end, score))
                or abs(start-index*5) > .01 or abs(end-min((index+1)*5, duration_s)) > .02
                or not 0 <= score <= 1):
            raise ValueError('YAMNet returned an invalid window')
        windows.append({'start_s': start, 'end_s': end, 'dog_score': score,
                        'label': 'dog_candidate' if score >= .05 else 'other_candidate',
                        'padded': bool(row.get('padded', False))})
    return {'model_name': 'YAMNet Bark', 'model_role': 'experimental',
            'windows': windows, 'dog_score': max(row['dog_score'] for row in windows),
            'threshold': .05,
            'scope': 'direct YAMNet Bark score; not calibrated probability or dog identity'}


def store_clip(db, content, pet_id, training_consent, retention_days, outing_id, demo_source=None,
               captured_at=None, capture_kind=None, capture_session=None):
    try:
        info = sf.info(io.BytesIO(content))
        if info.format != 'WAV' or info.duration <= 0 or info.duration > 30 or info.channels > 2:
            raise ValueError('expected mono/stereo WAV up to 30 seconds')
        values, _ = sf.read(io.BytesIO(content), dtype='float32')
        if not np.isfinite(values).all() or np.abs(values).max() > 1:
            raise ValueError('invalid samples')
    except Exception as exc:
        raise HTTPException(422, '30초 이하의 정상적인 모노/스테레오 WAV 파일이 필요합니다.') from exc
    if (captured_at is None) != (capture_kind is None) or (capture_kind and not capture_session):
        raise HTTPException(422, '수집 시각·종류·세션 ID가 함께 필요합니다.')
    observed_at = utcnow()
    if captured_at is not None:
        if captured_at.tzinfo is None:
            raise HTTPException(422, '수집 시작 시각에 시간대가 필요합니다.')
        captured_at = captured_at.astimezone(timezone.utc)
        observed_at = (captured_at+timedelta(seconds=info.duration)).replace(tzinfo=None)
        if observed_at > utcnow() or (capture_kind == 'device' and demo_source):
            raise HTTPException(422, '미래 수집 시각 또는 장치·시연 출처 혼합은 허용하지 않습니다.')
    FOLDER.mkdir(parents=True, exist_ok=True)
    clip_id = uuid.uuid4().hex
    path = FOLDER/(clip_id+'.wav')
    path.write_bytes(content)
    try:
        from pet_monitor.audio import analyze_wav
        analysis = analyze_wav(path)
        # Candidate score integration is separate from energy-event counts.
        analysis['input_scope'] = 'public_demo' if demo_source else 'user_upload'
        if demo_source:
            analysis['demo_source'] = demo_source
        if settings.audio_detector == 'yamnet':
            try:
                experiment = predict_yamnet(content, info.duration)
                analysis['audio_model'] = experiment
            except (ValueError, RuntimeError, KeyError, TypeError, requests.RequestException):
                analysis['model_status'] = 'yamnet_model_failed'
        elif settings.audio_detector == 'lstm':
            checkpoint = audio_lstm_checkpoint_path(ROOT)
            if checkpoint.exists():
                from pet_monitor.audio_model_cache import get_audio_predictor
                try:
                    experiment = get_audio_predictor(checkpoint).predict(path)
                    experiment['model_name'] = 'LSTM'
                    experiment['model_role'] = 'default' if checkpoint.name == 'esc50_lstm.pt' else 'experimental'
                    experiment['checkpoint_name'] = checkpoint.name
                    analysis['audio_lstm'] = experiment
                except (ValueError, RuntimeError, OSError, KeyError, EOFError, pickle.UnpicklingError):
                    analysis['model_status'] = 'experimental_model_failed'
            else:
                analysis['model_status'] = 'experimental_model_not_prepared'
        else:
            raise ValueError('PETMIND_AUDIO_DETECTOR must be lstm or yamnet')
        if experiment := analysis.get('audio_model') or analysis.get('audio_lstm'):
            analysis['dog_score'] = experiment['dog_score']
            analysis['model_disagreement'] = ((experiment['dog_score'] >= experiment['threshold']) !=
                                              (analysis['context']['bark']['count'] > 0))
        if captured_at is not None:
            from pet_monitor.event_video import candidate_windows
            analysis['capture'] = {'started_at': captured_at.isoformat(), 'kind': capture_kind,
                                   'session_id': capture_session}
            analysis['event_video'] = {'status': 'pending' if candidate_windows(analysis) else
                                      'model_unavailable' if analysis.get('model_status') else 'not_triggered'}
        context = analysis['context']
        context['input_note'] = ('공개 자료 시연' if demo_source else '사용자 업로드 음원') + '; 소리 크기 변화는 짖음 판별이 아님; 음성 모델 후보와 원본 확인 필요'
        if capture_kind:
            context['input_note'] = ('장치 동시 수집' if capture_kind == 'device' else '원본 파일 재생 입력') + '; 음성 모델 후보와 보호자 의견으로 확인; 영상 자동 행동 분석 없음'
        observation = save(db, ObservationIn(pet_id=pet_id, session_id='audio-'+clip_id,
            observed_at=observed_at.isoformat()+'Z', source='live' if capture_kind == 'device' else 'user_audio', context=context, outing_id=outing_id), commit=False)
        row = AudioClipLog(id=clip_id, pet_id=pet_id, observation_id=observation.id, filename=path.name,
            sha256=hashlib.sha256(content).hexdigest(), duration_s=info.duration,
            training_consent=int(training_consent), expires_at=utcnow()+timedelta(days=retention_days),
            analysis_json=json.dumps(analysis,ensure_ascii=False))
        db.add(row); db.commit(); db.refresh(row)
        return to_out(row)
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise


@router.post('/upload', status_code=201)
async def upload(request: Request, pet_id: str = Query(min_length=1,max_length=80),
                 store_consent: bool = False, training_consent: bool = False,
                 retention_days: int = Query(default=7,ge=1,le=30), outing_id: str | None = None,
                 demo_source: str | None = Query(default=None, min_length=5, max_length=200),
                 captured_at: datetime | None = None,
                 capture_kind: Literal['device', 'file_replay'] | None = None,
                 capture_session: str | None = Query(default=None, min_length=1, max_length=80),
                 db=Depends(get_db)):
    if not store_consent:
        raise HTTPException(422, '개인 기록 저장 동의가 필요합니다. 모델 학습 참여는 별도 선택입니다.')
    if demo_source and training_consent:
        raise HTTPException(422, '공개 시연 음원은 사용자 학습 참여 자료로 등록할 수 없습니다.')
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, '파일은 12MB 이하여야 합니다.')
    purge_expired(db)
    return await run_in_threadpool(store_clip, db, bytes(content), pet_id, training_consent,
                                   retention_days, outing_id, demo_source, captured_at, capture_kind, capture_session)


@router.get('')
def list_clips(pet_id: str, db=Depends(get_db)):
    purge_expired(db)
    rows = db.scalars(select(AudioClipLog).where(AudioClipLog.pet_id == pet_id).order_by(AudioClipLog.created_at.desc()).limit(100)).all()
    return [to_out(row) for row in rows]


@router.get('/review-queue')
def review_queue(pet_id: str, limit: int = Query(default=5, ge=2, le=20), db=Depends(get_db)):
    purge_expired(db)
    rows = db.scalars(select(AudioClipLog).where(AudioClipLog.pet_id == pet_id,
        AudioClipLog.deleted_at.is_(None)).order_by(AudioClipLog.created_at.desc()).limit(1000)).all()
    pending = [to_out(row) for row in rows if not json.loads(row.review_json) and path_for(row).is_file()]
    candidates = [item for item in pending if item['review_priority'] != 'routine_sample']
    routine = [item for item in pending if item['review_priority'] == 'routine_sample']
    # Deterministic exploration includes ordinary clips as well as uncertain model scores.
    routine.sort(key=lambda item: hashlib.sha256(('review-v1:'+item['id']).encode()).hexdigest())
    chosen = candidates[:limit-1] + routine[:1]
    used = {item['id'] for item in chosen}
    chosen += [item for item in candidates+routine if item['id'] not in used][:limit-len(chosen)]
    return {'items':chosen, 'pending_count':len(pending), 'policy':'model uncertainty + one routine slot',
            'scope':'uploaded clips only; missed events outside uploaded audio cannot be evaluated'}


@router.get('/{clip_id}/audio')
def audio(clip_id: str, pet_id: str, db=Depends(get_db)):
    row = require_clip(db,clip_id,pet_id)
    path = path_for(row)
    if row.deleted_at or not path.is_file():
        raise HTTPException(410, '원본이 삭제되었거나 보관 기간이 지났습니다.')
    if hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
        raise HTTPException(409, '원본 파일이 변경되었습니다.')
    return FileResponse(path,media_type='audio/wav',headers={'Cache-Control':'no-store'})


@router.get('/{clip_id}/player', response_class=HTMLResponse)
def player(clip_id: str, pet_id: str, start_s: float | None = Query(default=None, ge=0),
           end_s: float | None = Query(default=None, gt=0), db=Depends(get_db)):
    row = require_clip(db,clip_id,pet_id)
    if row.deleted_at or not path_for(row).is_file():
        raise HTTPException(410, '원본이 삭제되었거나 보관 기간이 지났습니다.')
    if (start_s is None) != (end_s is None) or (start_s is not None and
            (end_s <= start_s or end_s > row.duration_s + .01)):
        raise HTTPException(422, '원본 길이 안의 시작·종료 시각을 함께 지정해 주세요.')
    src = f'/audio-clips/{quote(clip_id,safe="")}/audio?pet_id={quote(pet_id,safe="")}'
    analysis = json.loads(row.analysis_json)
    source_title = ('공개 자료 시연: '+html.escape(analysis['demo_source']) if analysis.get('demo_source')
                    else '사용자 업로드 음원')
    fragment = f'#t={start_s:g},{end_s:g}' if start_s is not None else ''
    segment_note = (f'<p>분석 구간 {start_s:g}~{end_s:g}초 · 5초 분석 창이며 '
                    '정확한 발성 시작·종료 시각은 아닙니다.</p>') if start_s is not None else ''
    stop_script = (f'''<script>const player=document.querySelector('audio');
player.addEventListener('loadedmetadata',()=>{{player.currentTime={start_s:g};}});
player.addEventListener('timeupdate',()=>{{if(player.currentTime>={end_s:g})player.pause();}});
</script>''') if start_s is not None else ''
    return HTMLResponse(f'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PetMind 음원 근거</title><style>
body{{background:#FAFAFA;color:#0A0A0A;font:16px/1.5 sans-serif;margin:0;padding:24px}}
h2{{font-size:24px;margin:0 0 16px}}audio{{width:100%}}p{{color:#6B6B6B}}
</style>
<h2>관찰 #{row.observation_id} · 원본 음원</h2>
<audio controls preload="metadata" src="{html.escape(src+fragment,quote=True)}"></audio>
<p>{source_title} · {row.duration_s:g}초</p>{segment_note}<p>소리의 발생 위치와 감정은 자동 확정하지 않습니다.</p>
{stop_script}
</html>''',headers={'Cache-Control':'no-store'})


class Review(StrictModel):
    pet_id: str
    label: Literal['pet_vocalization', 'external_or_tv', 'other', 'uncertain']
    note: str = Field(default='',max_length=1000)


@router.post('/{clip_id}/review')
def review(clip_id: str, data: Review, db=Depends(get_db)):
    row = require_clip(db,clip_id,data.pet_id)
    is_demo = bool(json.loads(row.analysis_json).get('demo_source'))
    row.review_json = json.dumps({'label':data.label,'note':data.note,
                                  'source':'demo_operator_opinion' if is_demo else 'guardian_opinion',
                                  'updated_at':utcnow().isoformat()+'Z'},ensure_ascii=False)
    row.verified_at = None  # A changed opinion must be independently rechecked before training.
    db.commit()
    return to_out(row)


class Consent(StrictModel):
    pet_id: str
    training_consent: bool


@router.post('/{clip_id}/consent')
def consent(clip_id: str, data: Consent, db=Depends(get_db)):
    row = require_clip(db,clip_id,data.pet_id)
    if row.deleted_at and data.training_consent:
        raise HTTPException(410, '삭제된 원본은 학습에 제공할 수 없습니다.')
    if data.training_consent and json.loads(row.analysis_json).get('demo_source'):
        raise HTTPException(422, '공개 시연 음원은 사용자 학습 참여 자료로 등록할 수 없습니다.')
    row.training_consent = int(data.training_consent)
    row.verified_at = None
    db.commit()
    return to_out(row)


@router.post('/{clip_id}/delete-original')
def delete_original(clip_id: str, pet_id: str, db=Depends(get_db)):
    from ..services.event_video import delete_for_audio
    row = require_clip(db,clip_id,pet_id)
    path_for(row).unlink(missing_ok=True)
    delete_for_audio(db, row.id)
    row.deleted_at = row.deleted_at or utcnow()
    row.training_consent = 0
    row.verified_at = None
    db.commit()
    return to_out(row)
