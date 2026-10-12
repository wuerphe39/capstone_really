"""Prepared public inputs only; inference is cached before the interactive demo."""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..database import get_db
from ..schemas import ObservationIn
from ..services.observations import save
from ..settings import ROOT

router = APIRouter(prefix='/media', tags=['media'])
FOLDER = ROOT / 'artifacts' / 'media'
VIDEO_REPORT = ROOT / 'artifacts' / 'video_analysis.json'


class MediaRequest(BaseModel):
    pet_id: str = Field(min_length=1, max_length=80)
    audio_filename: str
    include_video: bool = True
    outing_id: str | None = Field(default=None, min_length=1, max_length=80)


def manifest():
    path = FOLDER / 'manifest.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else []


@router.get('/catalog')
def catalog():
    return {'files': manifest(), 'video_prepared': VIDEO_REPORT.exists()}


@router.get('/preview')
def preview():
    path = ROOT / 'artifacts' / 'video' / 'preview.jpg'
    if not path.exists():
        raise HTTPException(404, '영상 분석을 먼저 준비해 주세요.')
    return FileResponse(path, media_type='image/jpeg')


@router.get('/video-analysis')
def video_analysis():
    if not VIDEO_REPORT.exists():
        raise HTTPException(409, 'python -m scripts.evaluate_video를 먼저 실행해 주세요.')
    return json.loads(VIDEO_REPORT.read_text(encoding='utf-8'))


@router.post('/observe', status_code=201)
def media_observe(data: MediaRequest, db=Depends(get_db)):
    from pet_monitor.audio import analyze_wav
    item = next((entry for entry in manifest() if entry['type'] == 'audio' and entry['filename'] == data.audio_filename), None)
    if item is None:
        raise HTTPException(422, '준비된 공개 음원 목록에서 선택해 주세요.')
    video = video_analysis() if data.include_video else None
    audio = analyze_wav(FOLDER / item['filename'], max_duration_s=video['duration_s'] if video else None)
    context = audio['context']
    note = f'공개 음원 {item["filename"]}; 에너지 기반 후보 감지; 실제 짖음 분류 미검증'
    if data.include_video:
        duration, window = video['duration_s'], context['window_s']
        start = max(0, duration-window)
        durations = {}
        predictions = video['predictions']
        for i, prediction in enumerate(predictions):
            end = predictions[i+1]['t'] if i+1 < len(predictions) else duration
            overlap = max(0, min(end, duration) - max(prediction['t'], start))
            durations[prediction['label']] = durations.get(prediction['label'], 0) + overlap
        dominant = max(durations, key=durations.get) if durations else 'unknown'
        context['timestamp'] = duration
        context['motion'] = {'window_s': window, 'dominant': dominant, 'seconds_by_label': durations}
        context['motion_model'] = 'lstm_synthetic'
        context['lstm_metadata'] = {'feature_version': video.get('feature_version', 1),
                                    'training_source': video.get('training_source', 'synthetic_trajectories')}
        note += '; 별도 공개 영상의 마지막 구간과 음원을 결합한 합성 시연이며 실제 동시 녹화가 아님; 카메라 움직임 미보정'
        if video['source'].get('original_fps_verified') is False:
            note += f'; DAVIS 이미지 시퀀스 {video["source"]["replay_fps"]}fps 재생용 재구성, 원본 녹화 시간 미검증'
    context['input_note'] = note
    media = None
    if video:
        import hashlib
        source = video['source']
        path = (FOLDER / source['filename']).resolve()
        if not path.is_relative_to(FOLDER.resolve()) or not path.is_file():
            raise HTTPException(409, '관찰 근거로 연결할 원본 영상을 준비해 주세요.')
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if source.get('sha256') != digest:
            raise HTTPException(409, '영상과 분석 결과의 해시가 다릅니다. 영상을 다시 분석해 주세요.')
        media = {'filename': source['filename'], 'sha256': digest,
                 'start_s': start, 'end_s': duration,
                 'source_json': json.dumps(source, ensure_ascii=False)}
    row = save(db, ObservationIn(pet_id=data.pet_id, session_id='public-' + uuid.uuid4().hex,
                                observed_at=datetime.now(timezone.utc), source='public_media', context=context,
                                outing_id=data.outing_id), media=media)
    return {'observation': row.model_dump(mode='json'), 'audio': audio, 'video': video,
            'sources': [item] + ([video['source']] if video else [])}
