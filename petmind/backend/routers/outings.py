import html
import json
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from typing import Literal

from ..database import (ObservationLog, ObservationMedia, OutingLog, CaptureJob, get_db, utcnow)
from ..schemas import StrictModel
from ..settings import ROOT
from ..services import outings

router = APIRouter(prefix='/outings', tags=['outings'])
MEDIA_ROOT = ROOT / 'artifacts' / 'media'


class StartRequest(StrictModel):
    pet_id: str = Field(min_length=1, max_length=80)
    title: str = Field(default='외출 관찰', min_length=1, max_length=100)
    input_mode: Literal['synthetic_demo', 'prepared_video', 'live', 'uploaded_audio'] = 'synthetic_demo'
    auto_capture: bool = False
    store_consent: bool = False


class ExplainRequest(StrictModel):
    pet_id: str = Field(min_length=1, max_length=80)
    question: str = Field(default='이번 외출을 요약해 주세요.', min_length=1, max_length=1000)


@router.post('', status_code=201)
def start(data: StartRequest, db=Depends(get_db)):
    if data.auto_capture and (data.input_mode != 'live' or not data.store_consent):
        raise HTTPException(422, '자동 수집은 live 입력과 음성·사건 영상 저장 동의가 필요합니다.')
    row = OutingLog(id=uuid.uuid4().hex,
                    store_consent_at=utcnow() if data.store_consent else None,
                    **data.model_dump(exclude={'auto_capture', 'store_consent'}))
    db.add(row)
    try:
        if data.auto_capture:
            db.flush()
            db.add(CaptureJob(outing_id=row.id, pet_id=row.pet_id))
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '이미 진행 중인 외출이 있습니다. 먼저 종료해 주세요.')
    db.refresh(row)
    return outings.outing_out(row)


@router.get('')
def list_outings(pet_id: str, db=Depends(get_db)):
    rows = db.scalars(select(OutingLog).where(OutingLog.pet_id == pet_id)
                      .order_by(OutingLog.started_at.desc()).limit(100)).all()
    return [outings.outing_out(r) for r in rows]


@router.get('/day')
def daily(pet_id: str, day: date, db=Depends(get_db)):
    start = datetime.combine(day, time(), outings.KST).astimezone(timezone.utc).replace(tzinfo=None)
    end = start + timedelta(days=1)
    rows = db.scalars(select(ObservationLog).where(ObservationLog.pet_id == pet_id,
        ObservationLog.observed_at >= start, ObservationLog.observed_at < end).order_by(ObservationLog.id)).all()
    result = outings.aggregate(db, rows, start.replace(tzinfo=timezone.utc).timestamp(),
                               end.replace(tzinfo=timezone.utc).timestamp())
    return {'day': day.isoformat(), 'timezone': 'Asia/Seoul', 'pet_id': pet_id, **result}


@router.post('/day/explain')
def explain_day(day: date, data: ExplainRequest, db=Depends(get_db)):
    return outings.explain_day(daily(data.pet_id, day, db), data.question)


def require_media(db, observation_id, pet_id):
    observation = db.get(ObservationLog, observation_id)
    if not observation or observation.pet_id != pet_id:
        raise HTTPException(404, '관찰 기록을 찾을 수 없습니다.')
    media = db.get(ObservationMedia, observation_id)
    if not media:
        raise HTTPException(404, '이 관찰에는 연결된 영상이 없습니다.')
    from ..services.event_video import available
    if not available(db, media):
        raise HTTPException(410, '연결된 음원의 삭제·만료로 사건 영상도 사용할 수 없습니다.')
    path = (MEDIA_ROOT / media.filename).resolve()
    if not path.is_relative_to(MEDIA_ROOT.resolve()) or not path.is_file():
        raise HTTPException(404, '원본 영상 파일이 준비되지 않았습니다.')
    # Prevent a replaced file from silently becoming the old observation's evidence.
    import hashlib
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    if digest != media.sha256:
        raise HTTPException(409, '영상이 변경되어 기존 관찰의 근거로 재생할 수 없습니다.')
    return observation, media, path


@router.get('/observations/{observation_id}/evidence')
def observation_evidence(observation_id: int, pet_id: str, db=Depends(get_db)):
    observation = db.get(ObservationLog, observation_id)
    if observation is None or observation.pet_id != pet_id:
        raise HTTPException(404, '관찰 기록을 찾을 수 없습니다.')
    return outings.moment(db, observation)


@router.get('/observations/{observation_id}/video')
def video(observation_id: int, pet_id: str, db=Depends(get_db)):
    _, _, path = require_media(db, observation_id, pet_id)
    return FileResponse(path, media_type='video/mp4', headers={'Cache-Control': 'no-store'})


