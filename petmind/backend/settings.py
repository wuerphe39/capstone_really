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
    audio_detector: str = os.getenv('PETMIND_AUDIO_DETECTOR', 'yamnet').lower()
    yamnet_url: str = os.getenv('PETMIND_YAMNET_URL', 'http://127.0.0.1:8030/analyze')
    audio_storage_dir: Path = Path(os.getenv('PETMIND_AUDIO_STORAGE_DIR', str(ROOT/'artifacts'/'user_audio')))
    # LAN mode (start_demo -Lan): private-network clients may connect with this key. Empty = this PC only.
    lan_token: str = os.getenv('PETMIND_LAN_TOKEN', '').strip()
    # 'speaker' only when the launcher starts the speaker agent (start_demo -Speaker); the guardian's approval decides every play.
    action_mode: str = os.getenv('PETMIND_ACTION_MODE', 'simulated').strip().lower()
    # Phone notification for a sustained-barking alert, through ntfy (https://ntfy.sh or a self-hosted server). Empty topic = off.
    ntfy_topic: str = os.getenv('PETMIND_NTFY_TOPIC', '').strip()
    ntfy_server: str = os.getenv('PETMIND_NTFY_SERVER', 'https://ntfy.sh').strip()
    public_url: str = os.getenv('PETMIND_PUBLIC_URL', '').strip()  # opened when the notification is tapped
    # Built Flutter web app served by this backend at "/" (same origin, so phones need one address only).
    web_dir: Path | None = Path(os.environ['PETMIND_WEB_DIR']) if os.getenv('PETMIND_WEB_DIR') else None


settings = Settings()
if settings.action_mode not in {'simulated', 'speaker'}:
    raise ValueError('PETMIND_ACTION_MODE must be simulated or speaker')
if settings.ntfy_topic and len(settings.ntfy_topic) < 16:
    raise ValueError('PETMIND_NTFY_TOPIC must be at least 16 characters (the topic name is the only secret on a public ntfy server)')
if settings.lan_token and len(settings.lan_token) < 16:
    raise ValueError('PETMIND_LAN_TOKEN must be at least 16 characters')


def audio_lstm_checkpoint_path(root: Path | None = None) -> Path:
    """Select a local experimental checkpoint without changing the default model."""
    name = settings.audio_lstm_checkpoint_name
    if not re.fullmatch(r'[A-Za-z0-9_.-]+\.pt', name):
        raise ValueError('PETMIND_AUDIO_LSTM_CHECKPOINT must be a filename under artifacts/audio_lstm')
    return (root or ROOT) / 'artifacts' / 'audio_lstm' / name
