"""Small Tkinter control window opened from the tray."""

import threading
import tkinter as tk
from tkinter import ttk

import pyperclip

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
    root.geometry("760x460")
    root.minsize(560, 340)

    status_var = tk.StringVar()
    count_var = tk.StringVar()

    frame = ttk.Frame(root, padding=12)
    frame.pack(fill=tk.BOTH, expand=True)

    top = ttk.Frame(frame)
    top.pack(fill=tk.X)
    ttk.Label(top, textvariable=status_var).pack(side=tk.LEFT)
    ttk.Label(top, textvariable=count_var).pack(side=tk.RIGHT)

    listbox = tk.Listbox(frame, activestyle="dotbox", exportselection=False)
    listbox.pack(fill=tk.BOTH, expand=True, pady=(10, 8))

    buttons = ttk.Frame(frame)
    buttons.pack(fill=tk.X)

    def selected_text():
        selection = listbox.curselection()
        if not selection:
            return ""
        texts = list(listbox.full_texts)
        index = selection[0]
        return texts[index] if index < len(texts) else ""

    def copy_selected():
        text = selected_text()
        if text:
            try:
                pyperclip.copy(text)
            except Exception as e:
                log(f"Не удалось скопировать результат из окна: {e}")

    ttk.Button(buttons, text="Копировать", command=copy_selected).pack(side=tk.LEFT)
    ttk.Button(buttons, text="Обновить", command=lambda: _refresh(service, status_var, count_var, listbox)).pack(
        side=tk.LEFT, padx=(8, 0)
    )
    ttk.Button(buttons, text="Закрыть", command=root.destroy).pack(side=tk.RIGHT)

    listbox.full_texts = []
    _refresh(service, status_var, count_var, listbox)

    def tick():
        if _window is root:
            _refresh(service, status_var, count_var, listbox)
            root.after(1000, tick)

    root.after(1000, tick)
    root.protocol("WM_DELETE_WINDOW", root.destroy)
    root.mainloop()
    if _window is root:
        _window = None


def _refresh(service, status_var, count_var, listbox):
    status_var.set(f"Статус: {service.status}")
    history = list(service.history)
    count_var.set(f"Текстов в текущем запуске: {len(history)}")
    current_selection = listbox.curselection()
    selected = current_selection[0] if current_selection else None
    listbox.delete(0, tk.END)
    listbox.full_texts = history
    if not history:
        listbox.insert(tk.END, "(пока нет результатов в текущем запуске)")
        return
    for text in history:
        preview = " ".join(text.split())
        if len(preview) > 140:
            preview = preview[:137] + "..."
        listbox.insert(tk.END, preview)
    if selected is not None and selected < len(history):
        listbox.selection_set(selected)
