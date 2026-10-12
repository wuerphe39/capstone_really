"""Attach a bounded video excerpt to server-verified LSTM detections."""
import hashlib
import json
import math
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from ..database import AudioClipLog, ObservationMedia, OutingObservation, get_db, utcnow
from ..schemas import StrictModel
from .audio_clips import require_clip
from . import outings
from pet_monitor.event_video import candidate_windows

router = APIRouter(prefix='/event-videos', tags=['audio event video'])
MAX_BYTES = 64*1024*1024


def rows_for_event(db, pet_id, clip_ids):
    if not 1 <= len(clip_ids) <= 24 or len(set(clip_ids)) != len(clip_ids):
        raise HTTPException(422, '사건당 서로 다른 음원 1~24개가 필요합니다.')
    rows = [require_clip(db, cid, pet_id) for cid in clip_ids]
    sessions, kinds, outings_set = set(), set(), set()
    windows = []
    for row in rows:
        if row.deleted_at or row.expires_at <= utcnow():
            raise HTTPException(410, '원본 음원 보관 기간이 끝났습니다.')
        analysis = json.loads(row.analysis_json)
        capture = analysis.get('capture')
        positives = candidate_windows(analysis)
        if not capture or not positives:
            raise HTTPException(422, '수집 시각과 서버의 음성 LSTM 감지 결과가 필요합니다.')
        start = datetime.fromisoformat(capture['started_at']).timestamp()
        windows.extend((start+w['start_s'], start+w['end_s']) for w in positives)
        sessions.add(capture['session_id']); kinds.add(capture['kind'])
        link = db.get(OutingObservation, row.observation_id)
        outings_set.add(link.outing_id if link else None)
    if len(sessions) != 1 or len(kinds) != 1 or len(outings_set) != 1:
        raise HTTPException(422, '서로 다른 수집·외출 세션을 하나의 사건으로 합칠 수 없습니다.')
    return rows, sorted(windows), kinds.pop()


