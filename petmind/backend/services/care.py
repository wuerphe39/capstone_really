"""Legacy approval/history flow adapted to observations and virtual device polling."""
import asyncio
import json
import re
import uuid
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..database import AudioClipLog, CareActionLog, CareSuggestionLog, ObservationLog, PetProfileLog, utcnow
from ..mcp_client import retrieve_records
from ..providers import RuleBasedProvider, get_provider
from ..schemas import CareSuggestionDraft
from ..settings import settings
from .observations import care_context
from . import retrieval
from .profiles import profile_out
from .frequency import compare_candidate_frequency
from .query_plan import plan_query


def suggestion_to_out(row):
    retrieval = json.loads(row.retrieval_json)
    return {'id': row.id, 'pet_id': row.pet_id, 'observation_id': row.observation_id,
            'state': row.state, 'summary': row.summary, 'reasons': json.loads(row.reasons_json),
            'recommended_actions': json.loads(row.recommended_actions_json), 'music_style': row.music_style,
            'severity': row.severity, 'status': row.status, 'provider': row.provider,
            'context': json.loads(row.context_json), 'retrieval': retrieval,
            'care_steps': retrieval.get('care_steps', []),
            'cited_observation_ids': json.loads(row.cited_ids_json), 'question': row.question,
            'created_at': row.created_at.isoformat() + 'Z'}


def action_to_out(row):
    return {'id': row.id, 'suggestion_id': row.suggestion_id, 'action_type': row.action_type,
            'command_id': row.command_id, 'status': row.status, 'request': json.loads(row.request_json),
            'result': json.loads(row.result_json) if row.result_json else None, 'error': row.error,
            'created_at': row.created_at.isoformat() + 'Z', 'updated_at': row.updated_at.isoformat() + 'Z'}


def current_audio_evidence(db, observation_id):
    """Expose only measured audio metadata and the review label to care RAG."""
    clip = db.scalars(select(AudioClipLog).where(AudioClipLog.observation_id == observation_id)).first()
    if clip is None:
        return None
    analysis = json.loads(clip.analysis_json)
    model = analysis.get('audio_model') or analysis.get('audio_lstm') or {}
    windows = model.get('windows') or []
    review = json.loads(clip.review_json or '{}')
    return {'observation_id': observation_id,
            'input_scope': analysis.get('input_scope', 'unknown'),
            'analyzed_windows': len(windows),
            'dog_candidate_windows': sum(w.get('label') == 'dog_candidate' for w in windows),
            'dog_score': model.get('dog_score'),
            'threshold': model.get('threshold'),
            'model_role': model.get('model_role'),
            'model_name': model.get('model_name', 'LSTM'),
            'review_label': review.get('label'),
            'review_source': review.get('source')}


def care_draft_matches_current_audio(draft, audio):
    if not audio or not audio['analyzed_windows']:
        return True
    if re.search(r'(?:음성\s*)?(?:LSTM|YAMNet)(?:\s*분석)?\s*창\s*(?:수)?(?:는|가|은)?\s*0\s*개', draft.summary, re.I):
        return False
    if audio['dog_candidate_windows'] == 0 and audio['review_label'] in {'other', 'external_or_tv'}:
        summary = draft.summary
        expected = ('기타 소리', '다른 소리', 'TV', '외부 소리')
        contradicted = ('다르', '불일치', '의견이 불확실', '의견은 불확실', '의견이 판단 어려움')
        return any(term in summary for term in expected) and not any(term in summary for term in contradicted)
    return True


