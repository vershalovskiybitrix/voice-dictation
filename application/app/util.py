"""Мелкие утилиты, общие для модулей."""

import sys


def log(msg):
    line = f"[VoiceService] {msg}"
    try:
        print(line, flush=True)
    except (UnicodeEncodeError, ValueError, OSError):
        # Под pythonw вывод может быть в cp1251 — не даём логированию ронять поток.
        try:
            buf = getattr(sys.stdout, "buffer", None)
            if buf is not None:
                buf.write((line + "\n").encode("utf-8", "replace"))
                buf.flush()
        except Exception:
            pass
