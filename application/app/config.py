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
    "speech_recognition_provider": "whisper",  # whisper | yandex | both

    # Хоткеи.
    #  ptt_key   — «зажать-и-говорить». Если во время удержания нажата ЛЮБАЯ другая
    #              клавиша (Ctrl+Home, Ctrl+C и т.п.) — диктовка отменяется без вставки.
    #  toggle_key — режим вкл/выкл. Scroll Lock удобен: его лампочка показывает,
    #               что микрофон в режиме диктовки.
    "ptt_key": "ctrl_r",
    "toggle_key": "scroll_lock",
    "read_selected_key": "ctrl_r",
    "read_selected_double_tap": True,
    "read_selected_double_tap_seconds": 0.45,
    "read_selected_max_tap_seconds": 0.25,
    "read_selected_copy_delay_seconds": 0.12,
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
    "chunk_strip_trailing_ellipsis": True,
    "ptt_stop_grace_seconds": 0.15,
    "toggle_stop_grace_seconds": 0.55,
    "transcription_tail_padding_seconds": 0.25,
    "tail_retranscribe_enabled": True,
    "tail_retranscribe_min_seconds": 35.0,
    "tail_retranscribe_seconds": 25.0,
    "history_persist_count": 50,

    # Читалка текста. Windows SAPI удалён из проекта из-за непригодного качества.
    "tts_provider": "yandex",      # piper | yandex | google_translate | amazon_polly_maxim
    "tts_piper_exe": "",
    "tts_piper_model": "",
    "tts_yandex_voice": "alena",
    "tts_yandex_role": "",
    "tts_yandex_speed": 1.0,
    "tts_google_lang": "ru",
    "tts_google_tld": "com",
    "tts_google_speed": 1.0,
    "tts_polly_region": "eu-central-1",
    "tts_polly_rate_percent": 100,
    "tts_chunk_chars": 280,
    "tts_prefetch_seconds": 5.0,
    "tts_stop_triple_tap": True,

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
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
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
    if cfg.get("tts_provider") == "sapi":
        cfg["tts_provider"] = "yandex"
    if cfg.get("tts_provider") == "google_old":
        cfg["tts_provider"] = "google_translate"
    for key in (
        "tts_sapi_remove_later",
        "tts_voice",
        "tts_rate",
        "tts_volume",
    ):
        cfg.pop(key, None)
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
