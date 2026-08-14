"""Движок распознавания: подготовка CUDA, загрузка модели и транскрипция."""

import os
import re

import numpy as np

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

    def transcribe(self, audio, language, vad_filter=None):
        """Распознаёт аудио (numpy float32 16кГц или путь к файлу).

        Порог no_speech отдаём самой модели: свой грубый отсев сегментов выбрасывал куски
        длинной речи и пения (обрывал текст). Тишину отсекает vad_filter, мусорные фразы —
        hallucination_blacklist."""
        vad_filter = self.cfg.get("vad_filter", True) if vad_filter is None else bool(vad_filter)
        text = self._transcribe_once(audio, language, vad_filter)
        text = self._merge_tail_retranscription(text, audio, language, vad_filter)
        if text.lower() in self.blacklist:
            log(f"Отброшено как галлюцинация: {text!r}")
            return ""
        return text

    def _transcribe_once(self, audio, language, vad_filter):
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
            vad_filter=vad_filter,
            no_speech_threshold=self.cfg["no_speech_threshold"],
            initial_prompt=self.cfg["initial_prompt"] or None,
        )
        text = collapse_repeats("".join(seg.text for seg in segments).strip())
        return text

    def _merge_tail_retranscription(self, text, audio, language, vad_filter):
        if not self.cfg.get("tail_retranscribe_enabled", True):
            return text
        if not isinstance(audio, np.ndarray) or audio.size == 0:
            return text
        duration = audio.size / 16000.0
        min_duration = float(self.cfg.get("tail_retranscribe_min_seconds", 35.0))
        if duration < min_duration:
            return text
        tail_seconds = float(self.cfg.get("tail_retranscribe_seconds", 25.0))
        tail_samples = int(tail_seconds * 16000)
        if tail_samples <= 0 or audio.size <= tail_samples:
            return text
        tail_audio = audio[-tail_samples:]
        tail_text = self._transcribe_once(tail_audio, language, vad_filter)
        merged = _merge_text_tail(text, tail_text)
        if merged != text:
            log(f"Хвост распознавания дополнен: {tail_text!r}")
        return merged


def _merge_text_tail(text, tail_text):
    text = (text or "").strip()
    tail_text = (tail_text or "").strip()
    if not text:
        return tail_text
    if not tail_text:
        return text
    text_norm = _overlap_norm(text)
    tail_norm = _overlap_norm(tail_text)
    best = 0
    max_len = min(len(text_norm), len(tail_norm))
    for size in range(max_len, 19, -1):
        if text_norm[-size:] == tail_norm[:size]:
            best = size
            break
    if best == 0:
        return text
    consumed = _chars_for_norm_prefix(tail_text, best)
    mid_word = (
        consumed > 0
        and consumed < len(tail_text)
        and _is_word_char(tail_text[consumed - 1])
        and _is_word_char(tail_text[consumed])
    )
    suffix = tail_text[consumed:] if mid_word else tail_text[consumed:].lstrip(" ,.!?;:…")
    if not suffix:
        return text
    if mid_word:
        return f"{text}{suffix}"
    if text[-1:] and text[-1] not in " \n":
        return f"{text} {suffix}"
    return f"{text}{suffix}"


def _overlap_norm(value):
    return re.sub(r"[^0-9a-zа-яё]+", "", value.lower())


def _chars_for_norm_prefix(value, norm_count):
    count = 0
    for index, ch in enumerate(value):
        if re.match(r"[0-9a-zа-яё]", ch.lower()):
            count += 1
            if count >= norm_count:
                return index + 1
    return len(value)


def _is_word_char(value):
    return bool(re.match(r"[0-9a-zа-яё]", value.lower()))
