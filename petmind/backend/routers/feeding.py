from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import FeedingLog, get_db
from schemas import FeedingIn, FeedingOut
from mqtt_client import publish_feed

router = APIRouter(prefix="/feeding", tags=["feeding"])


@router.post("/", response_model=FeedingOut)
def feed(data: FeedingIn, db: Session = Depends(get_db)):
    # MQTT로 라파에 급식 명령 전송
    publish_feed(data.amount_g)

    log = FeedingLog(**data.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/", response_model=list[FeedingOut])
def get_list(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(FeedingLog).order_by(FeedingLog.timestamp.desc()).limit(limit).all()
