from datetime import datetime
from pathlib import Path
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = Path(__file__).parent / "petmind.db"
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class AnalysisLog(Base):
    __tablename__ = "analysis_logs"
    id         = Column(Integer, primary_key=True, index=True)
    behavior   = Column(String, nullable=False)
    behavior_conf = Column(Float)
    emotion    = Column(String, nullable=False)
    emotion_conf  = Column(Float)
    timestamp  = Column(DateTime, default=datetime.utcnow)


class FeedingLog(Base):
    __tablename__ = "feeding_logs"
    id        = Column(Integer, primary_key=True, index=True)
    amount_g  = Column(Float, nullable=False)
    triggered_by = Column(String, default="manual")  # manual | auto
    timestamp = Column(DateTime, default=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
