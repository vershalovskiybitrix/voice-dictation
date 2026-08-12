"""Text-to-speech provider adapters."""

import subprocess
import sys
import shutil
import importlib.util

import pyperclip

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
    if provider == "rhvoice":
        return speak_rhvoice(text, cfg)
    if provider in ("piper", "silero", "yandex", "google_old"):
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
            "available": bool(shutil.which("piper")),
            "detail": shutil.which("piper") or "piper CLI не найден",
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
