"""Small hand-authored retrieval fixture, NOT a production-user accuracy estimate."""
import argparse
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from petmind.backend.main import analyze_demo
from petmind.backend.database import Base, FeedbackLog, ObservationLog
from petmind.backend.services import retrieval
from petmind.backend.services.embeddings import embed

# Distinct events and paraphrases; every question has a reviewed expected observation.
CASES = [
    ('현관 초인종이 울린 직후 짖음 후보가 발생했다.', '문 앞에서 벨 소리가 났을 때 반응은?'),
    ('천둥 소리를 들은 뒤 방 안에서 왕복 이동했다.', '폭풍 때 큰 소리가 났을 때 어떤 움직임이 있었어?'),
    ('청소기를 켠 뒤 거실을 벗어났다.', '진공 청소 기계가 작동하면 어떻게 반응했어?'),
    ('택배 기사 방문 뒤 짖음 후보가 반복됐다.', '배송하는 사람이 왔을 때 기록을 보여줘'),
    ('보호자가 외출한 뒤 문 앞에서 기다렸다.', '혼자 집에 남았을 때 문 근처에 있었나?'),
    ('보호자 귀가 후 주위를 빙빙 돌았다.', '주인이 돌아왔을 때 회전한 관찰은?'),
    ('공 장난감을 따라 뛰어갔다.', '볼을 가지고 놀 때 움직인 기록은?'),
    ('산책 후 침대에서 움직임이 적었다.', '밖에서 걷고 온 뒤 쉬었을 때 기록은?'),
    ('TV에서 개 짖는 소리가 난 뒤 고개를 들었다.', '텔레비전 속 강아지 소리에 반응한 적 있어?'),
    ('자동차 경적이 들린 뒤 창문으로 이동했다.', '차량이 빵 소리를 냈을 때 창가로 갔어?'),
    ('피아노 음악 재생 후 보호자가 짖음 감소를 보고했다.', '잔잔한 건반 음악을 듣고 보호자는 뭐라고 했어?'),
    ('자연 소리 재생 후 보호자는 변화가 없다고 남겼다.', '숲 소리 케어가 도움이 안 됐다는 의견이 있었어?'),
    ('동물병원 방문 뒤 집에서 오래 누워 있었다.', '진료를 받고 돌아온 날 쉬었던 기록은?'),
    ('미끄러운 바닥에서 발이 미끄러졌다.', '바닥 때문에 균형을 잃었던 관찰은?'),
    ('낯선 손님이 들어오자 침대 아래로 이동했다.', '방문객을 보고 숨은 곳이 있었나?'),
    ('로봇 청소기가 접근하자 뒤로 물러났다.', '자동으로 돌아다니는 청소 장치에 대한 반응은?'),
    ('엘리베이터 도착 알림이 난 뒤 현관으로 갔다.', '승강기 소리가 들리면 어디로 이동했어?'),
    ('창밖 고양이를 보고 창가에 머물렀다.', '밖에 다른 동물이 지나갈 때 창문 근처에 있었어?'),
    ('공사장에서 드릴 소리가 난 뒤 짖음 후보가 있었다.', '집 주변 작업장의 소음에 반응했나?'),
    ('불꽃놀이 소리를 들은 뒤 왕복 이동했다.', '폭죽이 터질 때 움직임에 대한 기록은?'),
]


def run(semantic=False):
    output = Path('artifacts/rag'); output.mkdir(parents=True, exist_ok=True)
    # In-memory evaluation database never changes live observations.
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    before = datetime(2026, 10, 11, 12)
    sessions = sessionmaker(engine)
    questions = [question for _, question in CASES]
    if semantic:
        embed(questions + ['화성 우주선의 연료 구성은?'], 'RETRIEVAL_QUERY')
    with sessions() as db:
        for i, (note, _) in enumerate(CASES):
            row = ObservationLog(pet_id='rag-eval', session_id=f'eval-{i}',
                                 observed_at=before-timedelta(hours=i+1), source='synthetic_demo',
                                 summary=f'평가용 관찰 {i+1}', context_json=json.dumps(analyze_demo('calm')))
            db.add(row); db.flush()
            db.add(FeedbackLog(observation_id=row.id, feedback_json=json.dumps({'note': note}, ensure_ascii=False),
                               created_at=before-timedelta(minutes=1)))
        db.commit()
        results = []
        for expected, question in enumerate(questions, 1):
            started = time.perf_counter()
            result = retrieval.search_result(db, 'rag-eval', before.isoformat(), question, semantic=semantic)
            ids = [row['id'] for row in result['records']]
            tokens = set(re.findall(r'[\w]+', question.lower()))
            baseline = sorted(range(1, len(CASES)+1), key=lambda i: (sum(t in f'평가용 관찰 {i} still quiet' for t in tokens), -i), reverse=True)[:5]
            results.append({'question': question, 'expected': expected, 'actual': ids, 'baseline': baseline,
                            'recall_at_5': int(expected in ids),
                            'reciprocal_rank': 1/(ids.index(expected)+1) if expected in ids else 0,
                            'baseline_recall_at_5': int(expected in baseline),
                            'latency_ms': round((time.perf_counter()-started)*1000, 2), 'search': result['search']})
        unrelated = retrieval.search_result(db, 'rag-eval', before.isoformat(), '화성 우주선의 연료 구성은?', semantic=semantic)
    report = {'fixture': '20 authored observation/guardian-note paraphrase pairs', 'semantic_enabled': semantic,
              'recall_at_5': sum(r['recall_at_5'] for r in results)/len(results),
              'mean_reciprocal_rank': sum(r['reciprocal_rank'] for r in results)/len(results),
              'baseline_recall_at_5': sum(r['baseline_recall_at_5'] for r in results)/len(results),
              'unrelated_query_ids': [r['id'] for r in unrelated['records']], 'results': results,
              'limitations': ['small authored fixture', 'not independent held-out user questions',
                              'threshold not calibrated on production data', 'answer factuality not scored']}
    path = output / ('evaluation_semantic.json' if semantic else 'evaluation_lexical.json')
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ['semantic_enabled', 'recall_at_5', 'mean_reciprocal_rank',
                                                 'baseline_recall_at_5', 'unrelated_query_ids']}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--semantic', action='store_true')
    run(parser.parse_args().semantic)
