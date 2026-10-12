"""
PetMind 백엔드 서버 (FastAPI + SQLite + MQTT)

실행:
    cd petmind/backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

API 문서:
    http://localhost:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from database import SessionLocal, init_db
from routers import analysis, feeding, sensors, care
from settings import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    print("PetMind 서버 시작됨")
    yield


app = FastAPI(title="PetMind API", version="2.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(feeding.router)
app.include_router(sensors.router)
app.include_router(care.router)


@app.get("/")
def root():
    return {
        "status": "ok",
        "service": "PetMind API",
        "version": app.version,
        "docs": "/docs",
    }


@app.get("/health")
def health():
    database_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        database_ok = True
    except Exception as exc:
        print(f"[Health] database failed: {exc}")
    return {
        "status": "healthy" if database_ok else "degraded",
        "components": {
            "database": "ok" if database_ok else "failed",
            "care_provider": settings.provider,
            "action_mode": "simulation" if settings.simulate_actions else "mqtt",
            "mqtt_target": f"{settings.mqtt_broker}:{settings.mqtt_port}",
        },
    }
