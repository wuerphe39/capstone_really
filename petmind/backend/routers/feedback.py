import json
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field, model_validator
from sqlalchemy import select

from ..database import CareSuggestionLog, FeedbackLog, ObservationLog, get_db
from ..schemas import StrictModel

router = APIRouter(prefix='/feedback', tags=['guardian feedback'])


class FeedbackIn(StrictModel):
    observation_id: int = Field(gt=0)
    suggestion_id: int | None = Field(default=None, gt=0)
    bark_present: bool | None = None
    suggestion_appropriate: bool | None = None
    note: str = Field(default='', max_length=1000)
    source: Literal['guardian_feedback', 'synthetic_demo'] = 'guardian_feedback'

    @model_validator(mode='after')
    def not_empty(self):
        if self.bark_present is None and self.suggestion_appropriate is None and not self.note.strip():
            raise ValueError('at least one feedback field is required')
        if self.suggestion_appropriate is not None and self.suggestion_id is None:
            raise ValueError('suggestion feedback requires suggestion_id')
        return self


def to_out(row):
    return {'id': row.id, 'source': 'guardian_feedback',
            **json.loads(row.feedback_json), 'created_at': row.created_at.isoformat()+'Z'}


@router.post('', status_code=201)
def create_feedback(data: FeedbackIn, db=Depends(get_db)):
    observation = db.get(ObservationLog, data.observation_id)
    if observation is None:
        raise HTTPException(404, '관찰 기록을 찾을 수 없습니다.')
    if data.suggestion_id is not None:
        suggestion = db.get(CareSuggestionLog, data.suggestion_id)
        if suggestion is None or suggestion.observation_id != observation.id:
            raise HTTPException(422, '피드백의 관찰과 제안이 일치하지 않습니다.')
    row = FeedbackLog(observation_id=observation.id, suggestion_id=data.suggestion_id,
                      feedback_json=data.model_dump_json())
    db.add(row); db.commit(); db.refresh(row)
    return to_out(row)


@router.get('')
def list_feedback(pet_id: str, limit: int = Query(20, ge=1, le=100), db=Depends(get_db)):
    rows = db.scalars(select(FeedbackLog).join(ObservationLog).where(ObservationLog.pet_id == pet_id)
                      .order_by(FeedbackLog.created_at.desc()).limit(limit)).all()
    return [to_out(row) for row in rows]
