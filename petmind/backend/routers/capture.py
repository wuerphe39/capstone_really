"""Single household pull agent. Expose only over local/SSH network."""
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import Field
from sqlalchemy import select, update
from ..database import CaptureJob, OutingLog, get_db, utcnow
from ..schemas import StrictModel
from ..services.outings import require_outing

router = APIRouter(prefix='/capture', tags=['capture'])
LEASE_SECONDS = 30


def status(job):
    if job is None:
        return {'state': 'manual', 'stop_requested': False}
    stale = job.owner and (not job.heartbeat_at or utcnow()-job.heartbeat_at > timedelta(seconds=LEASE_SECONDS))
    state = 'disconnected' if stale and job.state not in {'stopped', 'failed', 'clock_mismatch'} else job.state
    return {'state': state, 'stop_requested': job.stop_requested,
            'heartbeat_at': job.heartbeat_at.isoformat()+'Z' if job.heartbeat_at else None}


class AgentRequest(StrictModel):
    pet_id: str = Field(min_length=1, max_length=80)
    owner: str = Field(min_length=16, max_length=80)
    state: Literal['starting', 'capturing', 'model_unavailable', 'draining', 'stopped', 'failed', 'clock_mismatch'] = 'starting'


@router.get('/{outing_id}')
def get_status(outing_id: str, pet_id: str, db=Depends(get_db)):
    require_outing(db, outing_id, pet_id)
    return status(db.get(CaptureJob, outing_id))


@router.post('/claim')
def claim(data: AgentRequest, db=Depends(get_db)):
    # Do not steal expired jobs: a partitioned device may still own the camera.
    job = db.scalars(select(CaptureJob).join(OutingLog).where(
        CaptureJob.pet_id == data.pet_id, CaptureJob.owner.is_(None),
        CaptureJob.stop_requested.is_(False), OutingLog.ended_at.is_(None))).first()
    if not job:
        return {'job': None}
    changed = db.execute(update(CaptureJob).where(CaptureJob.outing_id == job.outing_id,
        CaptureJob.owner.is_(None), CaptureJob.stop_requested.is_(False)).values(
            owner=data.owner, state='starting', heartbeat_at=utcnow()))
    db.commit()
    return {'job': {'outing_id': job.outing_id, 'pet_id': job.pet_id} if changed.rowcount else None,
            'server_time': utcnow().isoformat()+'Z'}


@router.post('/{outing_id}/heartbeat')
def heartbeat(outing_id: str, data: AgentRequest, db=Depends(get_db)):
    row = require_outing(db, outing_id, data.pet_id)
    job = db.get(CaptureJob, outing_id)
    if not job or job.owner != data.owner:
        raise HTTPException(409, '수집 작업 소유자가 다릅니다.')
    if row.ended_at or job.state in {'stopped', 'failed', 'clock_mismatch'}:
        return {'stop': True, **status(job), 'server_time': utcnow().isoformat()+'Z'}
    job.heartbeat_at = utcnow()
    job.state = data.state
    if data.state in {'stopped', 'failed', 'clock_mismatch'}:
        row.ended_at = utcnow()
    db.commit()
    return {'stop': job.stop_requested, **status(job), 'server_time': utcnow().isoformat()+'Z'}
