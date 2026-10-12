"""Seed a disposable localhost outing with public-bark / AI-TTS demonstration audio."""
import hashlib
import json
from pathlib import Path

import requests

BASE='http://127.0.0.1:8012'
ROOT=Path('artifacts/ai_sound_demo_20261012')
PET='demo-dog'


def request(method,path,**kwargs):
    r=requests.request(method,BASE+path,timeout=60,**kwargs)
    r.raise_for_status()
    return r.json()


def main():
    health=request('GET','/health')['components']
    if not health['audio_lstm_checkpoint_present'] or health['audio_lstm_model_role']!='experimental':
        raise RuntimeError('Expected isolated experimental checkpoint')
    if request('GET','/outings',params={'pet_id':PET}):
        raise RuntimeError('Use a fresh disposable demo database')
    outing=request('POST','/outings',json={'pet_id':PET,'input_mode':'uploaded_audio',
                                           'title':'AI 생성 말소리·공개 짖음 임시 시연'})
    definitions=[
        ('bark_tts_0.2.wav','AI TTS 말소리 + FSD50K #15791 짖음 · 합성 시연',
         'pet_vocalization','공개 짖음 원본과 AI 생성 말소리를 섞었습니다. 시연 담당자의 음원 확인 의견입니다.'),
        ('bark_tts_0.4.wav','AI TTS 말소리 + FSD50K #15791 짖음 · 큰 말소리 · 합성 시연',
         'uncertain','같은 짖음 원본이지만 말소리가 커졌습니다. LSTM 놓침 사례이며 실제 보호자 확인이 아닙니다.'),
        ('tts_only.wav','AI TTS 말소리만 있음 · 짖음 없음 · 합성 시연',
         'other','AI 생성 말소리만 있는 대조 자료입니다. 시연 담당자의 확인 의견입니다.'),
    ]
    records=[]
    for filename,source,label,note in definitions:
        content=(ROOT/filename).read_bytes()
        clip=request('POST','/audio-clips/upload',
            params={'pet_id':PET,'store_consent':'true','training_consent':'false',
                    'outing_id':outing['id'],'demo_source':source},
            data=content,headers={'Content-Type':'audio/wav'})
        clip=request('POST',f'/audio-clips/{clip["id"]}/review',
                     json={'pet_id':PET,'label':label,'note':note})
        model=clip['analysis']['audio_lstm']
        if model['model_role']!='experimental' or model['checkpoint_name']!='household_bark_candidate.pt':
            raise RuntimeError('Recorded model provenance differs from intended experimental model')
        records.append({'filename':filename,'sha256':hashlib.sha256(content).hexdigest(),
                        'clip_id':clip['id'],'observation_id':clip['observation_id'],
                        'score':model['dog_score'],'threshold':model['threshold'],
                        'detected':model['dog_score']>=model['threshold'],
                        'review_source':clip['review']['source'],'source_note':clip['source_note']})
    output={'outing_id':outing['id'],'pet_id':PET,'origin':'AI-generated speech plus FSD50K public bark',
            'input_method':'API preload into isolated DB; subsequent interactions recorded in actual web UI',
            'records':records}
    (ROOT/'ui_seed_results.json').write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(output,ensure_ascii=False))


if __name__=='__main__':main()
