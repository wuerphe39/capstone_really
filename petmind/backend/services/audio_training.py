"""Local reviewed-data export. No audio copy, automatic learning or model deployment."""
import hashlib
import json
from pathlib import Path

from sqlalchemy import select

from ..database import AudioClipLog, AudioVerificationLog, utcnow


def review_hash(row):
    return hashlib.sha256(row.review_json.encode()).hexdigest()


def eligibility(db, row):
    from ..routers.audio_clips import path_for
    if row.deleted_at or row.expires_at <= utcnow():
        return 'deleted_or_expired'
    if not row.training_consent:
        return 'no_training_consent'
    review = json.loads(row.review_json)
    if not review or review.get('label') == 'uncertain':
        return 'guardian_review_incomplete'
    path = path_for(row)
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row.sha256:
        return 'original_missing_or_changed'
    verification = db.get(AudioVerificationLog,row.id)
    if not row.verified_at or not verification or verification.review_sha256 != review_hash(row) or verification.audio_sha256 != row.sha256:
        return 'independent_review_required'
    return None


def verify(db, clip_id, label, reviewer, reason):
    if label not in {'dog','other'} or not reviewer.strip() or not reason.strip():
        raise ValueError('dog/other label, reviewer and rationale required')
    row = db.get(AudioClipLog,clip_id)
    if row is None:
        raise ValueError('clip not found')
    problem = eligibility(db,row)
    if problem not in {None,'independent_review_required'}:
        raise ValueError(problem)
    record = db.get(AudioVerificationLog,clip_id)
    values = {'label':label,'reviewer':reviewer,'reason':reason,'review_sha256':review_hash(row),
              'audio_sha256':row.sha256,'verified_at':utcnow()}
    if record:
        for key,value in values.items(): setattr(record,key,value)
    else:
        db.add(AudioVerificationLog(clip_id=clip_id,**values))
    row.verified_at = values['verified_at']
    db.commit()


def build_manifest(db):
    from ..routers.audio_clips import purge_expired
    purge_expired(db)
    rows = db.scalars(select(AudioClipLog).order_by(AudioClipLog.id)).all()
    # Group ALL known clips, not only currently eligible clips. Same pet or exact
    # source hash must never cross splits, including transitive shared uploads.
    parents = {row.pet_id: row.pet_id for row in rows}
    def root(pet):
        while parents[pet] != pet:
            parents[pet] = parents[parents[pet]]; pet = parents[pet]
        return pet
    sources = {}
    for row in rows:
        if row.sha256 in sources:
            a,b = sorted([root(row.pet_id),root(sources[row.sha256])]); parents[b] = a
        sources[row.sha256] = row.pet_id
    eligible, excluded, seen = [], [], {}
    for row in rows:
        problem = eligibility(db,row)
        if problem:
            excluded.append({'clip_id':row.id,'reason':problem}); continue
        verification = db.get(AudioVerificationLog,row.id)
        if row.sha256 in seen:
            previous = seen[row.sha256]
            if previous['label'] != verification.label:
                previous['conflict'] = True
                excluded.append({'clip_id':row.id,'reason':'conflicting_duplicate_label'})
            else:
                excluded.append({'clip_id':row.id,'reason':'duplicate_audio'})
            continue
        group = hashlib.sha256(('petmind-split-v1:'+root(row.pet_id)).encode()).hexdigest()
        bucket = int(group[:8],16)%10
        entry = {'clip_id':row.id,'sha256':row.sha256,'review_sha256':review_hash(row),
                 'label':verification.label,'group':group,
                 'split':'train' if bucket < 6 else 'validation' if bucket < 8 else 'test'}
        seen[row.sha256] = entry; eligible.append(entry)
    records = []
    for entry in eligible:
        if entry.pop('conflict',False): excluded.append({'clip_id':entry['clip_id'],'reason':'conflicting_duplicate_label'})
        else: records.append(entry)
    return {'created_at':utcnow().isoformat()+'Z','schema':1,'records':records,'excluded':excluded,
            'policy':'pet/source connected groups; deterministic 60/20/20 buckets, deduplicated exact audio',
            'note':'snapshot only: revalidate before every training read; no raw audio copied; not automatic retraining'}


def resolve_manifest(db, manifest):
    """Fail closed if consent, expiry, opinion, label, source or grouping changed."""
    from ..routers.audio_clips import path_for
    current = {row['clip_id']:row for row in build_manifest(db)['records']}
    resolved = []
    for entry in manifest['records']:
        if current.get(entry['clip_id']) != entry:
            raise ValueError('stale or revoked manifest: regenerate before training')
        row = db.get(AudioClipLog,entry['clip_id'])
        resolved.append({**entry,'path':str(path_for(row))})
    return resolved
