"""Opt-in real Gemini verification using ONLY generated synthetic facts.

No personal database or raw recording is read. Credentials stay in environment.
This verifies provider integration and citation preservation, not user accuracy.
"""
import json
from datetime import datetime, timezone
from pathlib import Path


def main():
    from petmind.backend.services.outings import explain_day, narrate, summary_facts
    from petmind.backend.settings import settings
    if settings.provider != 'gemini' or not settings.gemini_api_key:
        raise RuntimeError('Set GEMINI_API_KEY and PETMIND_LLM_PROVIDER=gemini locally')
    report = {'day': '2026-10-11', 'pet_id': 'synthetic-verification-only',
              'sample_seconds': 30, 'unknown_seconds': 12, 'bark_candidate_count': 3,
              'counted_observation_ids': [101, 102], 'moments': [
                  {'observation_id': 101, 'summary': '합성 관찰: 소리 후보 3회.',
                   'guardian_review': {'label': 'external_or_tv', 'note': '검증용 가상 보호자 의견: TV 소리로 생각함.'}},
                  {'observation_id': 102, 'summary': '합성 관찰: 영상 판단 불가 12초.', 'guardian_review': None}]}
    facts = summary_facts(report)
    cases = [
        ('session', '관찰 시간과 판단 불가 시간을 설명해 주세요.',
         lambda: narrate(report, facts, '관찰 시간과 판단 불가 시간을 설명해 주세요.')),
        ('day', '오늘 기록 요약과 보호자 의견을 알려주세요.',
         lambda: explain_day(report, '오늘 기록 요약과 보호자 의견을 알려주세요.')),
        ('guardian', '보호자 의견을 보여 주세요.',
         lambda: explain_day(report, '보호자 의견을 보여 주세요.')),
    ]
    results = []
    for name, question, action in cases:
        response = action()
        allowed = {f['id']: f for f in facts}
        # Day text has a date prefix rather than the session phrase.
        if name != 'session':
            allowed = {f['id']: f for f in summary_facts(report, '2026-10-11에 저장된')}
        claims = response['claims']
        checks = {
            'real_gemini': response['provider'].startswith('gemini:'),
            'no_fallback': response['failure'] is None,
            'nonempty': bool(claims),
            'canonical_text_and_citations': all(c == allowed.get(c['id']) for c in claims),
            'only_retrieved_ids': all(c['id'] in response['retrieved_fact_ids'] for c in claims),
            'answer_matches_claims': response['answer'] == '\n'.join(c['text'] for c in claims),
            'expected_topics': ({'current.samples', 'current.unknown'} <= {c['id'] for c in claims}
                                if name == 'session' else 'guardian.101' in {c['id'] for c in claims}),
        }
        results.append({'case': name, 'question': question, 'provider': response['provider'],
                        'failure': response['failure'], 'checks': checks, 'claims': claims})
        print(json.dumps({'case': name, 'checks': checks}), flush=True)
    evidence = {'tested_at': datetime.now(timezone.utc).isoformat(), 'model': settings.gemini_model,
                'source': 'generated synthetic facts only; no user database or raw audio transmitted',
                'results': results, 'passed': all(all(r['checks'].values()) for r in results),
                'limitations': ['three developer-authored integration cases, not independent user accuracy',
                                'local fact retrieval; MCP transport is verified separately']}
    Path('docs/evidence/outing_gemini_verification.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    if not evidence['passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
