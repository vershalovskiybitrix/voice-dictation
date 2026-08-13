"""Text-to-speech provider adapters."""

import os
import subprocess
import sys
import shutil
import importlib.util
import re
import threading
import time
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


class TtsPlaybackController:
    def __init__(self):
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._session = 0

    def stop(self):
        with self._lock:
            self._session += 1
            self._stop_event.set()
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass

    def speak(self, text, cfg):
        text = _prepare_tts_text(text)
        with self._lock:
            self.stop()
            self._stop_event = threading.Event()
            self._session += 1
            session = self._session
        chunks = _split_reading_text(text, int(cfg.get("tts_chunk_chars", 280)))
        next_job = None
        for index, chunk in enumerate(chunks):
            if not self._is_session_active(session):
                break
            if next_job is not None:
                result = next_job.result(self, session)
                next_job = None
                if result is None:
                    break
                wav_path, duration = result
            else:
                wav_path, duration = synthesize_text(chunk, cfg)
            if not self._is_session_active(session):
                break

            if index + 1 < len(chunks):
                prefetch_after = max(0.0, duration - float(cfg.get("tts_prefetch_seconds", 5.0)))
                next_text = chunks[index + 1]

                def prefetch():
                    nonlocal next_job
                    if next_job is None and self._is_session_active(session):
                        next_job = _SynthesisJob(next_text, cfg)

                self._play_wav(session, wav_path, duration, prefetch, prefetch_after)
            else:
                self._play_wav(session, wav_path, duration)

    def _is_session_active(self, session):
        with self._lock:
            return session == self._session and not self._stop_event.is_set()

    def _play_wav(self, session, wav_path, duration, prefetch=None, prefetch_after=None):
        if not self._is_session_active(session):
            return
        try:
            winsound.PlaySound(str(wav_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception as e:
            raise TtsError(f"Не удалось проиграть WAV: {e}") from e
        started = time.monotonic()
        prefetched = False
        while self._is_session_active(session):
            elapsed = time.monotonic() - started
            if prefetch and not prefetched and prefetch_after is not None and elapsed >= prefetch_after:
                prefetched = True
                prefetch()
            if elapsed >= duration + 0.2:
                break
            time.sleep(0.05)
        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
        except Exception:
            pass


class _SynthesisJob:
    def __init__(self, text, cfg):
        self._result = None
        self._error = None
        self._done = threading.Event()
        self._thread = threading.Thread(target=self._run, args=(text, dict(cfg)), daemon=True)
        self._thread.start()

    def _run(self, text, cfg):
        try:
            self._result = synthesize_text(text, cfg)
        except Exception as e:
            self._error = e
        finally:
            self._done.set()

    def result(self, controller, session):
        while not self._done.wait(0.05):
            if not controller._is_session_active(session):
                return None
        if self._error:
            raise self._error
        return self._result


_DEFAULT_PLAYBACK = TtsPlaybackController()


PROVIDER_LABELS = {
    "piper": "Piper: локальная нейросетевая читалка",
    "yandex": "Yandex SpeechKit: облачная читалка",
    "google_translate": "Google Translate",
    "amazon_polly_maxim": "Amazon Polly: Maxim",
}

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


def provider_label(provider):
    return PROVIDER_LABELS.get(provider, provider)


def provider_value(label):
    for value, known_label in PROVIDER_LABELS.items():
        if known_label == label:
            return value
    return label


def speak_text(text, cfg):
    return _DEFAULT_PLAYBACK.speak(text, cfg)


def stop_speaking():
    _DEFAULT_PLAYBACK.stop()


def synthesize_text(text, cfg):
    text = _prepare_tts_text(text)
    provider = cfg.get("tts_provider", "yandex")
    if provider in ("sapi", "google_old"):
        provider = "yandex" if provider == "sapi" else "google_translate"
    if provider == "piper":
        return speak_piper(text, cfg)
    if provider == "yandex":
        return speak_yandex(text, cfg)
    if provider == "google_translate":
        return speak_google_translate(text, cfg)
    if provider == "amazon_polly_maxim":
        return speak_amazon_polly_maxim(text, cfg)
    raise TtsError(f"Неизвестный TTS-провайдер: {provider!r}")


def _prepare_tts_text(text):
    text = str(text or "").strip()
    text = re.sub(r"([?!.,;:])\1{1,}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not any(ch.isalnum() for ch in text):
        raise TtsError("Нет текста для чтения.")
    return text


def speak_clipboard(cfg):
    try:
        text = pyperclip.paste()
    except Exception as e:
        raise TtsError(f"Не удалось прочитать буфер: {e}") from e
    if not text.strip():
        raise TtsError("Буфер пуст.")
    speak_text(text, cfg)


def _wav_duration(path):
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        rate = wav.getframerate()
    if rate <= 0:
        return 0.0
    return frames / float(rate)


def _split_reading_text(text, limit):
    limit = max(80, limit)
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(sentence) <= limit:
            current = sentence
            continue
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = word
    if current:
        chunks.append(current)
    return chunks or [text]


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
    return out_path, _wav_duration(out_path)


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


def _aws_credentials():
    env_file = _load_env_values()
    access_key = os.environ.get("AWS_ACCESS_KEY_ID") or env_file.get("AWS_ACCESS_KEY_ID")
    secret_key = os.environ.get("AWS_SECRET_ACCESS_KEY") or env_file.get("AWS_SECRET_ACCESS_KEY")
    session_token = os.environ.get("AWS_SESSION_TOKEN") or env_file.get("AWS_SESSION_TOKEN")
    region = os.environ.get("AWS_REGION") or env_file.get("AWS_REGION")
    return access_key, secret_key, session_token, region


def _polly_client(cfg):
    try:
        import boto3
    except Exception as e:
        raise TtsError(f"boto3 не установлен для Amazon Polly: {e}") from e
    access_key, secret_key, session_token, env_region = _aws_credentials()
    region = cfg.get("tts_polly_region") or env_region or "eu-central-1"
    kwargs = {"region_name": region}
    if access_key and secret_key:
        kwargs["aws_access_key_id"] = access_key
        kwargs["aws_secret_access_key"] = secret_key
        if session_token:
            kwargs["aws_session_token"] = session_token
    return boto3.client("polly", **kwargs)


def _polly_rate(cfg):
    try:
        value = int(float(cfg.get("tts_polly_rate_percent", 100)))
    except (TypeError, ValueError):
        value = 100
    return max(20, min(200, value))


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
    return out_path, _wav_duration(out_path)


def speak_amazon_polly_maxim(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    client = _polly_client(cfg)
    sample_rate = 16000
    rate = _polly_rate(cfg)
    ssml = f'<speak><prosody rate="{rate}%">{_escape_ssml_text(text)}</prosody></speak>'
    try:
        response = client.synthesize_speech(
            Engine="standard",
            LanguageCode="ru-RU",
            VoiceId="Maxim",
            OutputFormat="pcm",
            SampleRate=str(sample_rate),
            TextType="ssml",
            Text=ssml,
        )
        audio = response["AudioStream"].read()
    except Exception as e:
        raise TtsError(f"Amazon Polly Maxim не смог озвучить текст: {e}") from e
    if not audio:
        raise TtsError("Amazon Polly Maxim вернул пустой ответ.")

    out_dir = Path(RUNTIME_DIR) / "tts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"amazon_polly_maxim_{uuid.uuid4().hex}.wav"
    with wave.open(str(out_path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(audio)
    return out_path, _wav_duration(out_path)


def _escape_ssml_text(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def speak_google_translate(text, cfg):
    if not text.strip():
        raise TtsError("Нет текста для чтения.")
    try:
        import numpy as np
        import soundfile as sf
    except Exception as e:
        raise TtsError(f"numpy/soundfile не установлены для Google Translate TTS: {e}") from e

    out_dir = Path(RUNTIME_DIR) / "tts" / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / f"google_translate_{uuid.uuid4().hex}.wav"
    try:
        chunks = _split_google_tts_text(text)
        parts = []
        sample_rate = None
        for chunk in chunks:
            mp3_path = out_dir / f"google_translate_{uuid.uuid4().hex}.mp3"
            _download_google_translate_tts(
                chunk,
                cfg.get("tts_google_lang", "ru"),
                cfg.get("tts_google_tld", "com"),
                mp3_path,
            )
            audio, current_rate = sf.read(str(mp3_path), dtype="float32")
            sample_rate = sample_rate or current_rate
            if current_rate != sample_rate:
                raise TtsError(f"Google Translate TTS вернул разные sample rate: {sample_rate} и {current_rate}.")
            parts.append(audio)
        audio = np.concatenate(parts) if len(parts) > 1 else parts[0]
        audio = _change_audio_speed(audio, float(cfg.get("tts_google_speed", 1.0)))
        sf.write(str(wav_path), audio, sample_rate)
    except Exception as e:
        raise TtsError(f"Google Translate TTS не смог озвучить текст: {e}") from e
    return wav_path, _wav_duration(wav_path)


def _change_audio_speed(audio, speed):
    if speed <= 0:
        raise TtsError("Скорость Google TTS должна быть больше 0.")
    if abs(speed - 1.0) < 0.01:
        return audio
    speed = max(0.5, min(2.0, speed))
    try:
        from scipy import signal
    except Exception as e:
        raise TtsError(f"scipy не установлен для изменения скорости Google TTS: {e}") from e
    target_len = max(1, int(len(audio) / speed))
    return signal.resample(audio, target_len, axis=0)


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


def providers_status():
    piper_exe = find_piper_exe()
    piper_model = find_piper_model()
    yandex_api_key, yandex_folder_id = _yandex_credentials()
    aws_access_key, aws_secret_key, _aws_session_token, aws_region = _aws_credentials()
    polly_has_boto3 = bool(importlib.util.find_spec("boto3"))
    polly_ready = bool(polly_has_boto3 and aws_access_key and aws_secret_key)
    return {
        "piper": {
            "available": bool(piper_exe and piper_model),
            "detail": f"{piper_exe}; {piper_model}" if piper_exe and piper_model else "piper.exe или .onnx модель не найдены",
            "label": provider_label("piper"),
        },
        "yandex": {
            "available": bool(yandex_api_key and yandex_folder_id),
            "detail": "YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER_ID найдены" if yandex_api_key and yandex_folder_id else "нужны YANDEX_CLOUD_API_KEY и YANDEX_CLOUD_FOLDER_ID в .env",
            "label": provider_label("yandex"),
        },
        "google_translate": {
            "available": bool(importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile")),
            "detail": "готово" if importlib.util.find_spec("numpy") and importlib.util.find_spec("soundfile") else "numpy/soundfile не установлены",
            "label": provider_label("google_translate"),
        },
        "amazon_polly_maxim": {
            "available": polly_ready,
            "detail": f"boto3 + AWS keys; region {aws_region or 'config/default'}" if polly_ready else "нужны boto3, AWS_ACCESS_KEY_ID и AWS_SECRET_ACCESS_KEY в .env",
            "label": provider_label("amazon_polly_maxim"),
        },
    }
