from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import SensorLog, get_db
from schemas import SensorIn, SensorOut

router = APIRouter(prefix="/sensors", tags=["sensors"])


@router.post("/", response_model=SensorOut)
def create(data: SensorIn, db: Session = Depends(get_db)):
    row = SensorLog(**data.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.get("/latest", response_model=SensorOut | None)
def latest(db: Session = Depends(get_db)):
    return db.query(SensorLog).order_by(SensorLog.timestamp.desc()).first()
