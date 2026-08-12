"""Silence-aware audio chunking helpers for long toggle dictation."""

import numpy as np

from .config import SAMPLE_RATE


def rms(audio):
    if audio is None or audio.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(audio, dtype=np.float64))))


def should_cut(audio, cfg):
    """Return True when a long enough buffer ends with a configured silence pause."""
    if audio is None or audio.size == 0:
        return False
    min_samples = int(float(cfg["chunk_min_seconds"]) * SAMPLE_RATE)
    max_samples = int(float(cfg["chunk_max_seconds"]) * SAMPLE_RATE)
    silence_samples = int(float(cfg["chunk_silence_seconds"]) * SAMPLE_RATE)
    if audio.size >= max_samples:
        return True
    if audio.size < min_samples or audio.size < silence_samples:
        return False
    tail = audio[-silence_samples:]
    return rms(tail) <= float(cfg["chunk_silence_rms"])
