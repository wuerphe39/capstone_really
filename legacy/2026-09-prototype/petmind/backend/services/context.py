from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database import AnalysisLog, FeedingLog, SensorLog
from schemas import PetContext


def build_pet_context(db: Session, window_seconds: int = 30) -> PetContext:
    now = datetime.utcnow()
    since = now - timedelta(seconds=window_seconds)
    analyses = (
        db.query(AnalysisLog)
        .filter(AnalysisLog.timestamp >= since)
        .order_by(AnalysisLog.timestamp.asc())
        .all()
    )

    scores: dict[str, float] = defaultdict(float)
    for row in analyses:
        scores[row.behavior] += row.behavior_conf or 0.0

    observed = max(scores, key=scores.get) if scores else "unknown"
    matching = [row for row in analyses if row.behavior == observed]
    confidence = (
        sum((row.behavior_conf or 0.0) for row in matching) / len(matching)
        if matching
        else 0.0
    )
    duration = (
        max(0.0, (matching[-1].timestamp - matching[0].timestamp).total_seconds())
        if len(matching) >= 2
        else 0.0
    )

    sensor = db.query(SensorLog).order_by(SensorLog.timestamp.desc()).first()
    feeding = (
        db.query(FeedingLog)
        .filter(FeedingLog.status == "completed")
        .order_by(FeedingLog.timestamp.desc())
        .first()
    )
    feeding_due = bool(feeding and now - feeding.timestamp >= timedelta(hours=6))

    return PetContext(
        observed_behavior=observed,
        behavior_confidence=confidence,
        behavior_duration_seconds=duration,
        bark_detected=bool(sensor.bark_detected) if sensor else False,
        bark_count=sensor.bark_count if sensor else 0,
        bark_volume=sensor.bark_volume if sensor else 0.0,
        temperature=sensor.temperature if sensor else None,
        humidity=sensor.humidity if sensor else None,
        feed_remaining_g=sensor.feed_remaining_g if sensor else None,
        last_feeding_at=feeding.timestamp if feeding else None,
        last_feeding_amount_g=feeding.amount_g if feeding else None,
        feeding_due=feeding_due,
        generated_at=now,
    )
