"""Deterministic scoped fact ranking; guardian notes remain evidence, never commands."""
import re
import unicodedata
from collections import deque

INTENTS = {
    'scene_note': ('초인종', '노크', '방문', '방문자', '벨소리'),
    'video': ('영상', '장면', '녹화', '사건'),
    'provenance': ('공개', '시연', '합성', '출처', '데이터셋'),
    'comparison': ('비교', '지난', '이전', '차이', '늘었', '줄었', '전보다'),
    'guardian_opinion': ('보호자', '의견', '메모', '확인한', '확인했', '사용자', 'tv', '텔레비전', '외부 소리'),
    'audio_lstm': ('lstm', '모델 점수', '감지 창', '개 소리 후보', '개 짖음 소리 후보', '짖음 후보'),
    'bark': ('짖', '소리', '소음', '발성'),
    'quality': ('판단', 'unknown', '추적', '불확실', '누락', '분석 안', '구분하지 못', '알 수 없', '불분명', '인식 못'),
    'summary': ('요약', '외출', '관찰', '오늘', '귀가', '정리', '기록'),
}


def asks_sample_duration(question):
    question = ' '.join(unicodedata.normalize('NFKC', question).lower().split())
    return bool(re.search(r'(분석|녹음|저장|표본).{0,15}(분량|몇\s*(초|분)|얼마|길이|총\s*시간)', question)
                or re.search(r'얼마나\s*오래\s*(봤|보았|관찰|분석|녹음|기록)', question))


def question_intents(question):
    question = ' '.join(unicodedata.normalize('NFKC', question).lower().split())
    requested = [kind for kind, terms in INTENTS.items() if any(t in question for t in terms)]
    if ('guardian_opinion' in requested and 'bark' in requested and
            any(term in question for term in ('tv', '텔레비전', '티비')) and
            '확인' in question and not any(term in question for term in ('후보', '횟수', '몇 번'))):
        # "TV 소리라고 확인" asks for the review, not the model's bark count.
        requested.remove('bark')
    if asks_sample_duration(question):
        requested.append('summary')
    return list(dict.fromkeys(requested))


def select_facts(facts, question, limit=8):
    """Reserve a slot per requested evidence kind before filling recent details.

    Matching is over the user's question, not instructions in guardian notes.
    All input facts must already have passed pet/session scoping.
    """
    if limit < 1:
        return []
    requested = question_intents(question)
    if not requested:
        return []
    normalized_question = unicodedata.normalize('NFKC', question).lower()
    if '보호자' in normalized_question:
        facts = [fact for fact in facts if fact['kind'] != 'guardian_opinion' or
                 fact.get('review_source', 'guardian_opinion') == 'guardian_opinion']
    if any(term in normalized_question for term in ('tv', '텔레비전', '티비')):
        facts = [fact for fact in facts if fact['kind'] != 'guardian_opinion' or
                 fact.get('review_label') in (None, 'external_or_tv')]
    kinds = list(requested)
    if 'summary' in kinds:
        kinds += (['provenance', 'quality'] if asks_sample_duration(question) and
                  set(requested) == {'summary'} else
                  ['provenance', 'quality', 'bark', 'audio_lstm', 'guardian_opinion', 'observation'])
    if 'bark' in kinds:
        # A sound count must not conceal missing/undecidable observation time.
        kinds += ['audio_lstm', 'provenance', 'quality', 'guardian_opinion', 'observation']
    if 'comparison' in kinds:
        kinds += ['summary', 'provenance', 'quality']
    if 'video' in kinds:
        kinds += ['provenance', 'quality', 'guardian_opinion']
    kinds = list(dict.fromkeys(kinds))
    buckets = {kind: [f for f in facts if f['kind'] == kind] for kind in kinds}
    # Facts are built in observation-ID order, so prefer recent details.
    for kind in ('guardian_opinion', 'observation', 'video'):
        if kind in buckets:
            # Current session facts precede prior-session facts. Both groups
            # are newest-last, so reverse within each group only.
            if kind == 'guardian_opinion':
                current = [f for f in buckets[kind] if not f['id'].startswith('previous.')]
                earlier = [f for f in buckets[kind] if f['id'].startswith('previous.')]
                buckets[kind] = list(reversed(current)) + earlier
            else:
                buckets[kind].reverse()
    buckets = {kind: deque(values) for kind, values in buckets.items()}
    result, seen = [], set()
    while len(result) < limit:
        added = False
        for kind in kinds:
            while buckets[kind] and buckets[kind][0]['id'] in seen:
                buckets[kind].popleft()
            if buckets[kind] and len(result) < limit:
                fact = buckets[kind].popleft()
                result.append(fact)
                seen.add(fact['id'])
                added = True
        if not added:
            break
    return result
