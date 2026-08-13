"""Оркестрация: состояние записи, реакции на хоткеи, запуск трея."""

import collections
import json
import os
import threading
import time
import winsound

import numpy as np
import pyperclip
from pynput import keyboard

from .chunking import should_cut
from .capture import Recorder
from .config import RUNTIME_DIR, SAMPLE_RATE, inbox_dir, load_config, recordings_dir, save_config
from .engine import Transcriber, load_model
from .files import save_recording, watch_inbox
from .hotkeys import HotkeyManager
from .output import Inserter
from .tts import TtsError, TtsPlaybackController, provider_label
from .util import log


class VoiceService:
    """Связывает запись, распознавание и вставку; реагирует на события хоткеев."""

    def __init__(self, cfg, model, device):
        self.cfg = cfg
        self.device = device
        self.recorder = Recorder()
        self.transcriber = Transcriber(model, cfg)
        self.inserter = Inserter(cfg)

        self.language = cfg["language"]
        self.file_insert = cfg["file_insert_at_cursor"]
        self.paused = False
        self.recording = False
        self.mode = None              # "ptt" | "toggle" | None
        self.status = "Idle"
        self.tray = None
        # Последние результаты (новые первыми) — доступны из трея, если текст не попал в поле.
        self.history = collections.deque(maxlen=10)

        self._record_start = 0.0
        self._beep_timer = None
        self._lock = threading.RLock()
        self._infer_lock = threading.Lock()  # одно распознавание за раз (микрофон/файл) — щадим VRAM
        self._chunk_lock = threading.Lock()
        self._chunk_buffer = np.zeros(0, dtype=np.float32)
        self._chunk_thread = None
        self._keys_busy = False
        self._kb = keyboard.Controller()
        self.tts_playback = TtsPlaybackController()

    # ------------------------------------------------------------------ #
    #  Индикация
    # ------------------------------------------------------------------ #
    def set_status(self, s):
        self.status = s
        log(f"Статус: {s}")
        if self.tray is not None:
            self.tray.title = f"VoiceService [{self.device}] — {s}"

    def beep(self, start):
        if not self.cfg["beep"]:
            return
        try:
            winsound.Beep(880 if start else 520, 90)
        except Exception:
            pass

    def _cancel_timer(self):
        if self._beep_timer is not None:
            self._beep_timer.cancel()
            self._beep_timer = None

    def _delayed_start_beep(self):
        with self._lock:
            if self.recording and self.mode == "ptt":
                self.beep(True)

    # ------------------------------------------------------------------ #
    #  Жизненный цикл записи
    # ------------------------------------------------------------------ #
    def _begin(self, mode):
        with self._lock:
            if self.paused or self.recording:
                return
            try:
                self.recorder.start()
            except Exception as e:
                log(f"Не удалось открыть микрофон: {e}")
                return
            self.recording = True
            self.mode = mode
            self._record_start = time.time()
            self.set_status("Recording")
            if mode == "ptt":
                # Сигнал «пишу» с задержкой — чтобы не пищать на Ctrl-шорткаты.
                self._cancel_timer()
                self._beep_timer = threading.Timer(
                    self.cfg["ptt_beep_delay"], self._delayed_start_beep
                )
                self._beep_timer.daemon = True
                self._beep_timer.start()
            else:
                self.beep(True)
            if mode == "toggle" and self.cfg.get("toggle_chunking_enabled", False):
                self._start_chunking()

    def _cancel(self, mode):
        with self._lock:
            if not self.recording or self.mode != mode:
                return
            self._cancel_timer()
            self.recording = False
            self.mode = None
            if mode == "toggle":
                self._stop_chunking()
            self.recorder.discard()
            self._clear_chunk_buffer()
            self.set_status("Idle")
        log("Ввод отменён (нажата другая клавиша).")

    def _commit(self, mode):
        with self._lock:
            if not self.recording or self.mode != mode:
                return
            self._cancel_timer()
            self.recording = False
            self.mode = None
            duration = time.time() - self._record_start
            if mode == "toggle":
                self._stop_chunking()
            audio = self.recorder.stop()
            if mode == "toggle":
                audio = self._drain_chunk_buffer(audio)

        if duration < self.cfg["min_record_seconds"] or audio.size == 0:
            log("Слишком короткая запись — игнор.")
            self.set_status("Idle")
            return
        self.beep(False)
        # Сохраняем запись, чтобы при сбое распознавания её можно было переиграть из трея.
        save_recording(recordings_dir(), audio, SAMPLE_RATE, self.cfg["keep_recordings"])
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _start_chunking(self):
        self._clear_chunk_buffer()
        self._chunk_thread = threading.Thread(target=self._chunk_loop, daemon=True)
        self._chunk_thread.start()

    def _stop_chunking(self):
        thread = self._chunk_thread
        self._chunk_thread = None
        if thread is not None and thread.is_alive():
            thread.join(timeout=1.0)

    def _clear_chunk_buffer(self):
        with self._chunk_lock:
            self._chunk_buffer = np.zeros(0, dtype=np.float32)

    def _append_chunk_audio(self, audio):
        if audio is None or audio.size == 0:
            return
        with self._chunk_lock:
            if self._chunk_buffer.size == 0:
                self._chunk_buffer = audio
            else:
                self._chunk_buffer = np.concatenate((self._chunk_buffer, audio))

    def _drain_chunk_buffer(self, tail):
        with self._chunk_lock:
            buffered = self._chunk_buffer
            self._chunk_buffer = np.zeros(0, dtype=np.float32)
        if buffered.size == 0:
            return tail
        if tail is None or tail.size == 0:
            return buffered
        return np.concatenate((buffered, tail))

    def _chunk_loop(self):
        poll = float(self.cfg.get("chunk_poll_seconds", 0.25))
        while True:
            time.sleep(poll)
            with self._lock:
                active = self.recording and self.mode == "toggle"
            if not active:
                return
            self._append_chunk_audio(self.recorder.read_available())
            with self._chunk_lock:
                if not should_cut(self._chunk_buffer, self.cfg):
                    continue
                audio = self._chunk_buffer
                self._chunk_buffer = np.zeros(0, dtype=np.float32)
            if audio.size < int(self.cfg["min_record_seconds"] * SAMPLE_RATE):
                continue
            save_recording(recordings_dir(), audio, SAMPLE_RATE, self.cfg["keep_recordings"])
            threading.Thread(target=self._process, args=(audio, True), daemon=True).start()

    def _process(self, audio, partial=False):
        self.set_status("Transcribing" if not partial else "Transcribing chunk")
        try:
            with self._infer_lock:
                text = self.transcriber.transcribe(audio, self.language)
        except Exception as e:
            log(f"Ошибка распознавания: {e}")
            self.set_status("Idle")
            return
        if text:
            log(f"Распознано: {text!r}")
            self.remember(text)
            if not partial or self.cfg.get("chunk_insert_partials", False):
                insert_text = text
                if partial:
                    insert_text = self._prepare_partial_text(insert_text)
                    insert_text += self.cfg.get("chunk_insert_separator", " ")
                self.inserter.insert(insert_text)
            elif partial:
                try:
                    pyperclip.copy(self._prepare_partial_text(text) + self.cfg.get("chunk_insert_separator", " "))
                except Exception:
                    pass
        else:
            log("Пустой результат — ничего не вставлено.")
        with self._lock:
            still_recording = self.recording
        self.set_status("Recording" if still_recording else "Idle")

    # ------------------------------------------------------------------ #
    #  Распознавание аудиофайлов
    # ------------------------------------------------------------------ #
    def _notify(self, message, title="VoiceService"):
        try:
            if self.tray is not None:
                self.tray.notify(message, title)
        except Exception:
            pass

    def set_file_insert(self, value):
        self.file_insert = value
        self.cfg["file_insert_at_cursor"] = value
        save_config(self.cfg)

    def update_setting(self, key, value):
        self.cfg[key] = value
        if key == "language":
            self.language = value
        elif key == "file_insert_at_cursor":
            self.file_insert = bool(value)
        save_config(self.cfg)

    def speak_text(self, text):
        if not text or not text.strip():
            self._notify("Не вижу текст для чтения.", "VoiceService TTS")
            return
        provider = self.cfg.get("tts_provider", "yandex")
        self.set_status(f"Speaking: {provider}")
        log(f"TTS start: {provider_label(provider)}")
        try:
            self.tts_playback.speak(text, self.cfg)
        except TtsError as e:
            log(f"Ошибка чтения: {e}")
            self._notify(str(e), "VoiceService TTS")
        except Exception as e:
            log(f"Неожиданная ошибка чтения: {e}")
            self._notify(str(e), "VoiceService TTS")
        finally:
            self.set_status("Recording" if self.recording else "Idle")

    def speak_clipboard(self):
        try:
            text = pyperclip.paste()
        except Exception as e:
            log(f"Ошибка чтения буфера: {e}")
            self._notify(str(e), "VoiceService TTS")
            return
        if not text.strip():
            self._notify("Буфер пуст.", "VoiceService TTS")
            return
        self.speak_text(text)

    def stop_speaking(self):
        log("TTS stop")
        self.tts_playback.stop()
        self.set_status("Recording" if self.recording else "Idle")

    def speak_selection(self):
        threading.Thread(target=self._speak_selection_worker, daemon=True).start()

    def _speak_selection_worker(self):
        try:
            text = self._copy_selection_text()
        except Exception as e:
            log(f"Ошибка чтения выделения: {e}")
            self._notify(str(e), "VoiceService TTS")
            return
        if not text.strip():
            self._notify("Не вижу выделенный текст.", "VoiceService TTS")
            return
        self.speak_text(text)

    def _copy_selection_text(self):
        marker = f"__VOICE_SERVICE_SELECTION_{time.time_ns()}__"
        try:
            old_clipboard = pyperclip.paste()
        except Exception:
            old_clipboard = ""
        self._keys_busy = True
        try:
            pyperclip.copy(marker)
            time.sleep(0.03)
            with self._kb.pressed(keyboard.Key.ctrl):
                self._kb.press("c")
                self._kb.release("c")
            time.sleep(float(self.cfg.get("read_selected_copy_delay_seconds", 0.12)))
            selected = pyperclip.paste()
            pyperclip.copy(old_clipboard)
        finally:
            self._keys_busy = False
        if selected == marker:
            return ""
        return selected

    def quit_cleanly(self):
        if self.tray is not None:
            try:
                self.tray.visible = False
            except Exception:
                pass
            try:
                self.tray.stop()
            except Exception:
                pass

    def handle_file(self, path):
        """Распознаёт аудиофайл (любой источник) → буфер (+ опц. вставка) + уведомление."""
        name = os.path.basename(path)
        self.set_status(f"Файл: {name}")
        try:
            with self._infer_lock:
                text = self.transcriber.transcribe(path, self.language)
        except Exception as e:
            log(f"Ошибка распознавания файла {name!r}: {e}")
            self._notify(f"Не удалось распознать: {name}")
            self.set_status("Idle")
            return
        if not text:
            log(f"Файл {name!r}: пустой результат.")
            self._notify(f"Речь не распознана: {name}")
            self.set_status("Idle")
            return
        log(f"Файл {name!r} распознан: {text!r}")
        self.remember(text)
        try:
            pyperclip.copy(text)
        except Exception:
            pass
        if self.file_insert:
            self.inserter.insert(text)
        preview = text if len(text) <= 200 else text[:197] + "..."
        self._notify(preview, f"Распознано: {name}")
        self.set_status("Idle")

    # ------------------------------------------------------------------ #
    #  Колбэки HotkeyManager
    # ------------------------------------------------------------------ #
    def remember(self, text):
        """Кладёт результат в историю (новые первыми)."""
        if text:
            self.history.appendleft(text)
            self._persist_history_text(text)

    def _persist_history_text(self, text):
        try:
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            path = os.path.join(RUNTIME_DIR, "recognition_history.jsonl")
            lines = []
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8-sig") as f:
                    lines = [line for line in f.read().splitlines() if line.strip()]
            lines.append(json.dumps({"ts": time.time(), "text": text}, ensure_ascii=False))
            keep = int(getattr(self, "cfg", {}).get("history_persist_count", 50))
            if keep > 0:
                lines = lines[-keep:]
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
        except Exception as e:
            log(f"Не удалось сохранить историю распознаваний: {e}")

    def _prepare_partial_text(self, text):
        if not self.cfg.get("chunk_strip_trailing_ellipsis", True):
            return text
        stripped = text.rstrip()
        while stripped.endswith("…"):
            stripped = stripped[:-1].rstrip()
        while stripped.endswith("..."):
            stripped = stripped[:-3].rstrip()
        return stripped

    def ignore_keys(self):
        """Игнорировать клавиши, пока сами шлём Ctrl+V (иначе отменим свою же диктовку)."""
        return self.inserter.busy or self._keys_busy

    def on_ptt_start(self):
        self._begin("ptt")

    def on_ptt_commit(self):
        self._commit("ptt")

    def on_ptt_cancel(self):
        self._cancel("ptt")

    def on_toggle(self):
        if self.recording and self.mode == "toggle":
            self._commit("toggle")
        elif not self.recording:
            self._begin("toggle")

    def on_read_selection(self):
        self.speak_selection()

    def on_stop_tts(self):
        self.stop_speaking()


