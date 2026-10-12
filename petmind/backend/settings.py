"""Local development defaults; secrets never enter stored observations."""
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / '.env')


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv('PETMIND_DATABASE_URL', f'sqlite:///{ROOT / "petmind.db"}')
    provider: str = os.getenv('PETMIND_LLM_PROVIDER', 'gemini' if os.getenv('GEMINI_API_KEY') else 'rule')
    retrieval_mode: str = os.getenv('PETMIND_RETRIEVAL_MODE', 'mcp')
    semantic_enabled: bool = os.getenv('PETMIND_SEMANTIC_SEARCH', 'off').lower() == 'on'
    gemini_api_key: str | None = os.getenv('GEMINI_API_KEY')
    gemini_model: str = os.getenv('PETMIND_GEMINI_MODEL', 'gemini-3.5-flash-lite')
    gemini_timeout_seconds: float = float(os.getenv('PETMIND_GEMINI_TIMEOUT_SECONDS', '12'))
    action_timeout_seconds: int = int(os.getenv('PETMIND_ACTION_TIMEOUT_SECONDS', '30'))
    audio_lstm_checkpoint_name: str = os.getenv('PETMIND_AUDIO_LSTM_CHECKPOINT', 'esc50_lstm.pt')
    audio_detector: str = os.getenv('PETMIND_AUDIO_DETECTOR', 'lstm').lower()
    yamnet_url: str = os.getenv('PETMIND_YAMNET_URL', 'http://127.0.0.1:8030/analyze')
    audio_storage_dir: Path = Path(os.getenv('PETMIND_AUDIO_STORAGE_DIR', str(ROOT/'artifacts'/'user_audio')))


settings = Settings()


def audio_lstm_checkpoint_path(root: Path | None = None) -> Path:
    """Select a local experimental checkpoint without changing the default model."""
    name = settings.audio_lstm_checkpoint_name
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.pt', name):
        raise ValueError('PETMIND_AUDIO_LSTM_CHECKPOINT must be a filename under artifacts/audio_lstm')
    return (root or ROOT) / 'artifacts' / 'audio_lstm' / name