def care_steps(context, evidence):
    """Concrete checks derived from the current observation and human review.

    These are conditional care options, not inferred behavior or treatment claims.
    """
    audio = evidence.get('current_audio') or {}
    if audio.get('analyzed_windows'):
        label = audio.get('review_label')
        candidates = audio.get('dog_candidate_windows', 0)
        if label == 'external_or_tv':
            return ['TV·외부 소리라는 확인 의견이 맞는지 원본을 다시 듣고 소리의 출처를 기록해 주세요.',
                    '같은 소리에 반복해서 반응하는지 확인하고, 필요하면 TV 음량이나 창가·현관의 자극을 줄여 보세요.']
        if label == 'other':
            return ['원본에서 어떤 소리인지 적고, 다음 외출에도 같은 소리가 나타나는지 비교해 주세요.',
                    '이번 자료만으로 반려견 행동 변화나 음악의 필요성을 판단하지 마세요.']
        if not candidates:
            return ['모델이 짖음 후보로 표시하지 않은 구간도 원본을 들어 놓친 소리가 있는지 확인해 주세요.',
                    '반려견 소리로 확인되면 그 시각의 주변 자극과 실제 반려견 모습을 기록해 주세요.']
        steps = ['후보 구간의 원본 소리와 연결된 영상이 있다면 전후 장면을 확인해 주세요.',
                 '실제 짖음으로 확인되면 현관·창가·TV 등 당시의 자극과 반려견 반응을 기록하고, 반복되는 자극을 줄여 보세요.']
        if label == 'pet_vocalization':
            steps.append('보호자가 원하면 낮은 음량의 잔잔한 음악을 짧게 시험하고, 재생 전후 반응을 기록해 주세요. 음악은 짖음의 원인 해결이나 치료로 간주하지 않습니다.')
        else:
            steps.append('소리 종류가 아직 불확실합니다. 반려견의 짖음으로 확인되고 편안한 환경을 원할 때만 잔잔한 음악을 선택적으로 시험해 보세요.')
        return steps
    if context.observed_behavior in {'spinning', 'pacing', 'sit_stand_repeat'}:
        return ['반복 움직임이 보인 원본과 전후 상황을 확인하고, 소음·방문·활동 부족 같은 가능한 자극을 기록해 주세요.',
                '같은 상황이 반복되면 조용한 공간과 짧은 놀이·휴식 시간을 마련하고 변화를 비교해 주세요.']
    return ['관찰 원본과 당시 주변 상황을 확인하고, 다음 기록에서도 같은 신호가 반복되는지 비교해 주세요.']


def evaluate(db, observation_id, question):
    observation = db.get(ObservationLog, observation_id)
    if observation is None:
        raise HTTPException(404, '관찰 기록을 찾을 수 없습니다.')
    context = care_context(observation)
    before = observation.observed_at.isoformat()
    query = question
    plan = plan_query(question, before)
    before = plan['before']
    if settings.retrieval_mode == 'mcp':
        try:
            evidence = asyncio.run(retrieve_records(observation.pet_id, before, query, plan['days'],
                                                   plan['start'], settings.semantic_enabled))
        except Exception:
            evidence = {'mode': 'mcp', 'status': 'failed', 'records': [], 'stats': {},
                        'care_history': [], 'tool_calls': [], 'error': 'MCP 기록 조회 실패'}
    else:
        search = retrieval.search_result(db, observation.pet_id, before, query, plan['days'],
                                         start=plan['start'], semantic=settings.semantic_enabled)
        evidence = {'mode': 'local', 'status': 'ok', **search,
                    'stats': retrieval.get_observation_stats(db, observation.pet_id, before, plan['days'], plan['start']),
                    'care_history': retrieval.get_care_history(db, observation.pet_id, before, start=plan['start']),
                    'tool_calls': []}
    evidence['query_plan'] = plan
    evidence['current_observation_id'] = observation.id
    evidence['current_audio'] = current_audio_evidence(db, observation.id)
    evidence['profile'] = profile_out(db.get(PetProfileLog, observation.pet_id))
    evidence['frequency_comparison'] = compare_candidate_frequency(context, evidence)
    current_audio = evidence['current_audio']
    evidence['care_steps'] = care_steps(context, evidence)
    provider = get_provider()
    provider_name = provider.name
    provider_stage = 'generate'
    try:
        draft = CareSuggestionDraft.model_validate(provider.suggest(context, evidence, question))
        provider_stage = 'citation_validation'
        allowed_citations = {observation.id, *(r['id'] for r in evidence['records'])}
        if not set(draft.cited_observation_ids).issubset(allowed_citations):
            raise ValueError('provider cited a record outside current or retrieved evidence')
        provider_stage = 'audio_consistency_validation'
        if not care_draft_matches_current_audio(draft, current_audio):
            raise ValueError('provider contradicted current audio review')
    except Exception as exc:
        provider_name = 'rule-fallback'
        response = getattr(exc, 'response', None)
        evidence['provider_failure'] = {'type': type(exc).__name__, 'stage': provider_stage,
                                       'http_status': response.status_code if response is not None else None}
        if hasattr(exc, 'errors'):
            evidence['provider_failure']['field_errors'] = [
                {'field': '.'.join(map(str, error['loc'])), 'code': error['type']}
                for error in exc.errors()]
        draft = RuleBasedProvider().suggest(context, evidence, question)
    if current_audio and current_audio['analyzed_windows']:
        model_reason = (f"현재 {current_audio['model_name']} 분석 창 {current_audio['analyzed_windows']}개 중 개 짖음 소리 후보 "
                        f"{current_audio['dog_candidate_windows']}개입니다. 5초 창은 정확한 짖음 횟수가 아닙니다.")
        review_labels = {'pet_vocalization': '반려견 소리', 'external_or_tv': 'TV·외부 소리',
                         'other': '기타 소리', 'uncertain': '판단 어려움'}
        source = ('시연 담당자' if current_audio['input_scope'] == 'public_demo' or
                  current_audio['review_source'] == 'demo_operator_opinion' else '보호자')
        review_reason = (f"{source} 확인 의견: {review_labels.get(current_audio['review_label'], '미확인')}. "
                         '모델 정답이나 즉시 재학습 결과가 아닙니다.')
        draft = draft.model_copy(update={'reasons': [model_reason, review_reason, *draft.reasons][:10]})
        music_eligible = (current_audio['dog_candidate_windows'] > 0 and
                          current_audio['review_label'] == 'pet_vocalization')
        if music_eligible:
            summary = draft.summary
            if '음악' not in summary:
                summary += ' 보호자가 원하면 잔잔한 음악을 짧게 시험하고 전후 반응을 기록할 수 있습니다.'
            draft = draft.model_copy(update={'summary': summary,
                                             'recommended_actions': ['music'],
                                             'music_style': 'calm_piano',
                                             'state': 'care_option'})
        elif draft.recommended_actions:
            draft = draft.model_copy(update={'recommended_actions': [], 'music_style': None,
                                             'state': 'insufficient_observation'})
    row = CareSuggestionLog(observation_id=observation.id, pet_id=observation.pet_id,
                            state=draft.state, summary=draft.summary,
                            reasons_json=json.dumps(draft.reasons, ensure_ascii=False),
                            recommended_actions_json=json.dumps(draft.recommended_actions),
                            music_style=draft.music_style, severity=draft.severity,
                            status='pending' if draft.recommended_actions else 'informational',
                            provider=provider_name, context_json=context.model_dump_json(),
                            retrieval_json=json.dumps(evidence, ensure_ascii=False),
                            cited_ids_json=json.dumps(draft.cited_observation_ids), question=question)
    db.add(row)
    db.commit()
    db.refresh(row)
    return suggestion_to_out(row)


