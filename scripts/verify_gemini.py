"""Verify one real grounded Gemini call after the user has set the local API key."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from petmind.backend.database import SessionLocal, init_db
from petmind.backend.main import analyze_demo
from petmind.backend.providers import GeminiProvider
from petmind.backend.schemas import ObservationIn
from petmind.backend.services import care
from petmind.backend.services.observations import save
from petmind.backend.settings import settings


def main():
    if not settings.gemini_api_key:
        raise SystemExit('Not verified: set GEMINI_API_KEY in local .env first (do not put it in chat).')
    init_db()
    now = datetime.now(timezone.utc)
    pet = 'gemini-verification-' + now.strftime('%Y%m%d%H%M%S')
    with SessionLocal() as db:
        save(db, ObservationIn(pet_id=pet, session_id='gemini-past', observed_at=now-timedelta(days=1),
                              source='synthetic_demo', context=analyze_demo('bored_pacing')))
        current = save(db, ObservationIn(pet_id=pet, session_id='gemini-current', observed_at=now,
                                        source='synthetic_demo', context=analyze_demo('anxious')))
        care.get_provider = GeminiProvider
        result = care.evaluate(db, current.id, '과거 관찰과 비교해서 보호자가 무엇을 확인하면 좋을까요?')
    Path('artifacts').mkdir(exist_ok=True)
    Path('artifacts/gemini_verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if not result['provider'].startswith('gemini:') or result['retrieval']['status'] != 'ok':
        print(json.dumps(result['retrieval'].get('provider_failure', {})))
        raise SystemExit('Not verified: provider or MCP failed; saved result identifies fallback.')
    print(json.dumps({'provider': result['provider'], 'retrieval': result['retrieval']['status'],
                      'cited_observation_ids': result['cited_observation_ids']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
