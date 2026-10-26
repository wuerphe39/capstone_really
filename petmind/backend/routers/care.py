from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

from ..database import CareActionLog, CareSuggestionLog, SustainedBarkAlert, get_db
from ..schemas import ActionAckIn, ApproveRequest, EvaluateRequest
from ..services.alerts import alert_to_out
from ..services.care import (acknowledge, action_to_out, approve, care_target, dismiss, evaluate,
                             expire_stale_actions, suggestion_to_out)

router = APIRouter(prefix='/care', tags=['care'])


@router.post('/evaluate')
def evaluate_current(data: EvaluateRequest, db=Depends(get_db)):
    return evaluate(db, data.observation_id, data.question)


@router.get('/target')
def target(pet_id: str, db=Depends(get_db)):
    return care_target(db, pet_id)


@router.get('/alerts')
def alerts(pet_id: str, limit: int = Query(10, ge=1, le=50), db=Depends(get_db)):
    rows = db.scalars(select(SustainedBarkAlert).where(SustainedBarkAlert.pet_id == pet_id)
                      .order_by(SustainedBarkAlert.created_at.desc()).limit(limit)).all()
    return [alert_to_out(row) for row in rows]


@router.get('/latest')
def latest(pet_id: str, db=Depends(get_db)):
    row = db.scalars(select(CareSuggestionLog).where(CareSuggestionLog.pet_id == pet_id)
                     .order_by(CareSuggestionLog.created_at.desc())).first()
    return suggestion_to_out(row) if row else None


@router.get('/history')
def history(pet_id: str, limit: int = Query(20, ge=1, le=100), db=Depends(get_db)):
    rows = db.scalars(select(CareSuggestionLog).where(CareSuggestionLog.pet_id == pet_id)
                      .order_by(CareSuggestionLog.created_at.desc()).limit(limit)).all()
    return [suggestion_to_out(row) for row in rows]


@router.post('/{suggestion_id}/approve')
def approve_action(suggestion_id: int, data: ApproveRequest, db=Depends(get_db)):
    return approve(db, suggestion_id, data.action_type)


@router.post('/{suggestion_id}/dismiss')
def dismiss_suggestion(suggestion_id: int, db=Depends(get_db)):
    return dismiss(db, suggestion_id)


@router.get('/actions/recent')
def recent_actions(pet_id: str, limit: int = Query(20, ge=1, le=100), db=Depends(get_db)):
    expire_stale_actions(db)
    rows = db.scalars(select(CareActionLog).join(CareSuggestionLog)
                      .where(CareSuggestionLog.pet_id == pet_id)
                      .order_by(CareActionLog.created_at.desc()).limit(limit)).all()
    return [action_to_out(row) for row in rows]


@router.get('/actions/pending')
def pending_actions(db=Depends(get_db)):
    expire_stale_actions(db)
    rows = db.scalars(select(CareActionLog).where(CareActionLog.status.in_(['requested', 'acknowledged']))
                      .order_by(CareActionLog.created_at).limit(100)).all()
    return [action_to_out(row) for row in rows]


@router.post('/actions/{command_id}/ack')
def acknowledge_action(command_id: str, data: ActionAckIn, db=Depends(get_db)):
    return acknowledge(db, command_id, data.status, data.detail, data.simulated)
