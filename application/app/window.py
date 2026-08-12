"""Tkinter control window opened from the tray."""

import threading
import tkinter as tk
from tkinter import ttk

import pyperclip

from .tts import list_sapi_voices
from .util import log

_window = None
_thread = None


def open_control_window(service):
    """Open or focus the control window without blocking the tray loop."""
    global _thread
    if _thread is not None and _thread.is_alive():
        try:
            if _window is not None:
                _window.after(0, _raise_window)
        except Exception as e:
            log(f"Не удалось активировать окно: {e}")
        return
    _thread = threading.Thread(target=_run_window, args=(service,), daemon=True)
    _thread.start()


def _raise_window():
    if _window is None:
        return
    _window.deiconify()
    _window.lift()
    _window.focus_force()


def _run_window(service):
    global _window
    root = tk.Tk()
    _window = root
    root.title("VoiceService")
    root.geometry("860x620")
    root.minsize(720, 500)

    app = SettingsWindow(root, service)
    app.pack(fill=tk.BOTH, expand=True)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    if _window is root:
        _window = None


class SettingsWindow(ttk.Frame):
    def __init__(self, master, service):
        super().__init__(master, padding=12)
        self.service = service
        self.vars = {}
        self.history_list = None
        self.status_var = tk.StringVar()
        self.count_var = tk.StringVar()
        self.sapi_voices = []

        self._build_header()
        self._build_tabs()
        self._refresh()
        self.after(1000, self._tick)

    def _build_header(self):
        header = ttk.Frame(self)
        header.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header, textvariable=self.status_var).pack(side=tk.LEFT)
        ttk.Label(header, textvariable=self.count_var).pack(side=tk.RIGHT)

    def _build_tabs(self):
        tabs = ttk.Notebook(self)
        tabs.pack(fill=tk.BOTH, expand=True)
        tabs.add(self._tab_results(tabs), text="Результаты")
        tabs.add(self._tab_dictation(tabs), text="Диктовка")
        tabs.add(self._tab_files(tabs), text="Файлы")
        tabs.add(self._tab_tts(tabs), text="Читалка")
        tabs.add(self._tab_providers(tabs), text="Провайдеры")

    def _tab_results(self, parent):
        frame = ttk.Frame(parent, padding=10)
        self.history_list = tk.Listbox(frame, activestyle="dotbox", exportselection=False)
        self.history_list.pack(fill=tk.BOTH, expand=True)
        self.history_list.full_texts = []
        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Копировать", command=self._copy_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Прочитать", command=self._speak_selected).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Обновить", command=self._refresh).pack(side=tk.LEFT, padx=(8, 0))
        return frame

    def _tab_dictation(self, parent):
        frame = ttk.Frame(parent, padding=10)
        self._combo(frame, "Язык", "language", ["auto", "ru", "en"], row=0)
        self._check(frame, "Звуковой сигнал", "beep", row=1)
        self._number(frame, "Минимальная запись, сек", "min_record_seconds", row=2, width=8)
        ttk.Separator(frame).grid(row=3, column=0, columnspan=3, sticky="ew", pady=10)
        self._check(frame, "Нарезать Scroll Lock по паузам", "toggle_chunking_enabled", row=4)
        self._number(frame, "Минимум до нарезки, сек", "chunk_min_seconds", row=5, width=8)
        self._number(frame, "Максимум куска, сек", "chunk_max_seconds", row=6, width=8)
        self._number(frame, "Пауза для резки, сек", "chunk_silence_seconds", row=7, width=8)
        self._number(frame, "Порог тишины RMS", "chunk_silence_rms", row=8, width=8)
        self._check(frame, "Вставлять куски сразу", "chunk_insert_partials", row=9)
        self._text(frame, "Разделитель кусков", "chunk_insert_separator", row=10, width=8)
        frame.columnconfigure(1, weight=1)
        return frame

    def _tab_files(self, parent):
        frame = ttk.Frame(parent, padding=10)
        self._check(frame, "Вставлять результат файла в курсор", "file_insert_at_cursor", row=0)
        self._text(frame, "Папка-приёмник", "inbox_dirname", row=1)
        self._number(frame, "Хранить обработанных файлов", "inbox_keep_processed", row=2, width=8)
        self._number(frame, "Хранить последних аудиозаписей", "keep_recordings", row=3, width=8)
        frame.columnconfigure(1, weight=1)
        return frame

    def _tab_tts(self, parent):
        frame = ttk.Frame(parent, padding=10)
        self._combo(frame, "Провайдер чтения", "tts_provider", ["sapi", "piper", "silero", "rhvoice", "yandex"], row=0)
        voices = [""] + self._load_sapi_voices()
        self._combo(frame, "SAPI голос", "tts_voice", voices, row=1)
        self._number(frame, "Скорость SAPI (-10..10)", "tts_rate", row=2, width=8)
        self._number(frame, "Громкость SAPI (0..100)", "tts_volume", row=3, width=8)
        buttons = ttk.Frame(frame)
        buttons.grid(row=4, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Button(buttons, text="Прочитать буфер", command=self.service.speak_clipboard).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Тестовая фраза", command=self._speak_test).pack(side=tk.LEFT, padx=(8, 0))
        frame.columnconfigure(1, weight=1)
        return frame

    def _tab_providers(self, parent):
        frame = ttk.Frame(parent, padding=10)
        ttk.Label(frame, text="Локальные TTS-кандидаты").grid(row=0, column=0, columnspan=2, sticky="w")
        self._text(frame, "Piper model path", "tts_piper_model", row=1)
        self._text(frame, "Silero speaker", "tts_silero_speaker", row=2)
        self._text(frame, "Robot/fun preset", "tts_robot_preset", row=3)
        ttk.Separator(frame).grid(row=4, column=0, columnspan=3, sticky="ew", pady=10)
        ttk.Label(frame, text="Yandex TTS").grid(row=5, column=0, columnspan=2, sticky="w")
        self._text(frame, "Yandex voice", "tts_yandex_voice", row=6)
        self._text(frame, "Yandex role", "tts_yandex_role", row=7)
        self._number(frame, "Yandex speed", "tts_yandex_speed", row=8, width=8)
        frame.columnconfigure(1, weight=1)
        return frame

    def _load_sapi_voices(self):
        if not self.sapi_voices:
            self.sapi_voices = list_sapi_voices()
        return self.sapi_voices

    def _get_var(self, key):
        if key not in self.vars:
            self.vars[key] = tk.StringVar(value=str(self.service.cfg.get(key, "")))
        return self.vars[key]

    def _save_var(self, key, caster=str):
        var = self._get_var(key)
        try:
            value = caster(var.get())
        except ValueError:
            return
        self.service.update_setting(key, value)

    def _text(self, frame, label, key, row, width=34):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(frame, textvariable=self._get_var(key), width=width)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        entry.bind("<FocusOut>", lambda _e: self._save_var(key))
        entry.bind("<Return>", lambda _e: self._save_var(key))

    def _number(self, frame, label, key, row, width=10):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(frame, textvariable=self._get_var(key), width=width)
        entry.grid(row=row, column=1, sticky="w", pady=4)
        entry.bind("<FocusOut>", lambda _e: self._save_var(key, _number_cast))
        entry.bind("<Return>", lambda _e: self._save_var(key, _number_cast))

    def _combo(self, frame, label, key, values, row):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(frame, textvariable=self._get_var(key), values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._save_var(key))

    def _check(self, frame, label, key, row):
        var = tk.BooleanVar(value=bool(self.service.cfg.get(key, False)))
        self.vars[key] = var

        def save():
            self.service.update_setting(key, bool(var.get()))

        ttk.Checkbutton(frame, text=label, variable=var, command=save).grid(
            row=row, column=0, columnspan=2, sticky="w", pady=4
        )

    def _selected_text(self):
        if self.history_list is None:
            return ""
        selection = self.history_list.curselection()
        if not selection:
            return ""
        texts = list(self.history_list.full_texts)
        index = selection[0]
        return texts[index] if index < len(texts) else ""

    def _copy_selected(self):
        text = self._selected_text()
        if text:
            try:
                pyperclip.copy(text)
            except Exception as e:
                log(f"Не удалось скопировать результат из окна: {e}")

    def _speak_selected(self):
        text = self._selected_text()
        if text:
            self.service.speak_text(text)

    def _speak_test(self):
        self.service.speak_text("Проверка чтения VoiceService. Один, два, три.")

    def _tick(self):
        self._refresh()
        self.after(1000, self._tick)

    def _refresh(self):
        self.status_var.set(f"Статус: {self.service.status}")
        history = list(self.service.history)
        self.count_var.set(f"Текстов в текущем запуске: {len(history)}")
        if self.history_list is None:
            return
        current_selection = self.history_list.curselection()
        selected = current_selection[0] if current_selection else None
        self.history_list.delete(0, tk.END)
        self.history_list.full_texts = history
        if not history:
            self.history_list.insert(tk.END, "(пока нет результатов в текущем запуске)")
            return
        for text in history:
            preview = " ".join(text.split())
            if len(preview) > 140:
                preview = preview[:137] + "..."
            self.history_list.insert(tk.END, preview)
        if selected is not None and selected < len(history):
            self.history_list.selection_set(selected)


def _number_cast(value):
    value = value.strip()
    if "." in value:
        return float(value)
    return int(value)
