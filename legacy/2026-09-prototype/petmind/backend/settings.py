"""Environment-backed settings shared by the PetMind backend."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR.parents[1] / ".env")


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv(
        "PETMIND_DATABASE_URL", f"sqlite:///{BACKEND_DIR / 'petmind.db'}"
    )
    mqtt_broker: str = os.getenv("MQTT_BROKER", "localhost")
    mqtt_port: int = int(os.getenv("MQTT_PORT", "1883"))
    simulate_actions: bool = _bool("PETMIND_SIMULATE_ACTIONS")
    allow_direct_feeding: bool = _bool("PETMIND_ALLOW_DIRECT_FEEDING")
    max_feeding_g: float = float(os.getenv("PETMIND_MAX_FEEDING_G", "100"))
    max_daily_feeding_g: float = float(
        os.getenv("PETMIND_MAX_DAILY_FEEDING_G", "300")
    )
    feeding_cooldown_minutes: int = int(
        os.getenv("PETMIND_FEEDING_COOLDOWN_MINUTES", "120")
    )
    action_timeout_seconds: int = int(
        os.getenv("PETMIND_ACTION_TIMEOUT_SECONDS", "20")
    )
    provider: str = os.getenv("PETMIND_LLM_PROVIDER", "rule")
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY")
    gemini_model: str = os.getenv("PETMIND_GEMINI_MODEL", "gemini-2.5-flash-lite")
    gemini_timeout_seconds: float = float(
        os.getenv("PETMIND_GEMINI_TIMEOUT_SECONDS", "5")
    )
    feeding_enabled: bool = _bool("PETMIND_FEATURE_FEEDING")


settings = Settings()
