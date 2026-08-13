"""Text-to-speech provider adapters."""

import os
import subprocess
import sys
import shutil
import importlib.util
import uuid
import winsound
import wave
from pathlib import Path
from urllib import parse, request, error

import pyperclip

from .config import RUNTIME_DIR, ROOT_DIR
from .util import log


class TtsError(RuntimeError):
    pass


PROVIDER_LABELS = {
    "sapi": "Windows SAPI: временный системный голос",
    "piper": "Piper: локальная нейросетевая читалка",
    "silero": "Silero: локальная русская модель",
    "yandex": "Yandex SpeechKit: облачная читалка",
    "google_old": "Старый Google Translate: тестовый голос",
}

SILERO_SPEAKERS = ["aidar", "baya", "kseniya", "eugene", "xenia"]
# Current adapter uses SpeechKit API v1, so only v1-compatible ru-RU voices are shown.
YANDEX_VOICES = {
    "alena": ["neutral", "good"],
    "filipp": [""],
    "ermil": ["neutral", "good"],
    "jane": ["neutral", "good", "evil"],
    "omazh": ["neutral", "evil"],
    "zahar": ["neutral", "good"],
    "marina": ["neutral", "whisper", "friendly"],
    "madi_ru": [""],
}
_SILERO_MODEL_CACHE = {}


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
    if provider == "silero":
        return speak_silero(text, cfg)
    if provider == "yandex":
        return speak_yandex(text, cfg)
    if provider == "google_old":
        return speak_google_old(text, cfg)
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
        encoding="utf-8",
        capture_output=True,
        check=False,
        creationflags=0x08000000 if sys.platform == "win32" else 0,
    )
    if completed.returncode != 0:
        raise TtsError(completed.stderr.strip() or "Piper вернул ошибку.")
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise TtsError("Piper не создал WAV-файл.")
    winsound.PlaySound(str(out_path), winsound.SND_FILENAME)


def _silero_cache_model_path(model_name):
    torch_home = Path(RUNTIME_DIR) / "tts" / "silero" / "torch"
    return (
        torch_home
        / "hub"
        / "snakers4_silero-models_master"
        / "src"
        / "silero"
        / "model"
        / f"{model_name}.pt"
    )


def find_silero_model_file(cfg=None):
    cfg = cfg or {}
    model_name = cfg.get("tts_silero_model", "v5_ru")
    path = _silero_cache_model_path(model_name)
    return str(path) if path.exists() else None


def _load_silero_model(model_name):
    cached = _SILERO_MODEL_CACHE.get(model_name)
    if cached is not None:
        return cached
    try:
        import torch
    except Exception as e:
        raise TtsError(f"torch не установлен для Silero: {e}") from e
    try:
        torch_home = Path(RUNTIME_DIR) / "tts" / "silero" / "torch"
        torch_home.mkdir(parents=True, exist_ok=True)
        os.environ["TORCH_HOME"] = str(torch_home)
        torch.hub.set_dir(str(torch_home / "hub"))
        model, _example_text = torch.hub.load(
            repo_or_dir="snakers4/silero-models",
            model="silero_tts",
            language="ru",
            speaker=model_name,
            trust_repo=True,
        )
    except Exception as e:
        raise TtsError(f"Не удалось загрузить модель Silero {model_name}: {e}") from e
    _SILERO_MODEL_CACHE[model_name] = model
    return model


