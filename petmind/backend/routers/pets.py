from fastapi import APIRouter, Depends
from pydantic import Field

from ..database import PetProfileLog, get_db, utcnow
from ..schemas import StrictModel
from ..services.profiles import profile_out

router = APIRouter(prefix='/pets', tags=['pets'])


class ProfileIn(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    age_years: float | None = Field(default=None, ge=0, le=35)
    living_pattern: str = Field(default='', max_length=500)
    guardian_note: str = Field(default='', max_length=1000)


@router.get('/{pet_id}/profile')
def get_profile(pet_id: str, db=Depends(get_db)):
    return profile_out(db.get(PetProfileLog, pet_id))


@router.post('/{pet_id}/profile')
def save_profile(pet_id: str, data: ProfileIn, db=Depends(get_db)):
    row = db.get(PetProfileLog, pet_id)
    if row is None:
        row = PetProfileLog(pet_id=pet_id, profile_json=data.model_dump_json())
        db.add(row)
    else:
        row.profile_json = data.model_dump_json()
        row.updated_at = utcnow()
    db.commit()
    db.refresh(row)
    return profile_out(row)
