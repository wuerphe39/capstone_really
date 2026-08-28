from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import AnalysisLog, get_db
from schemas import AnalysisIn, AnalysisOut

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("/", response_model=AnalysisOut)
def create(data: AnalysisIn, db: Session = Depends(get_db)):
    log = AnalysisLog(**data.model_dump())
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


@router.get("/", response_model=list[AnalysisOut])
def get_list(limit: int = 50, db: Session = Depends(get_db)):
    return db.query(AnalysisLog).order_by(AnalysisLog.timestamp.desc()).limit(limit).all()


@router.get("/latest", response_model=AnalysisOut | None)
def get_latest(db: Session = Depends(get_db)):
    return db.query(AnalysisLog).order_by(AnalysisLog.timestamp.desc()).first()
