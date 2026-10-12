"""Run from repository root: python -m uvicorn petmind.backend.main:app --port 8010."""
import json
import asyncio
import uuid
import ipaddress
import re
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text

from pet_monitor.bark import BarkDetector
from pet_monitor.build import build_context
from pet_monitor.simulator import make_scenario
from .database import CareActionLog, CareSuggestionLog, ObservationLog, SessionLocal, get_db, init_db
from .routers.care import router as care_router
from .routers.media import router as media_router
from .routers.pets import router as pets_router
from .routers.feedback import router as feedback_router
from .routers.comparisons import router as comparisons_router
from .routers.outings import router as outings_router
from .routers.audio_clips import router as audio_clips_router
from .routers.event_videos import router as event_videos_router
from .routers.camera import router as camera_router
from .routers.capture import router as capture_router
from .schemas import DemoRequest, ObservationIn, ObservationOut
from .services.observations import save, to_out
from .services.audio_retention import cleanup_once, cleanup_loop
from starlette.concurrency import run_in_threadpool
from .settings import ROOT, settings, audio_lstm_checkpoint_path


@asynccontextmanager
async def lifespan(app):
    init_db()
    await run_in_threadpool(cleanup_once)
    maintenance = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        maintenance.cancel()
        with suppress(asyncio.CancelledError):
            await maintenance


app = FastAPI(title='PetMind integrated API', version='0.3.0', lifespan=lifespan)


@app.middleware('http')
async def local_preview_boundary(request: Request, call_next):
    """This unauthenticated prototype must remain on loopback/SSH tunnels."""
    host = request.client.host if request.client else ''
    try:
        local_client = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local_client = host == 'testclient'
    origin = request.headers.get('origin')
    local_origin = not origin or bool(re.fullmatch(
        r'http://(?:localhost|127\.0\.0\.1)(?::\d+)?', origin))
    if not local_client or not local_origin:
        return JSONResponse({'detail': 'PetMind 시제품은 로컬/SSH 연결에서만 접근할 수 있습니다.'},
                            status_code=403)
    return await call_next(request)


app.add_middleware(CORSMiddleware, allow_origin_regex=r'http://(localhost|127\.0\.0\.1)(:\d+)?',
                   allow_methods=['GET', 'POST'], allow_headers=['Content-Type'])
app.include_router(care_router)
app.include_router(media_router)
app.include_router(pets_router)
app.include_router(feedback_router)
app.include_router(comparisons_router)
app.include_router(outings_router)
app.include_router(audio_clips_router)
app.include_router(event_videos_router)
app.include_router(camera_router)
app.include_router(capture_router)


@app.get('/health')
def health():
    with SessionLocal() as db:
        db.execute(text('SELECT 1'))
    return {'status': 'healthy', 'components': {'database': 'ok', 'care_provider': settings.provider,
            'gemini_key_configured': bool(settings.gemini_api_key), 'retrieval_mode': settings.retrieval_mode,
            'audio_detector': settings.audio_detector,
            'audio_lstm_checkpoint_present': settings.audio_detector == 'lstm' and audio_lstm_checkpoint_path(ROOT).is_file(),
            'audio_lstm_model_role': ('not_used' if settings.audio_detector != 'lstm' else
                                      'default' if settings.audio_lstm_checkpoint_name == 'esc50_lstm.pt' else 'experimental'),
            'action_mode': 'simulated'}, 'version': app.version}


@app.post('/observations', response_model=ObservationOut, status_code=201)
def create_observation(data: ObservationIn, db=Depends(get_db)):
    return save(db, data)


@app.get('/observations', response_model=list[ObservationOut])
def list_observations(pet_id: str, limit: int = Query(20, ge=1, le=100),
                      since: datetime | None = None, until: datetime | None = None, db=Depends(get_db)):
    query = select(ObservationLog).where(ObservationLog.pet_id == pet_id)
    for value in (since, until):
        if value is not None and value.tzinfo is None:
            from fastapi import HTTPException
            raise HTTPException(422, '기간 조회 시 timezone이 필요합니다.')
    if since:
        query = query.where(ObservationLog.observed_at >= since.astimezone(timezone.utc).replace(tzinfo=None))
    if until:
        query = query.where(ObservationLog.observed_at <= until.astimezone(timezone.utc).replace(tzinfo=None))
    rows = db.scalars(query.order_by(ObservationLog.observed_at.desc()).limit(limit)).all()
    return [to_out(row) for row in rows]


