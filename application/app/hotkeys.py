"""Глобальные хоткеи: PTT с отменой по любой другой клавише + toggle."""

import time

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

    Read selected text:
      - двойной короткий тап read_selection_key → on_read_selection.
        По умолчанию это тот же правый Ctrl; удержание продолжает работать как PTT.
    """

    def __init__(
        self,
        ptt_key,
        toggle_key,
        callbacks,
        read_selection_key=None,
        read_selection_double_tap=True,
        read_selection_double_tap_seconds=0.45,
        read_selection_max_tap_seconds=0.25,
    ):
        self.ptt_key = ptt_key
        self.toggle_key = toggle_key
        self.read_selection_key = read_selection_key
        self.read_selection_double_tap = read_selection_double_tap
        self.read_selection_double_tap_seconds = float(read_selection_double_tap_seconds)
        self.read_selection_max_tap_seconds = float(read_selection_max_tap_seconds)
        self.cb = callbacks
        self._ptt_down = False
        self._ptt_dirty = False
        self._ptt_press_time = None
        self._last_read_key_tap = None

    def _ignore(self):
        """Пока приложение само шлёт клавиши (вставка Ctrl+V) — не реагируем на них."""
        fn = getattr(self.cb, "ignore_keys", None)
        return bool(fn()) if fn else False

    def on_press(self, key):
        if self._ignore():
            return
        name = key_to_name(key)
        if name == self.ptt_key:
            if not self._ptt_down:
                self._ptt_down = True
                self._ptt_dirty = False
                self._ptt_press_time = time.monotonic()
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
        if self._ignore():
            return
        name = key_to_name(key)
        if name == self.ptt_key and self._ptt_down:
            self._ptt_down = False
            now = time.monotonic()
            press_time = self._ptt_press_time or now
            self._ptt_press_time = None
            if self._is_read_selection_double_tap(name, now, now - press_time):
                self._last_read_key_tap = None
                self.cb.on_ptt_cancel()
                fn = getattr(self.cb, "on_read_selection", None)
                if fn:
                    fn()
                return
            if self._is_read_selection_tap(name, now - press_time):
                self._last_read_key_tap = now
            if not self._ptt_dirty:
                self.cb.on_ptt_commit()

    def _is_read_selection_tap(self, name, duration):
        return (
            self.read_selection_double_tap
            and self.read_selection_key
            and name == self.read_selection_key
            and duration <= self.read_selection_max_tap_seconds
        )

    def _is_read_selection_double_tap(self, name, now, duration):
        if not self._is_read_selection_tap(name, duration):
            return False
        if self._last_read_key_tap is None:
            return False
        return now - self._last_read_key_tap <= self.read_selection_double_tap_seconds

    def run(self):
        """Блокирующий цикл прослушивания (запускать в отдельном потоке)."""
        with keyboard.Listener(on_press=self.on_press, on_release=self.on_release) as listener:
            listener.join()
