"""
Самопроверка VoiceService без микрофона и трея.

  python selftest.py            # только быстрые тесты логики (хоткеи, конфиг, импорты)
  python selftest.py --model    # + загрузка модели и распознавание тишины (медленно)

Тест логики хоткеев гоняет HotkeyManager синтетическими событиями клавиш и проверяет,
что PTT отменяется при нажатии другой клавиши, а toggle переключает запись.
"""

import os
import sys

# tests/ лежит внутри application/ — добавляем application/ в путь, чтобы найти пакет app.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pynput import keyboard

from app.config import DEFAULT_CONFIG, load_config
from app.hotkeys import HotkeyManager, key_to_name


class FakeCallbacks:
    def __init__(self):
        self.events = []

    def on_ptt_start(self):  self.events.append("start")
    def on_ptt_commit(self): self.events.append("commit")
    def on_ptt_cancel(self): self.events.append("cancel")
    def on_toggle(self):     self.events.append("toggle")


CTRL_R = keyboard.Key.ctrl_r
SCROLL = keyboard.Key.scroll_lock
KEY_A = keyboard.KeyCode.from_char("a")
KEY_HOME = keyboard.Key.home


def check(name, cond):
    print(f"  [{'OK ' if cond else 'FAIL'}] {name}")
    if not cond:
        check.failed += 1
check.failed = 0


def test_key_names():
    print("test: key_to_name")
    check("ctrl_r -> 'ctrl_r'", key_to_name(CTRL_R) == "ctrl_r")
    check("scroll_lock -> 'scroll_lock'", key_to_name(SCROLL) == "scroll_lock")
    check("'A' -> 'a'", key_to_name(KEY_A) == "a")


def new_mgr():
    cb = FakeCallbacks()
    return HotkeyManager("ctrl_r", "scroll_lock", cb), cb


def test_ptt_clean():
    print("test: чистый PTT (зажал-отпустил) -> start, commit")
    mgr, cb = new_mgr()
    mgr.on_press(CTRL_R)
    mgr.on_release(CTRL_R)
    check("события = [start, commit]", cb.events == ["start", "commit"])


def test_ptt_cancel_by_other_key():
    print("test: PTT + другая клавиша (Ctrl+Home) -> start, cancel, без commit")
    mgr, cb = new_mgr()
    mgr.on_press(CTRL_R)
    mgr.on_press(KEY_HOME)     # шорткат
    mgr.on_release(KEY_HOME)
    mgr.on_release(CTRL_R)
    check("события = [start, cancel]", cb.events == ["start", "cancel"])
    check("нет commit", "commit" not in cb.events)


def test_ptt_cancel_once():
    print("test: несколько других клавиш -> cancel ровно один раз")
    mgr, cb = new_mgr()
    mgr.on_press(CTRL_R)
    mgr.on_press(KEY_A)
    mgr.on_press(KEY_HOME)
    mgr.on_release(CTRL_R)
    check("cancel ровно один", cb.events.count("cancel") == 1)
    check("нет commit", "commit" not in cb.events)


def test_toggle():
    print("test: Scroll Lock -> toggle на каждое нажатие")
    mgr, cb = new_mgr()
    mgr.on_press(SCROLL)
    mgr.on_release(SCROLL)
    mgr.on_press(SCROLL)
    mgr.on_release(SCROLL)
    check("два toggle", cb.events == ["toggle", "toggle"])


def test_config():
    print("test: конфиг")
    cfg = load_config()
    check("ptt_key=ctrl_r", cfg["ptt_key"] == "ctrl_r")
    check("toggle_key=scroll_lock", cfg["toggle_key"] == "scroll_lock")
    check("есть ptt_beep_delay", "ptt_beep_delay" in cfg)


def test_imports():
    print("test: импорт всех модулей")
    import app.capture, app.engine, app.output, app.service, app.tray  # noqa
    import sounddevice, pyperclip, pystray  # noqa
    from PIL import Image  # noqa
    check("все модули импортированы", True)


def test_model():
    print("test: загрузка модели + распознавание тишины")
    import numpy as np
    from app.engine import Transcriber, load_model
    cfg = dict(DEFAULT_CONFIG)
    cfg["model"] = "small"
    model, device = load_model(cfg)
    tr = Transcriber(model, cfg)
    out = tr.transcribe(np.zeros(16000, dtype=np.float32), "auto")
    check(f"модель на {device}, тишина -> пусто", out == "")


def main():
    test_imports()
    test_key_names()
    test_ptt_clean()
    test_ptt_cancel_by_other_key()
    test_ptt_cancel_once()
    test_toggle()
    test_config()
    if "--model" in sys.argv:
        test_model()
    print()
    if check.failed:
        print(f"ПРОВАЛЕНО тестов: {check.failed}")
        sys.exit(1)
    print("Все тесты пройдены.")


if __name__ == "__main__":
    main()
