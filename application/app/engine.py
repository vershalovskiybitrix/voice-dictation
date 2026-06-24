"""Движок распознавания: подготовка CUDA, загрузка модели и транскрипция."""

import os

from .util import log


def add_cuda_dll_dirs():
    """На Windows CTranslate2 не находит DLL из pip-пакетов nvidia-*-cu12 сам —
    добавляем их каталоги bin в путь поиска DLL до импорта faster_whisper."""
    if os.name != "nt":
        return
    try:
        import nvidia
    except ImportError:
        return
    for base in list(getattr(nvidia, "__path__", [])):
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            p = os.path.join(base, sub, "bin")
            if not os.path.isdir(p):
                continue
            try:
                os.add_dll_directory(p)
            except Exception:
                pass
            os.environ["PATH"] = p + os.pathsep + os.environ.get("PATH", "")


def load_model(cfg):
    """Загружает faster-whisper с каскадным фолбэком GPU → CPU.

    GTX 10xx (Pascal, compute 6.1) не умеет int8_float16/float16, поэтому на GPU
    пробуем int8, затем float32, и в крайнем случае откатываемся на CPU.
    Возвращает (model, device)."""
    add_cuda_dll_dirs()
    from faster_whisper import WhisperModel

    model_name = cfg["model"]
    device_pref = cfg["device"]

    attempts = []
    if device_pref in ("auto", "cuda"):
        attempts.append(("cuda", "int8"))
        attempts.append(("cuda", "float32"))
    if device_pref in ("auto", "cpu", "cuda"):
        attempts.append(("cpu", "int8"))

    last_err = None
    for device, compute_type in attempts:
        try:
            log(f"Загрузка модели '{model_name}' на {device} ({compute_type})...")
            model = WhisperModel(model_name, device=device, compute_type=compute_type)
            log(f"Модель загружена: {device} / {compute_type}")
            return model, device
        except Exception as e:
            last_err = e
            log(f"Не удалось на {device}/{compute_type}: {e}")
    raise RuntimeError(f"Не удалось загрузить модель ни на одном устройстве: {last_err}")


class Transcriber:
    """Преобразует аудио (numpy float32 16кГц или путь к файлу) в текст."""

    def __init__(self, model, cfg):
        self.model = model
        self.cfg = cfg
        self.blacklist = {s.strip().lower() for s in cfg["hallucination_blacklist"]}

    def transcribe(self, audio, language):
        lang = None if language in ("auto", "", None) else language
        segments, _info = self.model.transcribe(
            audio,
            language=lang,
            beam_size=self.cfg["beam_size"],
            temperature=0.0,
            condition_on_previous_text=False,
            vad_filter=True,
            initial_prompt=self.cfg["initial_prompt"] or None,
        )
        threshold = self.cfg["no_speech_threshold"]
        parts = [
            seg.text
            for seg in segments
            if seg.no_speech_prob is None or seg.no_speech_prob <= threshold
        ]
        text = "".join(parts).strip()
        if text.lower() in self.blacklist:
            log(f"Отброшено как галлюцинация: {text!r}")
            return ""
        return text
