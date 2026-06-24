"""Конфигурация: значения по умолчанию и загрузка config.json."""

import json
import os

from .util import log

# Пути: пакет app/ лежит в application/, рабочие файлы — в соседнем runtime/.
PKG_DIR = os.path.dirname(os.path.abspath(__file__))          # .../application/app
APP_DIR = os.path.dirname(PKG_DIR)                            # .../application
ROOT_DIR = os.path.dirname(APP_DIR)                           # корень репозитория
RUNTIME_DIR = os.path.join(ROOT_DIR, "runtime")
CONFIG_PATH = os.path.join(RUNTIME_DIR, "config.json")

SAMPLE_RATE = 16000  # Whisper работает на 16 кГц

DEFAULT_CONFIG = {
    "model": "medium",            # small | medium | large-v3
    "device": "auto",             # auto | cuda | cpu
    "language": "auto",           # auto | ru | en

    # Хоткеи.
    #  ptt_key   — «зажать-и-говорить». Если во время удержания нажата ЛЮБАЯ другая
    #              клавиша (Ctrl+Home, Ctrl+C и т.п.) — диктовка отменяется без вставки.
    #  toggle_key — режим вкл/выкл. Scroll Lock удобен: его лампочка показывает,
    #               что микрофон в режиме диктовки.
    "ptt_key": "ctrl_r",
    "toggle_key": "scroll_lock",
    "ptt_beep_delay": 0.25,       # сек: задержка сигнала «пишу», чтобы не пищать на Ctrl-шорткаты

    "insert_method": "clipboard",  # clipboard | type
    "beep": True,
    "min_record_seconds": 0.4,    # короче — игнор (защита от случайных нажатий)
    "no_speech_threshold": 0.6,   # сегменты с no_speech_prob выше — отбрасываем
    "beam_size": 5,
    "initial_prompt": "",         # словарь частых терминов/имён для точности
    "hallucination_blacklist": [
        "продолжение следует...",
        "продолжение следует…",
        "субтитры сделал dimatorzok",
        "субтитры создавал dimatorzok",
        "редактор субтитров а.семкин корректор а.егорова",
        "спасибо за просмотр",
        "thank you.",
        "thanks for watching!",
        "you",
        "так.",
    ],
}


def load_config():
    """Читает config.json (создаёт при отсутствии), накладывая на значения по умолчанию."""
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update(json.load(f))
        except Exception as e:
            log(f"Не удалось прочитать config.json, использую значения по умолчанию: {e}")
    else:
        try:
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            log(f"Создан config.json со значениями по умолчанию: {CONFIG_PATH}")
        except Exception as e:
            log(f"Не удалось создать config.json: {e}")
    return cfg
