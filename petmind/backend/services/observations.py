import json

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from pet_monitor.context import MOTION_LABELS_KO
from sqlalchemy import update
from ..database import ObservationLog, OutingLog, OutingObservation, ObservationMedia, utcnow
from ..schemas import ObservationIn, ObservationOut, PetContext


def to_out(row):
    from sqlalchemy.orm import object_session
    db = object_session(row)
    link = db.get(OutingObservation, row.id) if db else None
    return ObservationOut(id=row.id, pet_id=row.pet_id, session_id=row.session_id,
                          observed_at=row.observed_at, source=row.source,
                          context=json.loads(row.context_json), summary=row.summary,
                          outing_id=link.outing_id if link else None)


def save(db, data: ObservationIn, media=None, commit=True):
    if data.outing_id:
        outing = db.get(OutingLog, data.outing_id)
        if outing is None or outing.pet_id != data.pet_id:
            raise HTTPException(404, '이 반려견의 외출 기록을 찾을 수 없습니다.')
        expected = {'synthetic_demo': 'synthetic_demo', 'prepared_video': 'public_media', 'live': 'live', 'uploaded_audio': 'user_audio'}
        if expected[outing.input_mode] != data.source:
            raise HTTPException(422, '외출의 입력 모드와 관찰 출처가 다릅니다.')
        if data.observed_at < outing.started_at or data.observed_at > utcnow():
            raise HTTPException(422, '외출 시작 이후 현재까지의 관찰만 연결할 수 있습니다.')
        if data.source == 'live':
            from datetime import timedelta
            if data.observed_at - timedelta(seconds=data.context.window_s) < outing.started_at:
                raise HTTPException(422, '실시간 관찰 구간은 외출 시작 이후여야 합니다.')
        locked = db.execute(update(OutingLog).where(OutingLog.id == data.outing_id,
                             OutingLog.ended_at.is_(None)).values(title=OutingLog.title)).rowcount
        if not locked:
            db.rollback()
            raise HTTPException(409, '종료된 외출에는 관찰을 추가할 수 없습니다.')
    b, m = data.context.bark, data.context.motion
    summary = (f'{data.context.window_s:g}초 관찰: 소리 크기 변화 {b.count}개(짖음 판별 아님), '
               f'주된 궤적 {MOTION_LABELS_KO[m.dominant]}.')
    if data.source in {'user_audio','live'}:
        summary = f'{data.context.window_s:g}초 음성 관찰: 소리 크기 변화만으로 개 짖음 소리를 판별하지 않습니다. 음성 모델 결과와 원본 확인을 참고합니다.'
    row = ObservationLog(pet_id=data.pet_id, session_id=data.session_id,
                         observed_at=data.observed_at, source=data.source,
                         context_json=data.context.model_dump_json(), summary=summary)
    db.add(row)
    try:
        db.flush()
        if data.outing_id:
            db.add(OutingObservation(observation_id=row.id, outing_id=data.outing_id))
        if media:
            db.add(ObservationMedia(observation_id=row.id, **media))
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '같은 세션·시각의 관찰이 이미 저장되어 있습니다.')
    db.refresh(row)
    result = to_out(row)
    result.outing_id = data.outing_id
    return result


def care_context(row):
    data = json.loads(row.context_json)
    motion, bark = data['motion'], data['bark']
    return PetContext(observed_behavior=motion['dominant'],
                      behavior_duration_seconds=motion['seconds_by_label'].get(motion['dominant'], 0),
                      bark_detected=bark['count'] > 0, bark_count=bark['count'],
                      bark_volume=bark['peak_db'], window_s=data['window_s'],
                      motion_model=data.get('motion_model', 'rule'), input_note=data.get('input_note', ''),
                      lstm_metadata=data.get('lstm_metadata', {}))
