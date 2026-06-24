"""Захват аудио с микрофона."""

import threading

import numpy as np
import sounddevice as sd

from .config import SAMPLE_RATE
from .util import log


class Recorder:
    """Пишет моно-аудио в буфер, пока открыт поток. start() → ... → stop()/discard()."""

    def __init__(self):
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()

    def _callback(self, indata, frames, time_info, status):
        if status:
            log(f"Аудио-статус: {status}")
        with self._lock:
            self._frames.append(indata.copy())

    def start(self):
        with self._lock:
            self._frames = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def _close_stream(self):
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            finally:
                self._stream = None

    def stop(self):
        """Закрывает поток и возвращает накопленное аудио (1-D float32)."""
        self._close_stream()
        with self._lock:
            if not self._frames:
                return np.zeros(0, dtype=np.float32)
            return np.concatenate(self._frames, axis=0).flatten()

    def discard(self):
        """Закрывает поток и выбрасывает записанное (отмена ввода)."""
        self._close_stream()
        with self._lock:
            self._frames = []
