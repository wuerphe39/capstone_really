from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field


class AnalysisIn(BaseModel):
    behavior: str
    behavior_conf: float
    emotion: str
    emotion_conf: float


class AnalysisOut(AnalysisIn):
    id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


class FeedingIn(BaseModel):
    amount_g: float
    triggered_by: str = "manual"


class FeedingOut(FeedingIn):
    id: int
    timestamp: datetime
    command_id: str | None = None
    status: str = "completed"
    actual_amount_g: float | None = None
    error: str | None = None

    model_config = {"from_attributes": True}


class SensorIn(BaseModel):
    temperature: float | None = None
    humidity: float | None = None
    feed_remaining_g: float | None = Field(default=None, ge=0)
    bark_detected: bool = False
    bark_count: int = Field(default=0, ge=0)
    bark_volume: float = Field(default=0.0, ge=0)


class SensorOut(SensorIn):
    id: int
    timestamp: datetime

    model_config = {"from_attributes": True}


class PetContext(BaseModel):
    observed_behavior: str = "unknown"
    behavior_confidence: float = Field(default=0.0, ge=0, le=1)
    behavior_duration_seconds: float = Field(default=0.0, ge=0)
    bark_detected: bool = False
    bark_count: int = Field(default=0, ge=0)
    bark_volume: float = Field(default=0.0, ge=0)
    temperature: float | None = None
    humidity: float | None = None
    feed_remaining_g: float | None = Field(default=None, ge=0)
    last_feeding_at: datetime | None = None
    last_feeding_amount_g: float | None = Field(default=None, ge=0)
    feeding_due: bool = False
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class CareSeverity(str, Enum):
    info = "info"
    attention = "attention"
    warning = "warning"
    urgent = "urgent"


class CareActionType(str, Enum):
    music = "music"
    feeding = "feeding"


class CareSuggestionDraft(BaseModel):
    state: str
    summary: str
    reasons: list[str] = Field(default_factory=list)
    recommended_actions: list[CareActionType] = Field(default_factory=list)
    music_style: str | None = None
    feeding_amount_g: float | None = Field(default=None, ge=0)
    severity: CareSeverity = CareSeverity.info


class EvaluateRequest(BaseModel):
    context: PetContext | None = None


class CareSuggestionOut(CareSuggestionDraft):
    id: int
    status: str
    provider: str
    context: PetContext
    created_at: datetime


class ApproveRequest(BaseModel):
    action_type: CareActionType


class CareActionOut(BaseModel):
    id: int
    suggestion_id: int
    action_type: CareActionType
    command_id: str
    status: str
    request: dict
    result: dict | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ActionAckIn(BaseModel):
    status: str
    actual_amount_g: float | None = Field(default=None, ge=0)
    detail: str | None = None
