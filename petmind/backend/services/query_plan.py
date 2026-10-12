"""Deterministic Korean date/intent planning; bounds are stored as naive UTC."""
import re
from datetime import datetime, timedelta, timezone


def plan_query(question, before):
    end = datetime.fromisoformat(before.replace('Z', '+00:00'))
    end = end.replace(tzinfo=timezone.utc) if end.tzinfo is None else end.astimezone(timezone.utc)
    local = end.astimezone(timezone(timedelta(hours=9)))
    midnight = local.replace(hour=0, minute=0, second=0, microsecond=0)
    days, label = 7, 'recent_7_days'
    match = re.search(r'(\d+)\s*(일|주|개월)', question)
    if match:
        days = max(1, min(90, int(match[1]) * {'일': 1, '주': 7, '개월': 30}[match[2]]))
        label = f'recent_{days}_days'
    start = end - timedelta(days=days)
    if '어제' in question:
        start, end, label = midnight - timedelta(days=1), midnight, 'yesterday_kst'
    elif '오늘' in question:
        start, label = midnight, 'today_kst'
    if label in {'today_kst', 'yesterday_kst'}:
        hours = next(((name, lo, hi) for name, lo, hi in [('새벽', 0, 6), ('오전', 0, 12),
                                                       ('오후', 12, 18), ('밤', 18, 24)] if name in question), None)
        if hours:
            name, lo, hi = hours
            day_start = start
            start = day_start + timedelta(hours=lo)
            end = min(end, day_start + timedelta(hours=hi))
            label += f'_{name}'
    intent = 'care_outcome' if any(w in question for w in ['음악', '조치', '효과', '도움', '완료']) else 'observation'
    if any(w in question for w in ['빈도', '몇 번', '늘었', '증가', '평균']):
        intent = 'frequency'
    return {'start': start.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
            'before': end.astimezone(timezone.utc).replace(tzinfo=None).isoformat(),
            'days': days, 'period': label, 'timezone': 'Asia/Seoul', 'intent': intent}
