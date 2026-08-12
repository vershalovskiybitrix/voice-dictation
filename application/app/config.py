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

    # Распознавание аудиофайлов (голосовые из мессенджеров и пр.).
    #  file_insert_at_cursor — кроме буфера, вставлять результат файла в активное поле.
    #  inbox_dirname         — папка-приёмник внутри runtime/ (бросил файл → распознался).
    #  inbox_keep_processed  — сколько обработанных файлов хранить в inbox/done (0 — удалять сразу).
    "file_insert_at_cursor": False,
    "inbox_dirname": "inbox",
    "inbox_keep_processed": 20,

    # Кэш последних диктовок: аудио сохраняется в runtime/recordings, чтобы при сбое
    # распознавания (петля повторов и т.п.) можно было перераспознать из трея. 0 — выключить.
    "keep_recordings": 10,

    # Длинная диктовка в toggle-режиме: запись режется на куски после паузы.
    # PTT по правому Ctrl не меняется.
    "toggle_chunking_enabled": True,
    "chunk_min_seconds": 10.0,
    "chunk_max_seconds": 30.0,
    "chunk_silence_seconds": 0.4,
    "chunk_silence_rms": 0.012,
    "chunk_poll_seconds": 0.25,
    "chunk_insert_partials": True,
    "chunk_insert_separator": " ",

    # Читалка текста. Провайдеры добавляются адаптерами; SAPI доступен на Windows без
    # тяжёлых моделей, остальные можно подключать и сравнивать отдельно.
    "tts_provider": "sapi",        # sapi | piper | silero | rhvoice | yandex
    "tts_voice": "",
    "tts_rate": 0,                # SAPI: -10..10
    "tts_volume": 100,            # SAPI: 0..100
    "tts_piper_model": "",
    "tts_silero_speaker": "",
    "tts_yandex_voice": "alena",
    "tts_yandex_role": "",
    "tts_yandex_speed": 1.0,
    "tts_robot_preset": "",

    "beep": True,
    "min_record_seconds": 0.4,    # короче — игнор (защита от случайных нажатий)
    "no_speech_threshold": 0.6,   # сегменты с no_speech_prob выше — отбрасываем
    "beam_size": 5,
    # Подсказка терминов: смещает распознавание к правильному написанию брендов/имён
    # (иначе Whisper пишет «гитхаб», «уклада» вместо GitHub, Claude). Допиши свои слова.
    "initial_prompt": "Часто встречаются слова: GitHub, Claude, Anthropic, ChatGPT, "
                      "Python, Git, коммит, пуш, запушь, репозиторий, VoiceService, Whisper.",
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


def save_config(cfg):
    """Сохраняет конфиг в config.json (например, при смене настройки из трея)."""
    try:
        os.makedirs(RUNTIME_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"Не удалось сохранить config.json: {e}")


def inbox_dir(cfg):
    """Путь к папке-приёмнику аудиофайлов (создаётся при обращении)."""
    return os.path.join(RUNTIME_DIR, cfg.get("inbox_dirname", "inbox"))


def recordings_dir(cfg=None):
    """Путь к кэшу последних диктовок (для перераспознавания при сбое)."""
    return os.path.join(RUNTIME_DIR, "recordings")