def analyze_demo(name):
    audio, observations = make_scenario(name)
    detector = BarkDetector()
    detector.feed(audio)
    context = build_context(detector, observations).to_dict()
    checkpoint = Path('artifacts/lstm/trajectory_lstm.pt')
    if checkpoint.exists():
        from pet_monitor.lstm import LSTMPredictor
        predictor = LSTMPredictor(checkpoint)
        durations = {}
        for i, observation in enumerate(observations):
            label = predictor.predict(observations[:i+1])['label']
            end = observations[i+1].t if i+1 < len(observations) else detector.now_s
            durations[label] = durations.get(label, 0) + end - observation.t
        context['motion']['seconds_by_label'] = durations
        context['motion']['dominant'] = max(durations, key=durations.get)
        context['motion_model'] = 'lstm_synthetic'
        context['lstm_metadata'] = {'feature_version': predictor.feature_version,
                                    'training_source': predictor.training_source}
        context['input_note'] = '합성 좌표·음성 시나리오; LSTM 행동 분류는 합성 라벨 학습; 실제 행동 정확도 미검증'
    return context


@app.post('/demo/observe', response_model=ObservationOut, status_code=201)
def demo_observe(data: DemoRequest, db=Depends(get_db)):
    return save(db, ObservationIn(pet_id=data.pet_id, session_id=f'demo-{uuid.uuid4()}',
                                 observed_at=datetime.now(timezone.utc), source='synthetic_demo',
                                 context=analyze_demo(data.scenario), outing_id=data.outing_id))


@app.post('/demo/seed')
def seed_history(data: DemoRequest, db=Depends(get_db)):
    count = db.scalar(select(func.count()).select_from(ObservationLog).where(
        ObservationLog.pet_id == data.pet_id, ObservationLog.session_id.like('seed-%')))
    if count:
        return {'created': 0, 'existing': count, 'source': 'synthetic_demo'}
    now = datetime.now(timezone.utc)
    for i, scenario in enumerate(['calm', 'bored_pacing', 'anxious']):
        save(db, ObservationIn(pet_id=data.pet_id, session_id=f'seed-{scenario}',
                              observed_at=now - timedelta(days=3-i), source='synthetic_demo',
                              context=analyze_demo(scenario)))
    return {'created': 3, 'source': 'synthetic_demo'}


@app.get('/timeline')
def timeline(pet_id: str, db=Depends(get_db)):
    events = []
    for row in db.scalars(select(ObservationLog).where(ObservationLog.pet_id == pet_id)
                          .order_by(ObservationLog.created_at.desc()).limit(30)):
        events.append({'type': 'observation', 'id': row.id, 'at': row.created_at.isoformat() + 'Z',
                       'detail': row.summary, 'session_id': row.session_id, 'source': row.source})
    for row in db.scalars(select(CareSuggestionLog).where(CareSuggestionLog.pet_id == pet_id)
                          .order_by(CareSuggestionLog.created_at.desc()).limit(30)):
        events.append({'type': 'suggestion', 'id': row.id, 'at': row.created_at.isoformat() + 'Z',
                       'detail': row.summary, 'observation_id': row.observation_id, 'status': row.status})
    for row in db.scalars(select(CareActionLog).join(CareSuggestionLog)
                          .where(CareSuggestionLog.pet_id == pet_id)
                          .order_by(CareActionLog.updated_at.desc()).limit(30)):
        events.append({'type': 'action', 'id': row.id, 'at': row.updated_at.isoformat() + 'Z',
                       'detail': f'가상 음악: {row.status}', 'suggestion_id': row.suggestion_id})
    return sorted(events, key=lambda event: event['at'], reverse=True)[:50]


@app.get('/metrics')
def metrics(pet_id: str, db=Depends(get_db)):
    observations = db.scalar(select(func.count()).select_from(ObservationLog).where(ObservationLog.pet_id == pet_id))
    suggestions = db.scalars(select(CareSuggestionLog).where(CareSuggestionLog.pet_id == pet_id)).all()
    actions = db.scalars(select(CareActionLog).join(CareSuggestionLog).where(CareSuggestionLog.pet_id == pet_id)).all()
    return {'observations': observations, 'suggestions': len(suggestions),
            'mcp_successes': sum(json.loads(row.retrieval_json)['mode'] == 'mcp' and json.loads(row.retrieval_json)['status'] == 'ok' for row in suggestions),
            'gemini_successes': sum(row.provider.startswith('gemini:') for row in suggestions),
            'actions_completed': sum(row.status == 'completed' for row in actions),
            'actions_failed': sum(row.status in {'failed', 'timed_out'} for row in actions)}
