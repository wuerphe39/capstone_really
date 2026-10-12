"""Gemini retrieval embeddings with a content-addressed, derived SQLite cache."""
import hashlib
import json
import sqlite3

import numpy as np
import requests

from ..settings import ROOT, settings

MODEL = 'gemini-embedding-001'
DIMENSIONS = 768


def embed(texts, task):
    if not texts:
        return []
    if not settings.gemini_api_key:
        raise ValueError('embedding key unavailable')
    cache = ROOT / 'artifacts' / 'rag' / 'embedding_cache.db'
    cache.parent.mkdir(parents=True, exist_ok=True)
    keys = [hashlib.sha256(f'{MODEL}:{DIMENSIONS}:{task}:{text}'.encode()).hexdigest() for text in texts]
    with sqlite3.connect(cache, timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vector TEXT NOT NULL)')
        values = {key: json.loads(row[0]) for key in keys
                  if (row := db.execute('SELECT vector FROM embeddings WHERE key=?', (key,)).fetchone())}
        missing = list(dict.fromkeys(key for key in keys if key not in values))
        by_key = dict(zip(keys, texts))
        for offset in range(0, len(missing), 50):
            batch = missing[offset:offset+50]
            response = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents',
                headers={'x-goog-api-key': settings.gemini_api_key}, timeout=8,
                json={'requests': [{'model': f'models/{MODEL}', 'taskType': task,
                                    'outputDimensionality': DIMENSIONS,
                                    'content': {'parts': [{'text': by_key[key]}]}} for key in batch]})
            response.raise_for_status()
            vectors = response.json()['embeddings']
            if len(vectors) != len(batch):
                raise ValueError('embedding count mismatch')
            for key, item in zip(batch, vectors):
                vector = np.asarray(item['values'], dtype=float)
                if vector.shape != (DIMENSIONS,) or not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
                    raise ValueError('invalid embedding')
                values[key] = (vector / np.linalg.norm(vector)).tolist()
                db.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?)', (key, json.dumps(values[key])))
        db.commit()
    return np.asarray([values[key] for key in keys], dtype=np.float32)
