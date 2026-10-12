from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database import FeedingLog
from settings import settings


MAX_FEEDING_G = settings.max_feeding_g
MAX_DAILY_FEEDING_G = settings.max_daily_feeding_g
FEEDING_COOLDOWN_MINUTES = settings.feeding_cooldown_minutes


def validate_feeding(db: Session, amount_g: float) -> None:
    if amount_g <= 0 or amount_g > MAX_FEEDING_G:
        raise HTTPException(
            status_code=422,
            detail=f"1회 급식량은 0g 초과 {MAX_FEEDING_G:g}g 이하여야 합니다.",
        )

    now = datetime.utcnow()
    latest = (
        db.query(FeedingLog)
        .filter(FeedingLog.status.in_(["requested", "acknowledged", "completed"]))
        .order_by(FeedingLog.timestamp.desc())
        .first()
    )
    if latest and now - latest.timestamp < timedelta(minutes=FEEDING_COOLDOWN_MINUTES):
        raise HTTPException(status_code=409, detail="재급식 대기시간이 지나지 않았습니다.")

    since = now - timedelta(hours=24)
    recent = (
        db.query(FeedingLog)
        .filter(
            FeedingLog.timestamp >= since,
            FeedingLog.status.in_(["requested", "acknowledged", "completed"]),
        )
        .all()
    )
    if sum(row.amount_g for row in recent) + amount_g > MAX_DAILY_FEEDING_G:
        raise HTTPException(status_code=409, detail="24시간 급식량 안전 한도를 초과합니다.")
