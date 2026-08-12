"""Text-to-speech provider adapters."""

import os
import subprocess
import sys
import shutil
import importlib.util
import uuid
import winsound
from pathlib import Path

import pyperclip

from .config import RUNTIME_DIR
from .util import log


class TtsError(RuntimeError):
    pass


PROVIDER_LABELS = {
    "sapi": "Windows: системный голос",
    "piper": "Piper: локальная нейросетевая читалка",
    "silero": "Silero: локальная русская модель",
    "rhvoice": "RHVoice: лёгкая офлайн-читалка",
    "yandex": "Yandex SpeechKit: облачная читалка",
    "google_old": "Старый Google-робот: не подключён",
}


def provider_label(provider):
    return PROVIDER_LABELS.get(provider, provider)


def provider_value(label):
    for value, known_label in PROVIDER_LABELS.items():
        if known_label == label:
            return value
    return label


def speak_text(text, cfg):
    provider = cfg.get("tts_provider", "sapi")
    if provider == "sapi":
        return speak_sapi(text, cfg)
    if provider == "piper":
        return speak_piper(text, cfg)
    if provider == "rhvoice":
        return speak_rhvoice(text, cfg)
    if provider in ("silero", "yandex", "google_old"):
        raise TtsError(f"{provider_label(provider)} пока не подключён.")
    raise TtsError(f"Неизвестный TTS-провайдер: {provider!r}")


def speak_clipboard(cfg):
    try:
        text = pyperclip.paste()
    except Exception as e:
        raise TtsError(f"Не удалось прочитать буфер: {e}") from e
    if not text.strip():
        raise TtsError("Буфер пуст.")
    speak_text(text, cfg)


def speak_sapi(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    escaped = (
        text.replace("`", "``")
        .replace("$", "`$")
        .replace('"', '`"')
    )
    voice = cfg.get("tts_voice", "")
    rate = int(cfg.get("tts_rate", 0))
    volume = int(cfg.get("tts_volume", 100))
    script = [
        "$voice = New-Object -ComObject SAPI.SpVoice",
        f"$voice.Rate = {rate}",
        f"$voice.Volume = {volume}",
    ]
    if voice:
        script.extend(
            [
                "$tokens = $voice.GetVoices()",
                f"$match = @($tokens | Where-Object {{ $_.GetDescription() -eq \"{voice}\" }})",
                "if ($match.Count -gt 0) { $voice.Voice = $match[0] }",
            ]
        )
    script.append(f'[void]$voice.Speak("{escaped}", 0)')
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "; ".join(script)],
        text=True,
        capture_output=True,
        check=False,
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )
    if completed.returncode != 0:
        raise TtsError(completed.stderr.strip() or "SAPI вернул ошибку.")


def speak_rhvoice(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    for command in (
        ["RHVoice-client", "-s", cfg.get("tts_voice", "")],
        ["rhvoice-client", "-s", cfg.get("tts_voice", "")],
    ):
        command = [part for part in command if part]
        try:
            completed = subprocess.run(
                command,
                input=text,
                text=True,
                capture_output=True,
                check=False,
                creationflags=0x08000000 if sys.platform == "win32" else 0,
            )
        except FileNotFoundError:
            continue
        if completed.returncode == 0:
            return
        raise TtsError(completed.stderr.strip() or "RHVoice вернул ошибку.")
    raise TtsError("RHVoice-client не найден в PATH.")


def _existing_path(value):
    if not value:
        return None
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if path.exists():
        return str(path)
    return None


def find_piper_exe(cfg=None):
    cfg = cfg or {}
    configured = _existing_path(cfg.get("tts_piper_exe"))
    if configured:
        return configured
    local_root = Path(RUNTIME_DIR) / "tts" / "piper"
    if local_root.exists():
        for path in local_root.rglob("piper.exe"):
            return str(path)
    found = shutil.which("piper") or shutil.which("piper.exe")
    return found


def find_piper_model(cfg=None):
    cfg = cfg or {}
    configured = _existing_path(cfg.get("tts_piper_model"))
    if configured:
        return configured
    models_root = Path(RUNTIME_DIR) / "tts" / "piper" / "models"
    if models_root.exists():
        preferred = models_root / "ru_RU-irina-medium.onnx"
        if preferred.exists():
            return str(preferred)
        for path in models_root.glob("*.onnx"):
            return str(path)
    return None


def speak_piper(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    exe = find_piper_exe(cfg)
    model = find_piper_model(cfg)
    if not exe:
        raise TtsError("Piper не найден: нужен piper.exe в runtime/tts/piper или путь tts_piper_exe.")
    if not model:
        raise TtsError("Модель Piper не найдена: нужен .onnx в runtime/tts/piper/models или путь tts_piper_model.")

    out_dir = Path(RUNTIME_DIR) / "tts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"piper_{uuid.uuid4().hex}.wav"
    completed = subprocess.run(
        [exe, "--model", model, "--output_file", str(out_path)],
        input=text,
        text=True,
        capture_output=True,
        check=False,
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )
    if completed.returncode != 0:
        raise TtsError(completed.stderr.strip() or "Piper вернул ошибку.")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TtsError("Piper не создал WAV-файл.")
    winsound.PlaySound(str(out_path), winsound.SND_FILENAME)


def list_sapi_voices():
    script = (
        "$v = New-Object -ComObject SAPI.SpVoice; "
        "$v.GetVoices() | ForEach-Object { $_.GetDescription() }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            check=False,
            creationflags=0x08000000 if sys.platform == "win32" else 0,
        )
    except Exception as e:
        log(f"Не удалось получить SAPI voices: {e}")
        return []
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def providers_status():
    sapi_voices = list_sapi_voices()
    piper_exe = find_piper_exe()
    piper_model = find_piper_model()
    return {
        "sapi": {
            "available": bool(sapi_voices),
            "detail": ", ".join(sapi_voices) if sapi_voices else "SAPI voices не найдены",
            "label": provider_label("sapi"),
        },
        "rhvoice": {
            "available": bool(shutil.which("RHVoice-client") or shutil.which("rhvoice-client")),
            "detail": shutil.which("RHVoice-client") or shutil.which("rhvoice-client") or "RHVoice-client не найден",
            "label": provider_label("rhvoice"),
        },
        "piper": {
            "available": bool(piper_exe and piper_model),
            "detail": f"{piper_exe}; {piper_model}" if piper_exe and piper_model else "piper.exe или .onnx модель не найдены",
            "label": provider_label("piper"),
        },
        "silero": {
            "available": bool(importlib.util.find_spec("torch")),
            "detail": "torch установлен" if importlib.util.find_spec("torch") else "torch/silero не установлены",
            "label": provider_label("silero"),
        },
        "yandex": {
            "available": False,
            "detail": "Yandex TTS будет подключён отдельным слоем через .env",
            "label": provider_label("yandex"),
        },
        "google_old": {
            "available": False,
            "detail": "старый Google-голос пока не найден/не подключён",
            "label": provider_label("google_old"),
        },
    }
