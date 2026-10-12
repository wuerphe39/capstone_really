import json
from datetime import timedelta
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from ..database import CareActionLog, CareSuggestionLog, ObservationLog, get_db

router = APIRouter(tags=['observation comparisons'])


@router.get('/care/actions/{command_id}/comparison')
def care_comparison(command_id: str, db=Depends(get_db)):
    action = db.scalars(select(CareActionLog).where(CareActionLog.command_id == command_id)).first()
    if action is None:
        raise HTTPException(404, '명령을 찾을 수 없습니다.')
    suggestion = db.get(CareSuggestionLog, action.suggestion_id)
    before = db.get(ObservationLog, suggestion.observation_id)
    before_context = json.loads(before.context_json)
    window = before_context['window_s']
    output = {'command_id': command_id, 'causality_established': False,
              'window_s': window, 'scope': 'live_windows' if before.source == 'live' else 'demo_windows',
              'status': 'insufficient_data', 'before_observation_id': before.id,
              'note': '같은 길이의 관찰 구간 변화이며 음악의 효과를 증명하지 않습니다.'}
    if action.status != 'completed':
        return output | {'reason': 'completed action required'}
    if before.observed_at > action.created_at:
        return output | {'reason': 'before observation ends after approval'}
    candidates = db.scalars(select(ObservationLog).where(
        ObservationLog.pet_id == before.pet_id, ObservationLog.source == before.source,
        ObservationLog.observed_at >= action.updated_at,
        ObservationLog.observed_at <= action.updated_at+timedelta(seconds=window*3+10)
    ).order_by(ObservationLog.observed_at)).all()
    for after in candidates:
        data = json.loads(after.context_json)
        if abs(data['window_s']-window) > .01:
            continue
        if after.observed_at-timedelta(seconds=window) < action.updated_at:
            continue
        return output | {'status': 'ok', 'after_observation_id': after.id,
                         'before_bark_candidates': before_context['bark']['count'],
                         'after_bark_candidates': data['bark']['count'],
                         'candidate_count_delta': data['bark']['count']-before_context['bark']['count'],
                         'before_motion': before_context['motion']['dominant'], 'after_motion': data['motion']['dominant']}
    return output | {'reason': 'no equal-length post-action window collected'}


@router.get('/pets/{pet_id}/baseline')
def baseline(pet_id: str, observation_id: int = Query(gt=0), db=Depends(get_db)):
    current = db.get(ObservationLog, observation_id)
    if current is None or current.pet_id != pet_id:
        raise HTTPException(404, '해당 반려견의 관찰을 찾을 수 없습니다.')
    output = {'pet_id': pet_id, 'observation_id': observation_id, 'status': 'insufficient_data',
              'days': 14, 'minimum_windows': 10, 'minimum_distinct_days': 3, 'timezone_offset_hours': 9}
    if current.source != 'live':
        return output | {'sample_count': 0, 'reason': '평소 패턴에는 실제 live 관찰만 사용합니다.'}
    rows = db.scalars(select(ObservationLog).where(
        ObservationLog.pet_id == pet_id, ObservationLog.source == 'live',
        ObservationLog.observed_at < current.observed_at,
        ObservationLog.observed_at >= current.observed_at-timedelta(days=14)
    ).order_by(ObservationLog.observed_at.desc()).limit(1000)).all()
    local = current.observed_at+timedelta(hours=9)
    same_hour = [row for row in rows if (row.observed_at+timedelta(hours=9)).hour == local.hour]
    day_count = len({(row.observed_at+timedelta(hours=9)).date() for row in same_hour})
    output |= {'sample_count': len(same_hour), 'distinct_days': day_count, 'local_hour': local.hour, 'bounded_to_latest': 1000}
    if len(same_hour) < 10 or day_count < 3:
        return output | {'reason': '동일 시간대의 실제 관찰 표본이 부족합니다.'}
    rates = [json.loads(row.context_json)['bark']['rate_per_min'] for row in same_hour]
    current_rate = json.loads(current.context_json)['bark']['rate_per_min']
    return output | {'status': 'ok', 'mean_candidate_rate_per_minute': mean(rates),
                     'current_candidate_rate_per_minute': current_rate, 'delta': current_rate-mean(rates),
                     'note': '짖음 후보 빈도 차이만 표시하며 정상·이상·질병으로 단정하지 않습니다.'}
