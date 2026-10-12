from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import CareActionLog, CareSuggestionLog, get_db
from schemas import (
    ActionAckIn,
    ApproveRequest,
    CareActionOut,
    CareSuggestionOut,
    EvaluateRequest,
)
from services.care import (
    acknowledge,
    action_to_out,
    approve,
    dismiss,
    evaluate,
    expire_stale_actions,
    suggestion_to_out,
)
from services.context import build_pet_context

router = APIRouter(prefix="/care", tags=["care"])


@router.post("/evaluate", response_model=CareSuggestionOut)
def evaluate_current(data: EvaluateRequest | None = None, db: Session = Depends(get_db)):
    context = data.context if data and data.context else build_pet_context(db)
    return evaluate(db, context)


@router.get("/latest", response_model=CareSuggestionOut | None)
def latest(db: Session = Depends(get_db)):
    row = db.query(CareSuggestionLog).order_by(CareSuggestionLog.created_at.desc()).first()
    return suggestion_to_out(row) if row else None


@router.get("/history", response_model=list[CareSuggestionOut])
def history(limit: int = 20, db: Session = Depends(get_db)):
    rows = (
        db.query(CareSuggestionLog)
        .order_by(CareSuggestionLog.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return [suggestion_to_out(row) for row in rows]


@router.post("/{suggestion_id}/approve", response_model=CareActionOut)
def approve_action(
    suggestion_id: int,
    data: ApproveRequest,
    db: Session = Depends(get_db),
):
    return approve(db, suggestion_id, data.action_type)


@router.post("/{suggestion_id}/dismiss", response_model=CareSuggestionOut)
def dismiss_suggestion(suggestion_id: int, db: Session = Depends(get_db)):
    return dismiss(db, suggestion_id)


@router.get("/actions/recent", response_model=list[CareActionOut])
def recent_actions(limit: int = 20, db: Session = Depends(get_db)):
    expire_stale_actions(db)
    rows = (
        db.query(CareActionLog)
        .order_by(CareActionLog.created_at.desc())
        .limit(min(max(limit, 1), 100))
        .all()
    )
    return [action_to_out(row) for row in rows]


@router.post("/actions/{command_id}/ack", response_model=CareActionOut)
def acknowledge_action(
    command_id: str,
    data: ActionAckIn,
    db: Session = Depends(get_db),
):
    return acknowledge(db, command_id, data.status, data.actual_amount_g, data.detail)
