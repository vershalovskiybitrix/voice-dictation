"""Вставка распознанного текста в активное поле."""

import time

import pyperclip
from pynput import keyboard


class Inserter:
    """Вставляет текст: через буфер обмена (по умолчанию) или эмуляцией набора."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.kb = keyboard.Controller()

    def insert(self, text):
        if self.cfg["insert_method"] == "type":
            self.kb.type(text)
            return
        # Буфер обмена + Ctrl+V с восстановлением прежнего содержимого.
        try:
            old = pyperclip.paste()
        except Exception:
            old = None
        pyperclip.copy(text)
        time.sleep(0.03)
        with self.kb.pressed(keyboard.Key.ctrl):
            self.kb.press("v")
            self.kb.release("v")
        if old is not None:
            time.sleep(0.15)
            try:
                pyperclip.copy(old)
            except Exception:
                pass
