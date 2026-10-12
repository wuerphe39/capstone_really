from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from settings import settings


DATABASE_URL = settings.database_url
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
if DATABASE_URL == "sqlite://":
    engine_kwargs["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_kwargs)
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
    command_id = Column(String, unique=True, index=True, nullable=True)
    status = Column(String, default="completed")
    actual_amount_g = Column(Float, nullable=True)
    error = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)


class SensorLog(Base):
    __tablename__ = "sensor_logs"
    id = Column(Integer, primary_key=True, index=True)
    temperature = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    feed_remaining_g = Column(Float, nullable=True)
    bark_detected = Column(Integer, default=0)
    bark_count = Column(Integer, default=0)
    bark_volume = Column(Float, default=0.0)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)


class CareSuggestionLog(Base):
    __tablename__ = "care_suggestions"
    id = Column(Integer, primary_key=True, index=True)
    state = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    reasons_json = Column(Text, nullable=False, default="[]")
    recommended_actions_json = Column(Text, nullable=False, default="[]")
    music_style = Column(String, nullable=True)
    feeding_amount_g = Column(Float, nullable=True)
    severity = Column(String, nullable=False, default="info")
    status = Column(String, nullable=False, default="pending")
    provider = Column(String, nullable=False, default="rule")
    context_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class CareActionLog(Base):
    __tablename__ = "care_actions"
    id = Column(Integer, primary_key=True, index=True)
    suggestion_id = Column(Integer, ForeignKey("care_suggestions.id"), nullable=False, index=True)
    action_type = Column(String, nullable=False)
    command_id = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, nullable=False, default="requested")
    request_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


def init_db():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
