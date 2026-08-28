"""
PetMind 백엔드 서버 (FastAPI + SQLite + MQTT)

실행:
    cd petmind/backend
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

API 문서:
    http://localhost:8000/docs
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database import init_db
from routers import analysis, feeding

app = FastAPI(title="PetMind API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analysis.router)
app.include_router(feeding.router)


@app.on_event("startup")
def startup():
    init_db()
    print("PetMind 서버 시작됨")


@app.get("/")
def root():
    return {"status": "ok", "service": "PetMind API"}


@app.get("/health")
def health():
    return {"status": "healthy"}
