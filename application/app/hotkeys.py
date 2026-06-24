"""Глобальные хоткеи: PTT с отменой по любой другой клавише + toggle."""

from pynput import keyboard


def key_to_name(key):
    """Канонизированное имя клавиши pynput для сравнения с конфигом."""
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char.lower()
        return f"vk{key.vk}"
    if isinstance(key, keyboard.Key):
        return key.name
    return str(key)


class HotkeyManager:
    """Чистая логика хоткеев (без таймеров/звука — их держит сервис).

    callbacks — объект с методами on_ptt_start / on_ptt_commit / on_ptt_cancel / on_toggle.

    PTT (ptt_key):
      - нажатие → on_ptt_start (началась запись);
      - если пока PTT удерживается нажата ЛЮБАЯ другая клавиша → on_ptt_cancel
        (это шорткат вроде Ctrl+Home — ввод отменяется, ничего не вставляется);
      - отпускание без «грязи» → on_ptt_commit (распознать и вставить).

    Toggle (toggle_key): каждое нажатие → on_toggle.
    """

    def __init__(self, ptt_key, toggle_key, callbacks):
        self.ptt_key = ptt_key
        self.toggle_key = toggle_key
        self.cb = callbacks
        self._ptt_down = False
        self._ptt_dirty = False

    def on_press(self, key):
        name = key_to_name(key)
        if name == self.ptt_key:
            if not self._ptt_down:
                self._ptt_down = True
                self._ptt_dirty = False
                self.cb.on_ptt_start()
            return
        if name == self.toggle_key:
            self.cb.on_toggle()
            return
        # Любая другая клавиша во время удержания PTT — это шорткат, отменяем ввод.
        if self._ptt_down and not self._ptt_dirty:
            self._ptt_dirty = True
            self.cb.on_ptt_cancel()

    def on_release(self, key):
        name = key_to_name(key)
        if name == self.ptt_key and self._ptt_down:
            self._ptt_down = False
            if not self._ptt_dirty:
                self.cb.on_ptt_commit()

    def run(self):
        """Блокирующий цикл прослушивания (запускать в отдельном потоке)."""
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()
