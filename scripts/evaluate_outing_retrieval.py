"""Fixed developer-authored retrieval regression set, not user/Gemini accuracy.

Baseline is the pre-change ordered keyword filter copied verbatim in behavior.
No tuning of thresholds or generation occurs in this evaluation.
"""
import hashlib
import argparse
import json
from pathlib import Path

from petmind.backend.services.outing_retrieval import select_facts

CASES = Path('tests/fixtures/outing_retrieval_questions.json')


def baseline(facts, question):
    lowered = question.lower()
    if any(term in lowered for term in ('비교', '지난', '이전', '차이')):
        wanted = {'comparison', 'summary', 'quality'}
    elif any(term in lowered for term in ('보호자', '의견', '메모')):
        wanted = {'guardian_opinion'}
    elif any(term in lowered for term in ('짖', '소리', '소음')):
        wanted = {'bark', 'observation', 'guardian_opinion'}
    elif any(term in lowered for term in ('판단', 'unknown', '추적')):
        wanted = {'quality'}
    elif any(term in lowered for term in ('요약', '외출', '관찰', '오늘', '귀가')):
        wanted = {'summary', 'quality', 'bark', 'observation', 'guardian_opinion'}
    else:
        wanted = set()
    return [f for f in facts if f['kind'] in wanted][:8]


def fixture():
    facts = [
        {'id': 'current.samples', 'kind': 'summary', 'text': '분석 표본은 100초입니다.', 'observation_ids': list(range(1, 21))},
        {'id': 'current.unknown', 'kind': 'quality', 'text': '영상 판단 불가는 100초입니다.', 'observation_ids': list(range(1, 21))},
        {'id': 'current.bark', 'kind': 'bark', 'text': '짖음 후보는 4회입니다.', 'observation_ids': list(range(1, 21))},
    ]
    for i in range(1, 21):
        facts.append({'id': f'observation.{i}', 'kind': 'observation', 'text': f'관찰 #{i}', 'observation_ids': [i]})
        facts.append({'id': f'guardian.{i}', 'kind': 'guardian_opinion',
                      'text': f'보호자 의견 #{i}: TV 소리로 생각합니다.', 'observation_ids': [i]})
    facts.append({'id': 'comparison.bark_rate', 'kind': 'comparison',
                  'text': '이번 분당 2.4회, 이전 분당 1.2회. 케어 효과는 아닙니다.', 'observation_ids': [1, 21]})
    return facts


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--questions', type=Path, default=CASES)
    parser.add_argument('--output', type=Path, default=Path('docs/evidence/outing_retrieval_comparison.json'))
    args = parser.parse_args()
    cases = json.loads(args.questions.read_text(encoding='utf-8'))
    results = {}
    for name, retrieve in (('previous_ordered_filter', baseline), ('intent_balanced_recent', select_facts)):
        rows = []
        for case in cases:
            facts = [] if case.get('empty') else fixture()
            selected = retrieve(facts, case['question'])
            ids = {f['id'] for f in selected}
            expected = set(case['required'])
            passed = expected <= ids if expected else not ids
            grounded = all(f in facts for f in selected) and len(ids) == len(selected) <= 8
            rows.append({**case, 'retrieved': [f['id'] for f in selected], 'passed': passed,
                         'canonical_facts_unchanged': grounded,
                         'required_recall': len(ids & expected)/len(expected) if expected else None})
        results[name] = {'passed': sum(r['passed'] for r in rows), 'total': len(rows),
                         'canonical_fact_checks_passed': sum(r['canonical_facts_unchanged'] for r in rows),
                         'cases': rows}
    implementation = Path('petmind/backend/services/outing_retrieval.py')
    result = {'question_sha256': hashlib.sha256(args.questions.read_bytes()).hexdigest(),
              'implementation_sha256': hashlib.sha256(implementation.read_bytes()).hexdigest(), 'results': results,
              'scope': 'developer-authored fixed synthetic retrieval regression; 20 observations',
              'limitations': ['not independent user questions or a claim of general RAG accuracy',
                              'does not evaluate Gemini, MCP transport or database isolation',
                              'database scoping and invalid generation fallback have separate API tests']}
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: {'passed': v['passed'], 'total': v['total']} for k, v in results.items()}))


if __name__ == '__main__':
    main()
