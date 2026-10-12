from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)


class BarkSummary(StrictModel):
    window_s: float = Field(gt=0, le=3600)
    count: int = Field(ge=0)
    rate_per_min: float = Field(ge=0)
    peak_db: float | None = Field(default=None, le=0)
    mean_db: float | None = Field(default=None, le=0)
    total_bark_s: float = Field(ge=0)
    level: Literal['none', 'occasional', 'frequent']

    @model_validator(mode='after')
    def consistent_rate(self):
        if abs(self.rate_per_min - self.count * 60 / self.window_s) > .0001:
            raise ValueError('candidate count and rate do not match')
        if (self.count == 0) != (self.level == 'none'):
            raise ValueError('candidate count and level do not match')
        return self


class MotionSummary(StrictModel):
    window_s: float = Field(gt=0, le=3600)
    dominant: Literal['still', 'moving', 'spinning', 'pacing', 'sit_stand_repeat', 'unknown']
    seconds_by_label: dict[str, float] = Field(default_factory=dict)

    @field_validator('seconds_by_label')
    @classmethod
    def durations(cls, value):
        import math
        if any(not math.isfinite(v) or v < 0 for v in value.values()):
            raise ValueError('durations must be finite and nonnegative')
        return value


class AnalysisContext(StrictModel):
    timestamp: float = Field(ge=0)
    window_s: float = Field(gt=0, le=3600)
    bark: BarkSummary
    motion: MotionSummary
    motion_model: Literal['rule', 'lstm_synthetic'] = 'rule'
    input_note: str = Field(default='', max_length=1000)
    lstm_metadata: dict[str, str | int] = Field(default_factory=dict)

    @model_validator(mode='after')
    def matching_windows(self):
        if self.bark.window_s != self.window_s or self.motion.window_s != self.window_s:
            raise ValueError('audio and motion windows must match')
        if self.bark.total_bark_s > self.window_s or sum(self.motion.seconds_by_label.values()) > self.window_s + 0.01:
            raise ValueError('duration exceeds observation window')
        return self


class ObservationIn(StrictModel):
    pet_id: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=1, max_length=120)
    observed_at: datetime
    source: Literal['synthetic_demo', 'public_media', 'live', 'user_audio']
    context: AnalysisContext
    outing_id: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator('observed_at')
    @classmethod
    def utc_time(cls, value):
        if value.tzinfo is None:
            raise ValueError('observed_at requires timezone, e.g. +09:00 or Z')
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class ObservationOut(ObservationIn):
    id: int
    summary: str
    # Stored SQLite timestamps are UTC; add an offset when serializing/revalidating.
    @field_validator('observed_at', mode='before')
    @classmethod
    def stored_utc(cls, value):
        if isinstance(value, datetime) and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value

    @field_serializer('observed_at')
    def serialize_utc(self, value):
        return value.isoformat() + 'Z'


class PetContext(StrictModel):
    observed_behavior: str
    behavior_duration_seconds: float = Field(ge=0)
    bark_detected: bool
    bark_count: int = Field(ge=0)
    bark_volume: float | None = Field(default=None, le=0)
    window_s: float = Field(gt=0)
    motion_model: Literal['rule', 'lstm_synthetic'] = 'rule'
    input_note: str = Field(default='', max_length=1000)
    lstm_metadata: dict[str, str | int] = Field(default_factory=dict)


class CareSuggestionDraft(StrictModel):
    state: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=2000)
    reasons: list[str] = Field(default_factory=list, max_length=10)
    recommended_actions: list[Literal['music']] = Field(default_factory=list, max_length=1)
    music_style: Literal['calm_piano', 'nature_sounds', 'white_noise'] | None = None
    severity: Literal['info', 'attention', 'warning', 'urgent'] = 'info'
    cited_observation_ids: list[int] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def valid_music(self):
        if self.recommended_actions and self.music_style is None:
            raise ValueError('music action requires a registered style')
        return self


class EvaluateRequest(StrictModel):
    observation_id: int = Field(gt=0)
    question: str = Field(default='최근 기록과 비교해서 어떤 케어가 필요할까요?', min_length=1, max_length=1000)


class ApproveRequest(StrictModel):
    action_type: Literal['music'] = 'music'


class ActionAckIn(StrictModel):
    status: Literal['acknowledged', 'completed', 'failed']
    detail: str | None = Field(default=None, max_length=1000)


class DemoRequest(StrictModel):
    scenario: Literal['calm', 'anxious', 'bored_pacing'] = 'anxious'
    pet_id: str = Field(default='demo-dog', min_length=1, max_length=80)
    outing_id: str | None = Field(default=None, min_length=1, max_length=80)