def speak_silero(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    try:
        import soundfile as sf
    except Exception as e:
        raise TtsError(f"soundfile не установлен для Silero: {e}") from e

    model_name = cfg.get("tts_silero_model", "v5_ru")
    speaker = cfg.get("tts_silero_speaker", "baya")
    sample_rate = int(cfg.get("tts_silero_sample_rate", 48000))
    if speaker not in SILERO_SPEAKERS:
        raise TtsError(f"Голос Silero должен быть одним из: {', '.join(SILERO_SPEAKERS)}.")

    model = _load_silero_model(model_name)
    try:
        audio = model.apply_tts(text=text, speaker=speaker, sample_rate=sample_rate)
    except Exception as e:
        raise TtsError(f"Silero не смог озвучить текст: {e}") from e

    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    out_dir = Path(RUNTIME_DIR) / "tts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"silero_{uuid.uuid4().hex}.wav"
    sf.write(str(out_path), audio, sample_rate)
    winsound.PlaySound(str(out_path), winsound.SND_FILENAME)


def _load_env_values():
    values = {}
    for path in (Path(ROOT_DIR) / ".env", Path(RUNTIME_DIR) / ".env"):
        if not path.exists():
            continue
        try:
            lines = path.read_text(encoding="utf-8-sig").splitlines()
        except Exception as e:
            log(f"Не удалось прочитать {path}: {e}")
            continue
        for line in lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _yandex_credentials():
    env_file = _load_env_values()
    api_key = os.environ.get("YANDEX_CLOUD_API_KEY") or env_file.get("YANDEX_CLOUD_API_KEY")
    folder_id = os.environ.get("YANDEX_CLOUD_FOLDER_ID") or env_file.get("YANDEX_CLOUD_FOLDER_ID")
    return api_key, folder_id


def speak_yandex(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    api_key, folder_id = _yandex_credentials()
    if not api_key or not folder_id:
        raise TtsError("Yandex TTS не настроен: нужны YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER_ID в .env.")

    sample_rate = 48000
    data = {
        "text": text,
        "lang": "ru-RU",
        "voice": cfg.get("tts_yandex_voice", "alena"),
        "folderId": folder_id,
        "speed": str(cfg.get("tts_yandex_speed", 1.0)),
        "format": "lpcm",
        "sampleRateHertz": str(sample_rate),
    }
    role = cfg.get("tts_yandex_role", "")
    if role:
        data["emotion"] = role
    req = request.Request(
        "https://tts.api.cloud.yandex.net/speech/v1/tts:synthesize",
        data=parse.urlencode(data).encode("utf-8"),
        headers={"Authorization": f"Api-Key {api_key}"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            audio = response.read()
    except error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise TtsError(f"Yandex TTS вернул HTTP {e.code}: {detail}") from e
    except Exception as e:
        raise TtsError(f"Yandex TTS запрос не удался: {e}") from e
    if not audio:
        raise TtsError("Yandex TTS вернул пустой ответ.")

    out_dir = Path(RUNTIME_DIR) / "tts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"yandex_{uuid.uuid4().hex}.wav"
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio)
    winsound.PlaySound(str(out_path), winsound.SND_FILENAME)


def speak_google_old(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    try:
        import numpy as np
        import soundfile as sf
    except Exception as e:
        raise TtsError(f"numpy/soundfile не установлены для Google-robot: {e}") from e

    out_dir = Path(RUNTIME_DIR) / "tts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / f"google_old_{uuid.uuid4().hex}.wav"
    try:
        chunks = _split_google_tts_text(text)
        parts = []
        sample_rate = None
        for chunk in chunks:
            mp3_path = out_dir / f"google_old_{uuid.uuid4().hex}.mp3"
            _download_google_translate_tts(
                chunk,
                cfg.get("tts_google_lang", "ru"),
                cfg.get("tts_google_tld", "com"),
                mp3_path,
            )
            audio, current_rate = sf.read(str(mp3_path), dtype="float32")
            sample_rate = sample_rate or current_rate
            if current_rate != sample_rate:
                raise TtsError(f"Google-robot вернул разные sample rate: {sample_rate} и {current_rate}.")
            parts.append(audio)
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        sf.write(str(wav_path), audio, sample_rate)
    except Exception as e:
        raise TtsError(f"Google-robot TTS не смог озвучить текст: {e}") from e
    winsound.PlaySound(str(wav_path), winsound.SND_FILENAME)


def _split_google_tts_text(text, limit=180):
    words = text.split()
    chunks = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        current = word[:limit]
        rest = word[limit:]
        while rest:
            chunks.append(current)
            current = rest[:limit]
            rest = rest[limit:]
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


def _download_google_translate_tts(text, lang, tld, out_path):
    url = f"https://translate.google.{tld}/translate_tts?" + parse.urlencode(
        {"ie": "UTF-8", "client": "tw-ob", "tl": lang, "q": text}
    )
    req = request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with request.urlopen(req, timeout=30) as response:
        data = response.read()
    if not data:
        raise TtsError("Google Translate TTS вернул пустой ответ.")
    out_path.write_bytes(data)


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
    yandex_api_key, yandex_folder_id = _yandex_credentials()
    silero_ready = all(
        importlib.util.find_spec(name)
        for name in ("torch", "soundfile", "omegaconf")
    )
    silero_model = find_silero_model_file({"tts_silero_model": "v5_ru"})
    return {
        "sapi": {
            "available": bool(sapi_voices),
            "detail": ", ".join(sapi_voices) if sapi_voices else "SAPI voices не найдены",
            "label": provider_label("sapi"),
        },
        "piper": {
            "available": bool(piper_exe and piper_model),
            "detail": f"{piper_exe}; {piper_model}" if piper_exe and piper_model else "piper.exe или .onnx модель не найдены",
            "label": provider_label("piper"),
        },
        "silero": {
            "available": bool(silero_ready and silero_model),
            "detail": silero_model if silero_ready and silero_model else "torch/soundfile/omegaconf или v5_ru.pt не найдены",
            "label": provider_label("silero"),
        },
        "yandex": {
            "available": bool(yandex_api_key and yandex_folder_id),
            "detail": "YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER_ID найдены" if yandex_api_key and yandex_folder_id else "нужны YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER_ID в .env",
            "label": provider_label("yandex"),
        },
        "google_old": {
            "available": bool(importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile")),
            "detail": "прямой Google Translate TTS + soundfile" if importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile") else "numpy/soundfile не установлены",
            "label": provider_label("google_old"),
        },
    }
