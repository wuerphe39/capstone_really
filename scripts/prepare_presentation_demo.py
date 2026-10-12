"""Populate the isolated localhost presentation DB with clearly marked public audio.

Requires the API to be started with a disposable PETMIND_DATABASE_URL under artifacts/.
Only ESC-50 demo clips and public-dataset provenance are sent to localhost.
Run after completing a first browser outing with 5-203128-A-0.wav.
"""
import argparse
import hashlib
import json
from pathlib import Path

import requests

ROOT = Path('artifacts/datasets/esc50_demo/audio')
BASE = 'http://127.0.0.1:8010'
PET = 'demo-dog'
EVIDENCE = Path('artifacts/presentation_20261011/demo_api.json')


def call(method, path, **kwargs):
    response = requests.request(method, BASE+path, timeout=90, **kwargs)
    response.raise_for_status()
    return response.json()


def review(clip, label, note):
    return call('POST', f'/audio-clips/{clip["id"]}/review',
                json={'pet_id': PET, 'label': label, 'note': note})


def upload(outing, filename):
    content = (ROOT/filename).read_bytes()
    result = call('POST', '/audio-clips/upload', params={'pet_id': PET,
        'store_consent': 'true', 'training_consent': 'false', 'outing_id': outing,
        'demo_source': f'ESC-50 / {filename}'}, data=content,
        headers={'Content-Type': 'audio/wav'})
    return result, hashlib.sha256(content).hexdigest()


def model_finding(clip):
    """Keep this run's score separate from the dataset label and operator opinion."""
    model = clip['analysis'].get('audio_lstm') or {}
    score, threshold = model.get('dog_score'), model.get('threshold')
    if score is None or threshold is None:
        status = 'unavailable'
    else:
        status = 'below_threshold' if score < threshold else 'at_or_above_threshold'
    return {'status': status, 'dog_score': score, 'threshold': threshold}


def dog_review_note(clip):
    """Describe this run's model result without turning the dataset label into a verdict."""
    status = model_finding(clip)['status']
    if status == 'below_threshold':
        finding = '이번 실행의 실험 LSTM 점수가 기준값에 못 미쳤습니다.'
    elif status == 'at_or_above_threshold':
        finding = '이번 실행의 실험 LSTM 점수가 기준값 이상입니다.'
    else:
        finding = '현재 모델 결과가 없어 놓침 여부는 확인할 수 없습니다.'
    return f'ESC-50 Dog 라벨 공개 음원입니다. {finding} 실제 보호자 확인은 아닙니다.'


def main():
    global ROOT, BASE, PET, EVIDENCE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio-dir', type=Path, default=ROOT)
    parser.add_argument('--base', default=BASE)
    parser.add_argument('--pet-id', default=PET)
    parser.add_argument('--output', type=Path, default=EVIDENCE)
    args = parser.parse_args()
    ROOT, BASE, PET, EVIDENCE = args.audio_dir, args.base.rstrip('/'), args.pet_id, args.output
    if not all((ROOT/name).is_file() for name in
               ('5-203128-A-0.wav', '5-208030-A-0.wav', '5-181766-A-10.wav')):
        raise FileNotFoundError('Run python -m scripts.prepare_demo_audio first')
    outings = call('GET', '/outings', params={'pet_id': PET})
    if len(outings) not in (1, 2) or any(o['status'] != 'ended' for o in outings):
        raise RuntimeError('Expected one or two completed outings in the isolated DB')
    clips = call('GET', '/audio-clips', params={'pet_id': PET})
    by_source = {c['analysis'].get('demo_source'): c for c in clips}
    if 'ESC-50 / 5-203128-A-0.wav' not in by_source:
        raise RuntimeError('Expected the browser-uploaded public Dog example')
    first = review(by_source['ESC-50 / 5-203128-A-0.wav'], 'uncertain',
                   '공개 ESC-50 Dog 라벨 음원입니다. 시연 담당자의 메모이며 실제 보호자 확인은 아닙니다.')
    if len(outings) == 1:
        session = call('POST', '/outings', json={'pet_id': PET, 'input_mode': 'uploaded_audio',
                                                'title': '공개 음원 검증 시연 2'})
        dog_second, dog_second_hash = upload(session['id'], '5-208030-A-0.wav')
        dog_second = review(dog_second, 'uncertain', dog_review_note(dog_second))
        rain, rain_hash = upload(session['id'], '5-181766-A-10.wav')
        rain = review(rain, 'other', 'ESC-50 rain 라벨의 외부 환경음입니다. TV 소리로 확인한 기록이 아닙니다.')
        call('POST', f'/outings/{session["id"]}/end', params={'pet_id': PET}, json={})
    else:
        session = outings[0]
        dog_second = by_source['ESC-50 / 5-208030-A-0.wav']
        rain = by_source['ESC-50 / 5-181766-A-10.wav']
        dog_second_hash = hashlib.sha256((ROOT/'5-208030-A-0.wav').read_bytes()).hexdigest()
        rain_hash = hashlib.sha256((ROOT/'5-181766-A-10.wav').read_bytes()).hexdigest()
    summary = call('GET', f'/outings/{session["id"]}/summary', params={'pet_id': PET})
    explanations = {}
    for name, question in [('sounds', '무슨 소리가 있었어?'),
                           ('comparison', '지난번과 달라?'),
                           ('tv', '보호자가 TV라고 확인한 것은?')]:
        explanations[name] = call('POST', f'/outings/{session["id"]}/explain',
                                  json={'pet_id': PET, 'question': question})
    result = {'source': 'ESC-50 official test split; isolated local presentation database',
              'pet_id': PET, 'outing_ids': [outings[-1]['id'], session['id']],
              'input_sha256': {'dog_example_1': hashlib.sha256((ROOT/'5-203128-A-0.wav').read_bytes()).hexdigest(),
                               'dog_example_2': dog_second_hash, 'rain': rain_hash},
              'review_sources': [first['review']['source'], dog_second['review']['source'], rain['review']['source']],
              'summary': {'sample_seconds': summary['sample_seconds'],
                          'bark_candidate_count': summary['bark_candidate_count'],
                          'unknown_seconds': summary['unknown_seconds']},
              'model_windows': {k: v['analysis'].get('audio_lstm', {}).get('windows', [])
                                for k, v in [('dog_example_2', dog_second), ('rain', rain)]},
              'model_results': {k: model_finding(v) for k, v in
                                [('dog_example_1', first), ('dog_example_2', dog_second), ('rain', rain)]},
              'questions': {k: {'question': q['question'], 'provider': q['provider'],
                                'retrieval_mode': q['retrieval_mode'], 'answer': q['answer'],
                                'claims': q['claims']} for k, q in explanations.items()},
              'scope': 'Public dataset simulation, not longitudinal pet history or user-ground-truth accuracy'}
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'summary': result['summary'],
                      'questions': {k: v['answer'] for k, v in result['questions'].items()}},
                     ensure_ascii=False))


if __name__ == '__main__':
    main()
