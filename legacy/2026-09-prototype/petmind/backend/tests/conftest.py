import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))
os.environ["PETMIND_DATABASE_URL"] = "sqlite://"
os.environ["PETMIND_SIMULATE_ACTIONS"] = "true"
os.environ["PETMIND_FEATURE_FEEDING"] = "true"

from database import Base, SessionLocal, engine  # noqa: E402
from main import app  # noqa: E402


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
