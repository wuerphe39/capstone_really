"""Pet-scoped temporal retrieval; no future records or current observation leakage."""
import json
import re
from datetime import datetime, timedelta, timezone

import numpy as np

from sqlalchemy import case, func, select

from ..database import AudioClipLog, CareActionLog, CareSuggestionLog, FeedbackLog, ObservationLog
from . import embeddings


def utc(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _query(pet_id, before, days, start=None):
    end = utc(before)
    if not 1 <= days <= 90:
        raise ValueError('days must be between 1 and 90')
    return select(ObservationLog).where(
        ObservationLog.pet_id == pet_id, ObservationLog.observed_at < end,
        ObservationLog.observed_at >= (utc(start) if start else end - timedelta(days=days))
    ).order_by(ObservationLog.observed_at.desc()).limit(1000)


def _rows(db, pet_id, before, days, start=None):
    return db.scalars(_query(pet_id, before, days, start)).all()


def search_result(db, pet_id, before, query, days=7, limit=5, start=None, semantic=False):
    if not 1 <= limit <= 5:
        raise ValueError('limit must be between 1 and 5')
    aliases = {'짖': ['bark', '짖'], '소음': ['bark', '소음'], '왕복': ['pacing', '왕복'],
               '빙빙': ['spinning', '회전'], '회전': ['spinning', '회전'],
               '움직': ['moving', '이동'], '가만': ['still', '정지'], '음악': ['music', '음악']}
    tokens = {token for token in re.findall(r'[\w]+', query.lower()) if len(token) >= 2}
    tokens -= {'최근', '기록', '기록을', '관찰', '돌봄', '알려줘', '어때', '오늘', '어제', '주세요', '필요한가요'}
    for stem, words in aliases.items():
        if stem in query:
            tokens.update(words)
    generic = not tokens or query.strip() in {'최근 기록과 비교해서 어떤 케어가 필요할까요?',
                                              '최근 돌봄이 필요한가요?', '최근 기록', '오늘 기록', '어제 기록'}
    scored = []
    for row in _rows(db, pet_id, before, days, start):
        data = json.loads(row.context_json)
        feedback = db.scalars(select(FeedbackLog).where(
            FeedbackLog.observation_id == row.id, FeedbackLog.created_at < utc(before)
        ).order_by(FeedbackLog.created_at.desc()).limit(2)).all()
        feedback_data = [json.loads(item.feedback_json) for item in feedback]
        audio = db.scalars(select(AudioClipLog).where(
            AudioClipLog.observation_id == row.id, AudioClipLog.pet_id == pet_id)).first()
        input_scope = row.source
        if audio:
            analysis = json.loads(audio.analysis_json)
            if analysis.get('demo_source'):
                input_scope = 'public_demo'
            review = json.loads(audio.review_json)
            reviewed_at = review.get('updated_at')
            if reviewed_at and utc(reviewed_at) < utc(before):
                feedback_data.append({'observation_id': row.id,
                    'label': review.get('label'), 'note': review.get('note', ''),
                    'source': review.get('source', 'guardian_opinion'),
                    'reviewed_at': reviewed_at})
        suggestions = db.scalars(select(CareSuggestionLog).where(
            CareSuggestionLog.observation_id == row.id, CareSuggestionLog.created_at < utc(before)
        ).order_by(CareSuggestionLog.created_at.desc()).limit(2)).all()
        care = []
        for suggestion in suggestions:
            action = db.scalars(select(CareActionLog).where(
                CareActionLog.suggestion_id == suggestion.id, CareActionLog.updated_at < utc(before))).first()
            care.append({'summary': suggestion.summary, 'status': 'historical_status_unavailable',
                         'actions': json.loads(suggestion.recommended_actions_json),
                         'action_status': action.status if action else None})
        # Include bark only when a candidate is present; zero-count records must not match bark questions.
        bark = (' bark 짖음 ' + data['bark']['level']) if data['bark']['count'] else ''
        summary = row.summary if data['bark']['count'] else re.sub(r'짖음 후보\s*0회,?\s*', '', row.summary)
        text = (summary + ' ' + data['motion']['dominant'] + bark + ' ' +
                json.dumps({'feedback': feedback_data, 'care': care}, ensure_ascii=False)).lower()
        score = sum(token in text for token in tokens)
        scored.append({'row': row, 'data': data, 'text': text, 'lexical': score,
                       'semantic': None, 'feedback': feedback_data, 'care': care,
                       'input_scope': input_scope})
    diagnostics = {'method': 'lexical', 'candidate_count': len(scored), 'semantic_candidate_limit': 100,
                   'recency_context_only': generic, 'semantic_threshold': .55}
    if generic:
        diagnostics['method'] = 'recent_context'
    if semantic and scored and not generic:
        try:
            subset = scored[:100]  # All pet/time filters are applied BEFORE embedding or ranking.
            vectors = embeddings.embed([item['text'] for item in subset], 'RETRIEVAL_DOCUMENT')
            query_vector = embeddings.embed([query], 'RETRIEVAL_QUERY')[0]
            similarities = vectors @ query_vector
            for item, similarity in zip(subset, similarities):
                item['semantic'] = float(similarity)
            diagnostics['method'] = 'hybrid_gemini_embedding_001'
        except Exception as exc:
            diagnostics.update(method='lexical_fallback', embedding_failure=type(exc).__name__)
    accepted = [item for item in scored if generic or item['lexical'] > 0 or
                (item['semantic'] is not None and item['semantic'] >= .55)]
    if generic:
        accepted.sort(key=lambda item: item['row'].observed_at, reverse=True)
    else:
        accepted.sort(key=lambda item: (min(item['lexical'], 4) / 4 + (item['semantic'] or 0),
                                        item['row'].observed_at), reverse=True)
    results = []
    for item in accepted[:limit]:
        row, data = item['row'], item['data']
        results.append({'id': row.id, 'pet_id': row.pet_id, 'observed_at': row.observed_at.isoformat() + 'Z',
                        'source': row.source, 'summary': row.summary, 'context': data,
                        'relevance': item['lexical'], 'semantic_similarity': item['semantic'],
                        'match_type': 'recent_context' if generic else 'topic_match',
                        'input_scope': item['input_scope'],
                        'guardian_feedback': item['feedback'], 'care_outcomes': item['care']})
    return {'records': results, 'search': diagnostics}


def search_observations(db, pet_id, before, query, days=7, limit=5, start=None, semantic=False):
    return search_result(db, pet_id, before, query, days, limit, start, semantic)['records']


def get_observation_stats(db, pet_id, before, days=7, start=None):
    records = _query(pet_id, before, days, start).subquery()
    count, candidates, seconds, synthetic = db.execute(select(
        func.count(), func.sum(func.json_extract(records.c.context_json, '$.bark.count')),
        func.sum(func.json_extract(records.c.context_json, '$.window_s')),
        func.sum(case((records.c.source == 'synthetic_demo', 1), else_=0))
    ).select_from(records)).one()
    candidates, seconds = candidates or 0, seconds or 0
    return {'pet_id': pet_id, 'days': days, 'sample_count': count,
            'bark_candidate_total': candidates, 'observed_seconds': seconds,
            'bark_candidates_per_minute': candidates * 60 / seconds if seconds else None,
            'synthetic_count': synthetic or 0,
            'bounded_to_latest': 1000}


def get_care_history(db, pet_id, before, limit=5, start=None):
    end = utc(before)
    if not 1 <= limit <= 5:
        raise ValueError('limit must be between 1 and 5')
    statement = select(CareSuggestionLog).join(ObservationLog).where(
        CareSuggestionLog.pet_id == pet_id, ObservationLog.observed_at < end, CareSuggestionLog.created_at < end
    )
    if start:
        statement = statement.where(ObservationLog.observed_at >= utc(start))
    rows = db.scalars(statement.order_by(CareSuggestionLog.created_at.desc()).limit(limit)).all()
    results = []
    for row in rows:
        action = db.scalars(select(CareActionLog).where(CareActionLog.suggestion_id == row.id,
                                                       CareActionLog.updated_at < end)).first()
        results.append({'suggestion_id': row.id, 'summary': row.summary,
                        'status': 'historical_status_unavailable', 'action_status': action.status if action else None})
    return results
