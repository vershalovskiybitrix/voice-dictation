"""Оркестрация: состояние записи, реакции на хоткеи, запуск трея."""

import threading
import time
import winsound

from .capture import Recorder
from .config import load_config
from .engine import Transcriber, load_model
from .hotkeys import HotkeyManager
from .output import Inserter
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
        self.paused = False
        self.recording = False
        self.mode = None              # "ptt" | "toggle" | None
        self.status = "Idle"
        self.tray = None

        self._record_start = 0.0
        self._beep_timer = None
        self._lock = threading.RLock()

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

    def _cancel(self, mode):
        with self._lock:
            if not self.recording or self.mode != mode:
                return
            self._cancel_timer()
            self.recording = False
            self.mode = None
            self.recorder.discard()
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
            audio = self.recorder.stop()

        if duration < self.cfg["min_record_seconds"] or audio.size == 0:
            log("Слишком короткая запись — игнор.")
            self.set_status("Idle")
            return
        self.beep(False)
        threading.Thread(target=self._process, args=(audio,), daemon=True).start()

    def _process(self, audio):
        self.set_status("Transcribing")
        try:
            text = self.transcriber.transcribe(audio, self.language)
        except Exception as e:
            log(f"Ошибка распознавания: {e}")
            self.set_status("Idle")
            return
        if text:
            log(f"Распознано: {text!r}")
            self.inserter.insert(text)
        else:
            log("Пустой результат — ничего не вставлено.")
        self.set_status("Idle")

    # ------------------------------------------------------------------ #
    #  Колбэки HotkeyManager
    # ------------------------------------------------------------------ #
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


def run():
    """Точка входа: грузит модель, поднимает хоткеи и трей."""
    cfg = load_config()
    log("Запуск VoiceService...")
    model, device = load_model(cfg)
    service = VoiceService(cfg, model, device)

    hotkeys = HotkeyManager(cfg["ptt_key"], cfg["toggle_key"], service)
    threading.Thread(target=hotkeys.run, daemon=True).start()
    log(f"Готово. PTT: держать [{cfg['ptt_key']}] | Toggle: [{cfg['toggle_key']}]")

    from .tray import build_tray  # импорт здесь: pystray тянет GUI-зависимости
    icon = build_tray(service)
    service.set_status("Idle")
    icon.run()
