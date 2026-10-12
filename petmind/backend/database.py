"""SQLite observation, suggestion and command persistence, adapted from legacy backend."""
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, Float, Boolean, Index, UniqueConstraint, create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from .settings import settings


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


kwargs = {'connect_args': {'check_same_thread': False}} if settings.database_url.startswith('sqlite') else {}
if settings.database_url in {'sqlite://', 'sqlite:///:memory:'}:
    kwargs['poolclass'] = StaticPool
engine = create_engine(settings.database_url, **kwargs)
if settings.database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def _enable_foreign_keys(connection, _record):
        connection.execute('PRAGMA foreign_keys=ON')

SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class ObservationLog(Base):
    __tablename__ = 'observations'
    id = Column(Integer, primary_key=True)
    pet_id = Column(String, nullable=False, index=True)
    session_id = Column(String, nullable=False, index=True)
    observed_at = Column(DateTime, nullable=False, index=True)
    source = Column(String, nullable=False)
    context_json = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    __table_args__ = (UniqueConstraint('pet_id', 'session_id', 'observed_at', name='observation_identity'),)


class PetProfileLog(Base):
    __tablename__ = 'pet_profiles'
    pet_id = Column(String, primary_key=True)
    profile_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class CareSuggestionLog(Base):
    __tablename__ = 'care_suggestions'
    id = Column(Integer, primary_key=True)
    observation_id = Column(Integer, ForeignKey('observations.id'), nullable=False)
    pet_id = Column(String, nullable=False, index=True)
    state = Column(String, nullable=False)
    summary = Column(Text, nullable=False)
    reasons_json = Column(Text, nullable=False, default='[]')
    recommended_actions_json = Column(Text, nullable=False, default='[]')
    music_style = Column(String)
    severity = Column(String, nullable=False, default='info')
    status = Column(String, nullable=False, default='pending')
    provider = Column(String, nullable=False)
    context_json = Column(Text, nullable=False)
    retrieval_json = Column(Text, nullable=False)
    cited_ids_json = Column(Text, nullable=False, default='[]')
    question = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow, index=True)


class CareActionLog(Base):
    __tablename__ = 'care_actions'
    id = Column(Integer, primary_key=True)
    suggestion_id = Column(Integer, ForeignKey('care_suggestions.id'), nullable=False, unique=True)
    command_id = Column(String, nullable=False, unique=True, index=True)
    action_type = Column(String, nullable=False, default='music')
    status = Column(String, nullable=False, default='requested')
    request_json = Column(Text, nullable=False)
    result_json = Column(Text)
    error = Column(Text)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)


class FeedbackLog(Base):
    __tablename__ = 'guardian_feedback'
    id = Column(Integer, primary_key=True)
    observation_id = Column(Integer, ForeignKey('observations.id'), nullable=False, index=True)
    suggestion_id = Column(Integer, ForeignKey('care_suggestions.id'))
    feedback_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=utcnow)


class AudioClipLog(Base):
    __tablename__ = 'audio_clips'
    id = Column(String, primary_key=True)
    pet_id = Column(String, nullable=False, index=True)
    observation_id = Column(Integer, ForeignKey('observations.id'), nullable=False, unique=True)
    filename = Column(String, nullable=False)
    sha256 = Column(String, nullable=False)
    duration_s = Column(Float, nullable=False)
    training_consent = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False)
    deleted_at = Column(DateTime)
    analysis_json = Column(Text, nullable=False)
    review_json = Column(Text, nullable=False, default='{}')
    verified_at = Column(DateTime)
    created_at = Column(DateTime, default=utcnow)


class AudioVerificationLog(Base):
    __tablename__ = 'audio_verifications'
    clip_id = Column(String, ForeignKey('audio_clips.id'), primary_key=True)
    label = Column(String, nullable=False)
    reviewer = Column(String, nullable=False)
    reason = Column(Text, nullable=False)
    review_sha256 = Column(String, nullable=False)
    audio_sha256 = Column(String, nullable=False)
    verified_at = Column(DateTime, nullable=False, default=utcnow)


class OutingLog(Base):
    __tablename__ = 'outings'
    id = Column(String, primary_key=True)
    pet_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    input_mode = Column(String, nullable=False)
    started_at = Column(DateTime, nullable=False, default=utcnow)
    store_consent_at = Column(DateTime)
    ended_at = Column(DateTime)
    __table_args__ = (Index('one_active_outing_per_pet', 'pet_id', unique=True,
                           sqlite_where=text('ended_at IS NULL')) ,)


class CaptureJob(Base):
    __tablename__ = 'capture_jobs'
    outing_id = Column(String, ForeignKey('outings.id'), primary_key=True)
    pet_id = Column(String, nullable=False, index=True)
    state = Column(String, nullable=False, default='waiting')
    owner = Column(String)
    heartbeat_at = Column(DateTime)
    stop_requested = Column(Boolean, nullable=False, default=False)


class OutingObservation(Base):
    __tablename__ = 'outing_observations'
    observation_id = Column(Integer, ForeignKey('observations.id'), primary_key=True)
    outing_id = Column(String, ForeignKey('outings.id'), nullable=False, index=True)


class ObservationMedia(Base):
    __tablename__ = 'observation_media'
    observation_id = Column(Integer, ForeignKey('observations.id'), primary_key=True)
    filename = Column(String, nullable=False)
    sha256 = Column(String, nullable=False)
    start_s = Column(Float, nullable=False)
    end_s = Column(Float, nullable=False)
    source_json = Column(Text, nullable=False)


def init_db():
    Base.metadata.create_all(engine)
    # Existing single-file SQLite databases predate outing-level consent evidence.
    if engine.dialect.name == 'sqlite':
        with engine.begin() as connection:
            columns = {row[1] for row in connection.exec_driver_sql('PRAGMA table_info(outings)')}
            if 'store_consent_at' not in columns:
                connection.exec_driver_sql('ALTER TABLE outings ADD COLUMN store_consent_at DATETIME')


def get_db():
    with SessionLocal() as db:
        yield db
