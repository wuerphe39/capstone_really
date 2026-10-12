from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from database import FeedingLog, get_db
from schemas import FeedingIn, FeedingOut
import uuid
from mqtt_client import publish_feed
from services.safety import validate_feeding
from settings import settings

router = APIRouter(prefix="/feeding", tags=["feeding"])


@router.post("/", response_model=FeedingOut)
def feed(data: FeedingIn, db: Session = Depends(get_db)):
    if not settings.allow_direct_feeding:
        raise HTTPException(
            status_code=403,
            detail="직접 급식은 비활성화되어 있습니다. 케어 제안을 생성하고 보호자 승인을 사용하세요.",
        )
    validate_feeding(db, data.amount_g)
    command_id = str(uuid.uuid4())
    published = publish_feed(command_id, data.amount_g)

    log = FeedingLog(
        **data.model_dump(),
        command_id=command_id,
        status="requested" if published else "failed",
        error=None if published else "MQTT 명령 전송에 실패했습니다.",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/", response_model=list[FeedingOut])
def get_list(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(FeedingLog).order_by(FeedingLog.timestamp.desc()).limit(limit).all()