def run():
    """Точка входа: грузит модель, поднимает хоткеи и трей."""
    cfg = load_config()
    log("Запуск VoiceService...")
    model, device = load_model(cfg)
    service = VoiceService(cfg, model, device)

    hotkeys = HotkeyManager(
        cfg["ptt_key"],
        cfg["toggle_key"],
        service,
        read_selection_key=cfg.get("read_selected_key"),
        read_selection_double_tap=cfg.get("read_selected_double_tap", True),
        read_selection_double_tap_seconds=cfg.get("read_selected_double_tap_seconds", 0.45),
        read_selection_max_tap_seconds=cfg.get("read_selected_max_tap_seconds", 0.25),
        stop_tts_triple_tap=cfg.get("tts_stop_triple_tap", True),
    )
    threading.Thread(target=hotkeys.run, daemon=True).start()
    log(
        f"Готово. PTT: держать [{cfg['ptt_key']}] | Toggle: [{cfg['toggle_key']}] | "
        f"Read selection: двойной тап [{cfg.get('read_selected_key', '')}]"
    )

    # Слежение за папкой-приёмником: бросил аудиофайл → распознался.
    folder = inbox_dir(cfg)
    keep = cfg.get("inbox_keep_processed", 20)
    threading.Thread(
        target=watch_inbox, args=(folder, service.handle_file, keep), daemon=True
    ).start()

    from .tray import build_tray  # импорт здесь: pystray тянет GUI-зависимости
    icon = build_tray(service)
    service.set_status("Idle")
    icon.run()