@router.get('/observations/{observation_id}/clip', response_class=HTMLResponse)
def clip(observation_id: int, pet_id: str, db=Depends(get_db)):
    observation, media, _ = require_media(db, observation_id, pet_id)
    source = json.loads(media.source_json)
    event = source.get('kind') == 'audio_triggered_video'
    playback_kind = '저장된 사건 영상 / 실시간 스트림 아님' if event else '준비된 파일 재생 / 실시간 아님'
    provenance = ('동일 장치 수집' if source.get('capture_kind') == 'device' else '동일 원본 파일 재생 입력') if event else '별도 음원을 결합한 관찰입니다. 짖음 후보의 실제 영상 발생 시각은 아닙니다.'
    if event:
        provenance += (f" · 음성 LSTM 감지 전후 장면 · 앞 {source['missing_pre_s']:g}초 / 뒤 {source['missing_post_s']:g}초 미확보. "
                       '5초 분석 창은 정확한 발성 경계가 아니며 영상 행동을 자동 판정하지 않습니다.')
    src = f'/outings/observations/{observation_id}/video?pet_id={quote(pet_id, safe="")}'
    # End time is enforced after seek/play, including seeking outside the interval.
    return HTMLResponse(f'''<!doctype html><html lang="ko"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>PetMind 관찰 근거</title>
<style>body{{font:16px/1.5 sans-serif;background:#FAFAFA;color:#0A0A0A;margin:24px}}
h1{{font-size:24px}}video{{width:100%;max-height:65vh;background:#0A0A0A}}
button{{font:inherit;color:#fff;background:#6063ED;border:0;border-radius:6px;padding:10px 16px;cursor:pointer}}
button:hover{{background:#4F46E5}}p{{line-height:1.6;color:#6B6B6B}}</style>
<h1>관찰 #{observation.id} · 근거 구간</h1><p>{html.escape(observation.summary)}</p>
<p>영상 {media.start_s:g}~{media.end_s:g}초 · {playback_kind}</p>
<video id="v" controls muted playsinline preload="metadata" src="{html.escape(src, quote=True)}"></video>
<p><button id="replay">이 구간 재생</button></p><p id="status">영상 준비 중</p>
<p>{html.escape(provenance)}</p>
<p>{html.escape(source.get('attribution', ''))}<br>{html.escape(source.get('license', ''))}</p>
<script>const v=document.getElementById('v'),s={media.start_s},e={media.end_s},status=document.getElementById('status');
v.addEventListener('loadedmetadata',()=>{{v.currentTime=s;status.textContent='재생 버튼을 눌러 근거 구간을 확인하세요.';}});
v.addEventListener('error',()=>status.textContent='영상 코덱 또는 파일 오류: 브라우저 재생용 H.264 MP4를 준비해 주세요.');
v.addEventListener('timeupdate',()=>{{if(v.currentTime>=e){{v.pause();status.textContent='근거 구간 재생 완료';}}}});
v.addEventListener('seeking',()=>{{if(v.currentTime<s||v.currentTime>e)v.currentTime=s;}});
document.getElementById('replay').onclick=()=>{{v.currentTime=s;v.play().catch(()=>status.textContent='재생 실패: 파일과 코덱을 확인하세요.');}};
</script></html>''', headers={'Cache-Control': 'no-store'})


@router.get('/{outing_id}')
def get_outing(outing_id: str, pet_id: str, db=Depends(get_db)):
    return outings.outing_out(outings.require_outing(db, outing_id, pet_id))


@router.post('/{outing_id}/end')
def end(outing_id: str, pet_id: str, db=Depends(get_db)):
    row = outings.require_outing(db, outing_id, pet_id)
    job = db.get(CaptureJob, outing_id)
    if job and not row.ended_at:
        from .capture import status
        job.stop_requested = True
        if job.owner and status(job)['state'] not in {'disconnected', 'stopped', 'failed', 'clock_mismatch'}:
            job.state = 'draining'
            db.commit()
            return {**outings.outing_out(row), 'capture': status(job)}
        job.state = 'failed' if job.owner else 'stopped'
    db.execute(update(OutingLog).where(OutingLog.id == outing_id, OutingLog.ended_at.is_(None))
               .values(ended_at=utcnow()))
    db.commit()
    db.refresh(row)
    return outings.outing_out(row)


@router.get('/{outing_id}/summary')
def get_summary(outing_id: str, pet_id: str, db=Depends(get_db)):
    row = outings.require_outing(db, outing_id, pet_id)
    result = outings.summary(db, row)
    if db.get(CaptureJob, outing_id):
        from .capture import status
        result['capture'] = status(db.get(CaptureJob, outing_id))
    return result


@router.post('/{outing_id}/explain')
def explain(outing_id: str, data: ExplainRequest, db=Depends(get_db)):
    return outings.explain(db, outings.require_outing(db, outing_id, data.pet_id), data.question)