def persist(db, pet_id, clip_ids, started_at, pre_s, post_s, content):
    import cv2
    rows, windows, kind = rows_for_event(db, pet_id, clip_ids)
    if len(content) < 12 or content[4:8] != b'ftyp':
        raise HTTPException(422, 'MP4 컨테이너가 필요합니다.')
    if started_at.tzinfo is None:
        raise HTTPException(422, '영상 시작 시각에 시간대가 필요합니다.')
    start = started_at.astimezone(timezone.utc).timestamp()
    wanted_start, wanted_end = windows[0][0]-pre_s, max(b for _, b in windows)+post_s
    if wanted_end-wanted_start > 120:
        raise HTTPException(422, '사건 구간은 120초 이하여야 합니다.')
    # Gaps beyond the roll windows are distinct events, not a continuous excerpt.
    reach = windows[0][1]+post_s
    for a, b in windows[1:]:
        if a-pre_s > reach+.05:
            raise HTTPException(422, '겹치지 않는 감지는 별도 사건으로 저장해야 합니다.')
        reach = max(reach, b+post_s)
    root = outings.MEDIA_ROOT
    root.mkdir(parents=True, exist_ok=True)
    path = root/('event-'+uuid.uuid4().hex+'.mp4')
    path.write_bytes(content)
    try:
        cap = cv2.VideoCapture(str(path))
        try:
            fps, frames = cap.get(cv2.CAP_PROP_FPS), cap.get(cv2.CAP_PROP_FRAME_COUNT)
            decoded, _ = cap.read()
        finally:
            cap.release()
        duration = frames/fps if fps > 0 else 0
        if not decoded or not math.isfinite(duration) or not 0 < duration <= 120:
            raise HTTPException(422, '재생 가능한 120초 이하 영상이 필요합니다.')
        end = start+duration
        if start < wanted_start-.25 or end > wanted_end+.25 or not any(start < b and end > a for a,b in windows):
            raise HTTPException(422, '영상 시각이 감지 전후 구간과 일치하지 않습니다.')
        if end > datetime.now(timezone.utc).timestamp()+.25:
            raise HTTPException(422, '미래 영상 시각은 허용하지 않습니다.')
        digest = hashlib.sha256(content).hexdigest()
        existing = [db.get(ObservationMedia, row.observation_id) for row in rows]
        if any(existing):
            if all(m and m.sha256 == digest and
                   json.loads(m.source_json).get('clip_ids') == clip_ids and
                   abs(json.loads(m.source_json).get('video_start', -1)-start) < .001 for m in existing):
                return json.loads(existing[0].source_json)
            raise HTTPException(409, '이미 연결된 사건 영상은 덮어쓸 수 없습니다.')
        missing_pre, missing_post = max(0.,start-wanted_start), max(0.,wanted_end-end)
        source = {'kind':'audio_triggered_video', 'capture_kind':kind,
                  'event_id':path.stem, 'clip_ids':clip_ids, 'video_start':start,
                  'video_end':end, 'requested_start':wanted_start, 'requested_end':wanted_end,
                  'detection_windows':windows, 'missing_pre_s':round(missing_pre,3),
                  'missing_post_s':round(missing_post,3),
                  'status':'partial' if max(missing_pre,missing_post) > .25 else 'ready',
                  'attribution':'동일 입력의 음성 LSTM 감지 구간; 영상 자동 행동 분석 없음'}
        for row in rows:
            db.add(ObservationMedia(observation_id=row.observation_id, filename=path.name,
                   sha256=digest, start_s=0, end_s=duration, source_json=json.dumps(source,ensure_ascii=False)))
            analysis = json.loads(row.analysis_json)
            analysis['event_video'] = source
            row.analysis_json = json.dumps(analysis,ensure_ascii=False)
        db.commit()
        return source
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '다른 요청이 이 관찰의 영상을 먼저 저장했습니다.')
    except Exception:
        db.rollback()
        raise
    finally:
        # Retain only a committed reference; retries must not leave orphan files.
        if not db.scalars(select(ObservationMedia).where(ObservationMedia.filename == path.name)).first():
            path.unlink(missing_ok=True)


@router.post('', status_code=201)
async def upload(request: Request, pet_id: str, started_at: datetime,
                 clip_ids: list[str] = Query(), store_consent: bool = False,
                 pre_s: float = Query(default=5, ge=0, le=15, allow_inf_nan=False),
                 post_s: float = Query(default=5, ge=0, le=15, allow_inf_nan=False), db=Depends(get_db)):
    if not store_consent:
        raise HTTPException(422, '영상 저장 동의가 필요합니다.')
    rows_for_event(db, pet_id, clip_ids)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content)>MAX_BYTES:
            raise HTTPException(413, '영상은 64MB 이하여야 합니다.')
    return await run_in_threadpool(persist, db, pet_id, clip_ids, started_at, pre_s, post_s, bytes(content))


class Missing(StrictModel):
    pet_id: str
    clip_ids: list[str]
    reason: str  # limited to known failure categories below


@router.post('/missing')
def missing(data: Missing, db=Depends(get_db)):
    if data.reason not in {'camera_unavailable','buffer_gap','encode_failed','upload_failed'}:
        raise HTTPException(422, '알 수 없는 영상 실패 사유입니다.')
    rows, _, _ = rows_for_event(db,data.pet_id,data.clip_ids)
    for row in rows:
        if db.get(ObservationMedia,row.observation_id):
            raise HTTPException(409,'이미 연결된 영상을 실패 상태로 바꿀 수 없습니다.')
        analysis=json.loads(row.analysis_json)
        analysis['event_video']={'status':'missing','reason':data.reason}
        row.analysis_json=json.dumps(analysis,ensure_ascii=False)
    db.commit()
    return {'status':'missing','reason':data.reason}
