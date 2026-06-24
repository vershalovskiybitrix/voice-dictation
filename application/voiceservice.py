"""
VoiceService — локальная диктовка речи (RU/EN) с вставкой в курсор.

По горячей клавише записывает речь с микрофона, локально распознаёт через
faster-whisper и вставляет готовый текст (с пунктуацией) туда, где стоит курсор.
Работает в трее; в простое ресурсы не расходуются.

Хоткеи (настраиваются в config.json):
  - PTT (правый Ctrl): держать и говорить; нажатие любой другой клавиши отменяет ввод.
  - Toggle (Scroll Lock): нажал — пишет (горит лампочка), нажал снова — вставка.

Реализация разнесена по пакету app/ (см. app/service.py).
"""

import sys

# Вывод (в т.ч. в boot.log под pythonw) — в UTF-8, чтобы кириллица/спецсимволы
# в логах и именах файлов не роняли приложение (по умолчанию была бы cp1251).
for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.service import run

if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        sys.exit(0)
