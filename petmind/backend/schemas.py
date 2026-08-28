from datetime import datetime
from pydantic import BaseModel


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

    model_config = {"from_attributes": True}