def approve(db, suggestion_id, action_type):
    row = db.get(CareSuggestionLog, suggestion_id)
    if row is None:
        raise HTTPException(404, '케어 제안을 찾을 수 없습니다.')
    if action_type not in json.loads(row.recommended_actions_json):
        raise HTTPException(422, '제안에 허용되지 않은 액션입니다.')
    changed = db.execute(update(CareSuggestionLog).where(
        CareSuggestionLog.id == suggestion_id, CareSuggestionLog.status == 'pending'
    ).values(status='approved')).rowcount
    if not changed:
        db.rollback()
        raise HTTPException(409, '이미 승인 또는 거절된 제안입니다.')
    action = CareActionLog(suggestion_id=suggestion_id, command_id=str(uuid.uuid4()),
                          request_json=json.dumps({'style': row.music_style, 'mode': 'simulated'}))
    db.add(action)
    try:
        db.commit()  # Persist before the virtual agent can receive a command.
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '이미 요청된 액션입니다.')
    db.refresh(action)
    return action_to_out(action)


def dismiss(db, suggestion_id):
    row = db.get(CareSuggestionLog, suggestion_id)
    if row is None:
        raise HTTPException(404, '케어 제안을 찾을 수 없습니다.')
    changed = db.execute(update(CareSuggestionLog).where(
        CareSuggestionLog.id == suggestion_id, CareSuggestionLog.status == 'pending'
    ).values(status='dismissed')).rowcount
    if not changed:
        db.rollback()
        raise HTTPException(409, '대기 중인 제안만 거절할 수 있습니다.')
    db.commit()
    db.refresh(row)
    return suggestion_to_out(row)


def expire_stale_actions(db):
    deadline = utcnow() - timedelta(seconds=settings.action_timeout_seconds)
    db.execute(update(CareActionLog).where(
        CareActionLog.status.in_(['requested', 'acknowledged']), CareActionLog.created_at < deadline
    ).values(status='timed_out', error='가상 장치 완료 응답 시간 초과', updated_at=utcnow()))
    db.commit()


def acknowledge(db, command_id, status, detail):
    expire_stale_actions(db)
    row = db.scalars(select(CareActionLog).where(CareActionLog.command_id == command_id)).first()
    if row is None:
        raise HTTPException(404, '명령을 찾을 수 없습니다.')
    if row.status == status:
        return action_to_out(row)
    predecessors = ['requested'] if status == 'acknowledged' else ['acknowledged']
    changed = db.execute(update(CareActionLog).where(
        CareActionLog.id == row.id, CareActionLog.status.in_(predecessors)
    ).values(status=status, updated_at=utcnow(), error=detail if status == 'failed' else None,
             result_json=json.dumps({'simulated': True, 'detail': detail}, ensure_ascii=False))).rowcount
    if not changed:
        db.rollback()
        raise HTTPException(409, '현재 상태에서 해당 응답으로 변경할 수 없습니다.')
    db.commit()
    db.refresh(row)
    return action_to_out(row)
