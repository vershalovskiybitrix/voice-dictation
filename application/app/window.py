"""Tkinter control window opened from the tray."""

import threading
import tkinter as tk
from tkinter import ttk

import pyperclip

from .tts import (
    SILERO_SPEAKERS,
    YANDEX_VOICES,
    list_sapi_voices,
    provider_label,
    provider_value,
    providers_status,
)
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
    root.geometry("920x660")
    root.minsize(760, 540)

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
        self.tts_settings_frame = None
        self.tts_status_var = tk.StringVar()
        self.provider_status_text = None

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
        tabs.add(self._tab_connections(tabs), text="Подключения")

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
        self._combo(frame, "Способ распознавания", "speech_recognition_provider", ["whisper", "yandex", "both"], row=0)
        self._combo(frame, "Модель Whisper", "model", ["small", "medium", "large-v3"], row=1)
        self._combo(frame, "Устройство", "device", ["auto", "cuda", "cpu"], row=2)
        self._combo(frame, "Язык", "language", ["auto", "ru", "en"], row=3)
        self._number(frame, "Beam size", "beam_size", row=4, width=8)
        self._number(frame, "Порог тишины Whisper", "no_speech_threshold", row=5, width=8)
        self._text(frame, "Подсказка слов", "initial_prompt", row=6, width=58)
        self._check(frame, "Звуковой сигнал", "beep", row=7)
        self._number(frame, "Минимальная запись, сек", "min_record_seconds", row=8, width=8)
        ttk.Separator(frame).grid(row=9, column=0, columnspan=3, sticky="ew", pady=10)
        self._check(frame, "Нарезать Scroll Lock по паузам", "toggle_chunking_enabled", row=10)
        self._number(frame, "Минимум до нарезки, сек", "chunk_min_seconds", row=11, width=8)
        self._number(frame, "Максимум куска, сек", "chunk_max_seconds", row=12, width=8)
        self._number(frame, "Пауза для резки, сек", "chunk_silence_seconds", row=13, width=8)
        self._number(frame, "Порог тишины RMS", "chunk_silence_rms", row=14, width=8)
        self._check(frame, "Вставлять куски сразу", "chunk_insert_partials", row=15)
        self._text(frame, "Разделитель кусков", "chunk_insert_separator", row=16, width=8)
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

        provider_frame = ttk.LabelFrame(frame, text="Провайдер чтения")
        provider_frame.grid(row=0, column=0, sticky="ew")
        provider_frame.columnconfigure(1, weight=1)
        provider_values = [provider_label(v) for v in ("sapi", "piper", "silero", "yandex", "google_old")]
        provider_var = tk.StringVar(value=provider_label(self.service.cfg.get("tts_provider", "sapi")))
        self.vars["tts_provider_label"] = provider_var
        ttk.Label(provider_frame, text="Читалка").grid(row=0, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(provider_frame, textvariable=provider_var, values=provider_values, state="readonly")
        combo.grid(row=0, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: self._save_tts_provider())

        self.tts_settings_frame = ttk.Frame(provider_frame)
        self.tts_settings_frame.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        self.tts_settings_frame.columnconfigure(1, weight=1)

        ttk.Label(provider_frame, textvariable=self.tts_status_var).grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        buttons = ttk.Frame(provider_frame)
        buttons.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))
        ttk.Button(buttons, text="Прочитать буфер", command=lambda: self._run_bg(self.service.speak_clipboard)).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Тестовая фраза", command=lambda: self._run_bg(self._speak_test)).pack(side=tk.LEFT, padx=(8, 0))

        hotkey_frame = ttk.LabelFrame(frame, text="Горячее чтение выделенного")
        hotkey_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        hotkey_frame.columnconfigure(1, weight=0)
        hotkey_frame.columnconfigure(3, weight=0)
        self._check(hotkey_frame, "Двойной тап читает выделенный текст", "read_selected_double_tap", row=0)
        self._text(hotkey_frame, "Клавиша", "read_selected_key", row=1, width=12, sticky="w")
        self._number(hotkey_frame, "Окно двойного тапа, сек", "read_selected_double_tap_seconds", row=0, column=2, width=8)
        self._number(hotkey_frame, "Максимум короткого тапа, сек", "read_selected_max_tap_seconds", row=1, column=2, width=8)

        frame.columnconfigure(0, weight=1)
        self._rebuild_tts_settings()
        return frame

    def _tab_connections(self, parent):
        frame = ttk.Frame(parent, padding=10)
        self.provider_status_text = tk.Text(frame, height=10, width=80, wrap="word")
        self.provider_status_text.pack(fill=tk.BOTH, expand=True)
        self.provider_status_text.configure(state="disabled")
        ttk.Button(frame, text="Обновить", command=self._refresh_provider_status).pack(anchor="w", pady=(8, 0))
        self.after(100, self._refresh_provider_status)
        return frame

    def _save_tts_provider(self):
        label = self.vars["tts_provider_label"].get()
        self.service.update_setting("tts_provider", provider_value(label))
        self._rebuild_tts_settings()

    def _rebuild_tts_settings(self):
        if self.tts_settings_frame is None:
            return
        for child in self.tts_settings_frame.winfo_children():
            child.destroy()
        provider = self.service.cfg.get("tts_provider", "sapi")
        self.tts_status_var.set(self._provider_status_line(provider))
        if provider == "sapi":
            self._combo(self.tts_settings_frame, "Голос Windows", "tts_voice", [""] + self._load_sapi_voices(), row=0)
            self._number(self.tts_settings_frame, "Темп речи (-10 медленно, 0 обычно, 10 быстро)", "tts_rate", row=1, width=8)
            self._number(self.tts_settings_frame, "Громкость, %", "tts_volume", row=2, width=8)
            return
        if provider == "piper":
            self._text(self.tts_settings_frame, "Piper.exe", "tts_piper_exe", row=0, width=58)
            self._text(self.tts_settings_frame, "Файл модели Piper (.onnx)", "tts_piper_model", row=1, width=58)
            return
        if provider == "silero":
            self._combo(self.tts_settings_frame, "Модель Silero", "tts_silero_model", ["v5_ru"], row=0)
            self._combo(self.tts_settings_frame, "Голос Silero", "tts_silero_speaker", SILERO_SPEAKERS, row=1)
            self._combo(self.tts_settings_frame, "Частота Silero", "tts_silero_sample_rate", ["48000", "24000", "8000"], row=2)
            return
        if provider == "yandex":
            voice = self.service.cfg.get("tts_yandex_voice", "alena")
            roles = YANDEX_VOICES.get(voice, ["neutral"])
            if self.service.cfg.get("tts_yandex_role", "") not in roles:
                self.service.update_setting("tts_yandex_role", roles[0])
                if "tts_yandex_role" in self.vars:
                    self.vars["tts_yandex_role"].set(roles[0])
            self._combo(
                self.tts_settings_frame,
                "Голос Yandex",
                "tts_yandex_voice",
                list(YANDEX_VOICES.keys()),
                row=0,
                on_selected=self._save_yandex_voice,
            )
            self._combo(self.tts_settings_frame, "Амплуа/роль", "tts_yandex_role", roles, row=1)
            self._number(self.tts_settings_frame, "Скорость", "tts_yandex_speed", row=2, width=8)
            return
        if provider == "google_old":
            self._combo(self.tts_settings_frame, "Язык Google", "tts_google_lang", ["ru", "en"], row=0)

    def _provider_status_line(self, provider):
        info = providers_status().get(provider)
        if not info:
            return ""
        if info["available"]:
            return f"Доступно: {info['detail']}"
        return f"Не подключено: {info['detail']}"

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
        if key.startswith("tts_"):
            self.tts_status_var.set(self._provider_status_line(self.service.cfg.get("tts_provider", "sapi")))

    def _text(self, frame, label, key, row, width=34, sticky="ew"):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        entry = ttk.Entry(frame, textvariable=self._get_var(key), width=width)
        entry.grid(row=row, column=1, sticky=sticky, pady=4)
        entry.bind("<FocusOut>", lambda _e: self._save_var(key))
        entry.bind("<Return>", lambda _e: self._save_var(key))

    def _number(self, frame, label, key, row, width=10, column=0):
        ttk.Label(frame, text=label).grid(row=row, column=column, sticky="w", pady=4, padx=(0 if column == 0 else 18, 0))
        entry = ttk.Entry(frame, textvariable=self._get_var(key), width=width)
        entry.grid(row=row, column=column + 1, sticky="w", pady=4)
        entry.bind("<FocusOut>", lambda _e: self._save_var(key, _number_cast))
        entry.bind("<Return>", lambda _e: self._save_var(key, _number_cast))

    def _combo(self, frame, label, key, values, row, on_selected=None):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
        combo = ttk.Combobox(frame, textvariable=self._get_var(key), values=values, state="readonly")
        combo.grid(row=row, column=1, sticky="ew", pady=4)
        combo.bind("<<ComboboxSelected>>", lambda _e: on_selected() if on_selected else self._save_var(key))

    def _save_yandex_voice(self):
        self._save_var("tts_yandex_voice")
        voice = self.service.cfg.get("tts_yandex_voice", "alena")
        roles = YANDEX_VOICES.get(voice, ["neutral"])
        if self.service.cfg.get("tts_yandex_role", "") not in roles:
            self.service.update_setting("tts_yandex_role", roles[0])
            if "tts_yandex_role" in self.vars:
                self.vars["tts_yandex_role"].set(roles[0])
        self._rebuild_tts_settings()

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
            self._run_bg(lambda: self.service.speak_text(text))

    def _speak_test(self):
        self.service.speak_text("Проверка чтения VoiceService. Один, два, три.")

    def _run_bg(self, fn):
        threading.Thread(target=fn, daemon=True).start()

    def _refresh_provider_status(self):
        if self.provider_status_text is None:
            return
        lines = []
        for name, info in providers_status().items():
            mark = "Доступно" if info["available"] else "Не подключено"
            lines.append(f"{info['label']}\n  {mark}: {info['detail']}")
        self.provider_status_text.configure(state="normal")
        self.provider_status_text.delete("1.0", tk.END)
        self.provider_status_text.insert("1.0", "\n\n".join(lines))
        self.provider_status_text.configure(state="disabled")

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
