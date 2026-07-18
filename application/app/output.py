"""Вставка распознанного текста в активное поле."""

import time

import pyperclip
from pynput import keyboard


class Inserter:
    """Вставляет текст: через буфер обмена (по умолчанию) или эмуляцией набора."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.kb = keyboard.Controller()
        # True, пока шлём синтетические нажатия — чтобы слушатель хоткеев не принял
        # наш собственный Ctrl+V за «другую клавишу» и не отменил новую диктовку.
        self.busy = False

    def insert(self, text):
        self.busy = True
        try:
            self._insert(text)
        finally:
            self.busy = False

    def _insert(self, text):
        if self.cfg["insert_method"] == "type":
            self.kb.type(text)
            return
        # Буфер обмена + Ctrl+V. Прежнее содержимое НЕ восстанавливаем намеренно:
        # иначе при потере фокуса (свернулось окно, всплыло окно) текст стирался и
        # пропадал совсем. Теперь он остаётся в буфере — доступен повторным Ctrl+V и в Win+V.
        pyperclip.copy(text)
        time.sleep(0.03)
        with self.kb.pressed(keyboard.Key.ctrl):
            self.kb.press("v")
            self.kb.release("v")
