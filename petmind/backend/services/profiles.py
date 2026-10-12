import json


def profile_out(row):
    if row is None:
        return None
    return {'pet_id': row.pet_id, 'source': 'guardian_input',
            **json.loads(row.profile_json), 'updated_at': row.updated_at.isoformat()+'Z'}
