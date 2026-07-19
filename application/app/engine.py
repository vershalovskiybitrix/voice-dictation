"""Движок распознавания: подготовка CUDA, загрузка модели и транскрипция."""

import os
import re

from .util import log

# Температуры для отката: при 0.0 распознаётся обычная речь, выше — только те сегменты,
# которые библиотека признала зациклёнными/некачественными. Лестница укорочена до трёх
# шагов (в faster-whisper по умолчанию шесть): петля разрывается так же, но на музыке,
# где «плохими» признаётся много сегментов, расшифровка не замедляется в разы.
TEMPERATURE_FALLBACK = (0.0, 0.2, 0.4)

# Короткий фрагмент (1–4 символа), повторённый 5+ раз подряд: «1.1.1.1.1…», «ииии…».
_REPEAT_RE = re.compile(r"(.{1,4}?)\1{4,}", re.DOTALL)


def collapse_repeats(text):
    """Схлопывает зацикленные повторы до двух копий (страховка поверх temperature-отката).

    Порог намеренно высокий: в обычном тексте короткая группа редко повторяется 5+ раз
    подряд, поэтому нормальные фразы и многоточия не страдают."""
    return _REPEAT_RE.sub(lambda m: m.group(1) * 2, text).strip()


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
        """Распознаёт аудио (numpy float32 16кГц или путь к файлу).

        Порог no_speech отдаём самой модели: свой грубый отсев сегментов выбрасывал куски
        длинной речи и пения (обрывал текст). Тишину отсекает vad_filter, мусорные фразы —
        hallucination_blacklist."""
        lang = None if language in ("auto", "", None) else language
        segments, _info = self.model.transcribe(
            audio,
            language=lang,
            beam_size=self.cfg["beam_size"],
            # Лестница температур — штатная защита от зацикливания: если сегмент признан
            # слишком повторяющимся (compression_ratio выше порога), он перераспознаётся
            # со следующей температурой. Одно число отключало бы этот откат.
            temperature=TEMPERATURE_FALLBACK,
            compression_ratio_threshold=2.4,   # детектор «текст зациклился»
            repetition_penalty=1.1,            # мягко снижает шанс войти в петлю
            condition_on_previous_text=False,
            vad_filter=True,
            no_speech_threshold=self.cfg["no_speech_threshold"],
            initial_prompt=self.cfg["initial_prompt"] or None,
        )
        text = collapse_repeats("".join(seg.text for seg in segments).strip())
        if text.lower() in self.blacklist:
            log(f"Отброшено как галлюцинация: {text!r}")
            return ""
        return text
