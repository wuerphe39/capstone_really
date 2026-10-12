import json
import uuid
from datetime import datetime, timedelta

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from database import CareActionLog, CareSuggestionLog, FeedingLog
from mqtt_client import publish_feed, publish_music
from providers import RuleBasedProvider, get_provider
from schemas import (
    CareActionOut,
    CareActionType,
    CareSuggestionDraft,
    CareSuggestionOut,
    PetContext,
)
from services.safety import validate_feeding
from settings import settings


MUSIC_STYLES = {"calm_piano", "nature_sounds", "white_noise"}


def _loads(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def suggestion_to_out(row: CareSuggestionLog) -> CareSuggestionOut:
    return CareSuggestionOut(
        id=row.id,
        state=row.state,
        summary=row.summary,
        reasons=_loads(row.reasons_json, []),
        recommended_actions=_loads(row.recommended_actions_json, []),
        music_style=row.music_style,
        feeding_amount_g=row.feeding_amount_g,
        severity=row.severity,
        status=row.status,
        provider=row.provider,
        context=PetContext.model_validate(_loads(row.context_json, {})),
        created_at=row.created_at,
    )


def action_to_out(row: CareActionLog) -> CareActionOut:
    return CareActionOut(
        id=row.id,
        suggestion_id=row.suggestion_id,
        action_type=row.action_type,
        command_id=row.command_id,
        status=row.status,
        request=_loads(row.request_json, {}),
        result=_loads(row.result_json, None),
        error=row.error,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def evaluate(db: Session, context: PetContext) -> CareSuggestionOut:
    provider = get_provider()
    provider_name = provider.name
    try:
        draft = CareSuggestionDraft.model_validate(provider.suggest(context))
    except (Exception, ValidationError) as exc:
        print(f"[Care] provider failed, using rules: {exc}")
        provider = RuleBasedProvider()
        provider_name = "rule-fallback"
        draft = provider.suggest(context)

    row = CareSuggestionLog(
        state=draft.state,
        summary=draft.summary,
        reasons_json=json.dumps(draft.reasons, ensure_ascii=False),
        recommended_actions_json=json.dumps(
            [action.value for action in draft.recommended_actions], ensure_ascii=False
        ),
        music_style=draft.music_style,
        feeding_amount_g=draft.feeding_amount_g,
        severity=draft.severity.value,
        status="pending" if draft.recommended_actions else "informational",
        provider=provider_name,
        context_json=context.model_dump_json(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return suggestion_to_out(row)


def approve(db: Session, suggestion_id: int, action_type: CareActionType) -> CareActionOut:
    suggestion = db.get(CareSuggestionLog, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="케어 제안을 찾을 수 없습니다.")
    if suggestion.status not in {"pending", "partially_approved", "action_failed"}:
        raise HTTPException(status_code=409, detail="실행 가능한 액션이 남은 제안만 승인할 수 있습니다.")

    allowed = _loads(suggestion.recommended_actions_json, [])
    if action_type.value not in allowed:
        raise HTTPException(status_code=422, detail="이 제안에 허용되지 않은 액션입니다.")

    if (
        db.query(CareActionLog)
        .filter(
            CareActionLog.suggestion_id == suggestion_id,
            CareActionLog.action_type == action_type.value,
        )
        .first()
    ):
        raise HTTPException(status_code=409, detail="이미 실행 요청된 액션입니다.")

    command_id = str(uuid.uuid4())
    request: dict
    simulate = settings.simulate_actions
    published = simulate
    feeding_log = None
    if action_type == CareActionType.feeding:
        amount = suggestion.feeding_amount_g or 0.0
        validate_feeding(db, amount)
        request = {"amount_g": amount}
        feeding_log = FeedingLog(
            amount_g=amount,
            triggered_by="care_approved",
            command_id=command_id,
            status="requested",
        )
        db.add(feeding_log)
        if not simulate:
            published = publish_feed(command_id, amount)
    else:
        style = suggestion.music_style or "calm_piano"
        if style not in MUSIC_STYLES:
            raise HTTPException(status_code=422, detail="등록되지 않은 음악 유형입니다.")
        request = {"style": style}
        if not simulate:
            published = publish_music(command_id, style)

    status = "completed" if simulate else ("requested" if published else "failed")
    error = None if published or simulate else "MQTT 명령 전송에 실패했습니다."
    result = {"simulated": True} if simulate else None
    row = CareActionLog(
        suggestion_id=suggestion.id,
        action_type=action_type.value,
        command_id=command_id,
        status=status,
        request_json=json.dumps(request, ensure_ascii=False),
        result_json=json.dumps(result) if result else None,
        error=error,
    )
    if feeding_log:
        feeding_log.status = status
        feeding_log.error = error
        if simulate:
            feeding_log.actual_amount_g = feeding_log.amount_g
    action_types = {
        item.action_type
        for item in db.query(CareActionLog)
        .filter(CareActionLog.suggestion_id == suggestion_id)
        .all()
    }
    action_types.add(action_type.value)
    all_actions_requested = set(allowed).issubset(action_types)
    if status == "failed":
        suggestion.status = "action_failed"
    elif all_actions_requested:
        suggestion.status = "approved"
    else:
        suggestion.status = "partially_approved"
    db.add(row)
    db.commit()
    db.refresh(row)
    return action_to_out(row)


def dismiss(db: Session, suggestion_id: int) -> CareSuggestionOut:
    suggestion = db.get(CareSuggestionLog, suggestion_id)
    if not suggestion:
        raise HTTPException(status_code=404, detail="케어 제안을 찾을 수 없습니다.")
    if suggestion.status not in {"pending", "partially_approved", "action_failed"}:
        raise HTTPException(status_code=409, detail="실행 가능한 액션이 남은 제안만 거절할 수 있습니다.")
    suggestion.status = (
        "partially_dismissed"
        if db.query(CareActionLog)
        .filter(CareActionLog.suggestion_id == suggestion_id)
        .first()
        else "dismissed"
    )
    db.commit()
    db.refresh(suggestion)
    return suggestion_to_out(suggestion)


def acknowledge(
    db: Session,
    command_id: str,
    status: str,
    actual_amount_g: float | None = None,
    detail: str | None = None,
) -> CareActionOut:
    if status not in {"acknowledged", "completed", "failed"}:
        raise HTTPException(status_code=422, detail="지원하지 않는 액션 상태입니다.")
    action = (
        db.query(CareActionLog).filter(CareActionLog.command_id == command_id).first()
    )
    if not action:
        raise HTTPException(status_code=404, detail="액션 명령을 찾을 수 없습니다.")
    action.status = status
    action.updated_at = datetime.utcnow()
    action.error = detail if status == "failed" else None
    action.result_json = json.dumps(
        {"actual_amount_g": actual_amount_g, "detail": detail}, ensure_ascii=False
    )
    feeding = (
        db.query(FeedingLog).filter(FeedingLog.command_id == command_id).first()
    )
    if feeding:
        feeding.status = status
        feeding.actual_amount_g = actual_amount_g
        feeding.error = detail if status == "failed" else None
    db.commit()
    db.refresh(action)
    return action_to_out(action)


def expire_stale_actions(db: Session) -> int:
    """Mark device commands without a terminal acknowledgement as failed."""
    timeout_seconds = settings.action_timeout_seconds
    deadline = datetime.utcnow() - timedelta(seconds=timeout_seconds)
    actions = (
        db.query(CareActionLog)
        .filter(
            CareActionLog.status.in_(["requested", "acknowledged"]),
            CareActionLog.created_at < deadline,
        )
        .all()
    )
    for action in actions:
        action.status = "failed"
        action.error = "장치 완료 응답 시간이 초과되었습니다."
        action.updated_at = datetime.utcnow()
        feeding = (
            db.query(FeedingLog)
            .filter(FeedingLog.command_id == action.command_id)
            .first()
        )
        if feeding:
            feeding.status = "failed"
            feeding.error = action.error
    if actions:
        db.commit()
    return len(actions)
