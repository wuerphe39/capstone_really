"""Retention while the local service is running; startup catches offline expiry."""
import asyncio
import logging

from starlette.concurrency import run_in_threadpool

from ..database import SessionLocal


def cleanup_once(sessions=SessionLocal):
    from ..routers.audio_clips import purge_expired
    with sessions() as db:
        purge_expired(db)


async def cleanup_loop(interval_seconds=60):
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_in_threadpool(cleanup_once)
        except Exception:
            logging.getLogger(__name__).exception('Audio retention cleanup failed; retry next interval')
