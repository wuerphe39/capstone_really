"""Bounded model cache keyed by checkpoint bytes; no personal audio is cached."""
import io
from functools import lru_cache
from pathlib import Path

from .audio_lstm import AudioPredictor


@lru_cache(maxsize=2)
def _load(content):
    return AudioPredictor(io.BytesIO(content))


def get_audio_predictor(checkpoint):
    # Reading first also detects replacement with unchanged filename/mtime.
    return _load(Path(checkpoint).read_bytes())
