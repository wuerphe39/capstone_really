"""Event media lifecycle shared by evidence lookup and audio retention."""
import json
from sqlalchemy import select
from ..database import AudioClipLog, ObservationMedia, utcnow


def event_source(media):
    source = json.loads(media.source_json) if media else {}
    return source if source.get('kind') == 'audio_triggered_video' else None


def available(db, media):
    source = event_source(media)
    if source is None:
        return True
    ids = source['clip_ids']
    rows = list(db.scalars(select(AudioClipLog).where(AudioClipLog.id.in_(ids))))
    return len(rows) == len(ids) and all(r.deleted_at is None and r.expires_at > utcnow() for r in rows)


def delete_for_audio(db, clip_id):
    from ..routers.outings import MEDIA_ROOT
    # No schema migration: event attributes reside in existing source metadata.
    for media in db.scalars(select(ObservationMedia)):
        source = event_source(media)
        if source and clip_id in source['clip_ids']:
            path = (MEDIA_ROOT/media.filename).resolve()
            if path.is_relative_to(MEDIA_ROOT.resolve()):
                path.unlink(missing_ok=True)
            source['status'] = 'deleted'
            media.source_json = json.dumps(source, ensure_ascii=False)
            for row in db.scalars(select(AudioClipLog).where(AudioClipLog.id.in_(source['clip_ids']))):
                analysis = json.loads(row.analysis_json)
                analysis['event_video'] = {**source, 'status':'deleted'}
                row.analysis_json = json.dumps(analysis, ensure_ascii=False)
