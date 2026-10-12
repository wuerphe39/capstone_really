"""Isolated API/MCP/Gemini smoke evaluation; creates only synthetic test records."""
import json
import os
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

root = Path(__file__).resolve().parents[1]
os.environ['PETMIND_DATABASE_URL'] = f"sqlite:///{(root/'artifacts/rag'/('live_'+uuid.uuid4().hex+'.db')).as_posix()}"
os.environ['PETMIND_LLM_PROVIDER'] = 'gemini'
os.environ['PETMIND_RETRIEVAL_MODE'] = 'mcp'
os.environ['PETMIND_SEMANTIC_SEARCH'] = 'on'

from petmind.backend.main import app  # noqa: E402


def run():
    pet='rag-isolated-fixture'
    wav=(root/'artifacts/datasets/esc50_demo/audio/5-203128-A-0.wav').read_bytes()
    from io import BytesIO
    import numpy as np
    import soundfile as sf
    silence=BytesIO()
    sf.write(silence, np.zeros(16000*5,dtype=np.float32),16000,format='WAV')
    cases=[]
    with TestClient(app) as client:
        def post(path,**kw):
            result=client.post(path,**kw)
            assert result.status_code < 300,(path,result.status_code,result.text[:300])
            return result.json()
        def create(audio,label,note):
            outing=post('/outings',json={'pet_id':pet,'input_mode':'uploaded_audio'})['id']
            clip=post('/audio-clips/upload',params={'pet_id':pet,'outing_id':outing,'store_consent':'true'},
                      content=audio,headers={'Content-Type':'audio/wav'})
            post(f"/audio-clips/{clip['id']}/review",json={'pet_id':pet,'label':label,'note':note})
            post(f'/outings/{outing}/end',params={'pet_id':pet})
            return outing,clip['observation_id']
        old,old_id=create(wav,'external_or_tv','실험용 가상 보호자: TV 소리로 확인')
        current,current_id=create(silence.getvalue(),'pet_vocalization','실험용 가상 보호자: 반려견 소리로 확인')
        for question in ('보호자가 TV라고 확인한 것은?', '이번 외출의 소리와 보호자 의견을 알려줘',
                         '지난 외출과 달라?', '내일 날씨는?'):
            result=post(f'/outings/{current}/explain',json={'pet_id':pet,'question':question})
            cases.append({'question':question,'provider':result['provider'],
                          'failure':result['failure'],
                          'retrieval_mode':result['retrieval_mode'],
                          'retrieval_failure':result['retrieval_failure'],
                          'selection_completed':result['selection_completed'],
                          'fact_ids':[c['id'] for c in result['claims']],
                          'cited_ids':sorted({i for c in result['claims'] for i in c['observation_ids']}),
                          'comparison_status':result['report']['comparison']['status'],
                          'answer':result['answer']})
        care=post('/care/evaluate',json={'observation_id':current_id,
            'question':'지난번 보호자가 TV 소리라고 확인한 기록과 비교해줘'})
        cases.append({'question':'RAG·케어: 이전 TV 확인 기록',
            'provider':care['provider'], 'failure':care['retrieval'].get('provider_failure'),
            'retrieval_mode':care['retrieval']['mode'],
            'retrieval_failure':care['retrieval'].get('error'),
            'selection_completed':None,
            'fact_ids':[], 'cited_ids':care['cited_observation_ids'],
            'comparison_status':None, 'answer':care['summary'],
            'search_method':care['retrieval'].get('search',{}).get('method'),
            'retrieved_records':[r['id'] for r in care['retrieval']['records']],
            'retrieved_reviews':[
                {'observation_id':r['id'], 'input_scope':r.get('input_scope'),
                 'labels':[v.get('label') for v in r['guardian_feedback']]}
                for r in care['retrieval']['records']]})
    report={'scope':'isolated synthetic fixture; no user records','old_observation_id':old_id,
            'current_observation_id':current_id,'cases':cases}
    assert cases[0]['cited_ids'] == [old_id] and 'TV·외부 소리' in cases[0]['answer']
    assert current_id not in cases[0]['cited_ids']
    assert cases[1]['provider'].startswith('gemini:') and current_id in cases[1]['cited_ids']
    assert cases[2]['comparison_status'] == 'sample_rate_comparison'
    assert cases[3]['fact_ids'] == [] and cases[3]['cited_ids'] == []
    assert cases[4]['retrieved_records'] == [old_id]
    assert cases[4]['retrieved_reviews'][0]['labels'] == ['external_or_tv']
    output=root/'artifacts/rag/current_live_result.json'
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'} | {'cases':[
        {k:v for k,v in c.items() if k!='answer'} for c in cases]},ensure_ascii=False))


if __name__=='__main__':
    run()
