"""
Самопроверка VoiceService без микрофона и трея.

  python selftest.py            # только быстрые тесты логики (хоткеи, конфиг, импорты)
  python selftest.py --model    # + загрузка модели и распознавание тишины (медленно)

Тест логики хоткеев гоняет HotkeyManager синтетическими событиями клавиш и проверяет,
что PTT отменяется при нажатии другой клавиши, а toggle переключает запись.
"""

import os
import sys
import time

for _stream in (sys.stdout, sys.stderr):
    try:
        if _stream is not None:
            _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# tests/ лежит внутри application/ — добавляем application/ в путь, чтобы найти пакет app.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pynput import keyboard

from app.config import DEFAULT_CONFIG, load_config
from app.hotkeys import HotkeyManager, key_to_name


class FakeCallbacks:
    def __init__(self):
        self.events = []
        self.ignore = False

    def on_ptt_start(self):  self.events.append("start")
    def on_ptt_commit(self): self.events.append("commit")
    def on_ptt_cancel(self): self.events.append("cancel")
    def on_toggle(self):     self.events.append("toggle")
    def on_read_selection(self): self.events.append("read_selection")
    def ignore_keys(self):   return self.ignore


CTRL_R = keyboard.Key.ctrl_r
SCROLL = keyboard.Key.scroll_lock
KEY_A = keyboard.KeyCode.from_char("a")
KEY_V = keyboard.KeyCode.from_char("v")
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


def new_mgr_with_read_selection():
    cb = FakeCallbacks()
    return HotkeyManager(
        "ctrl_r",
        "scroll_lock",
        cb,
        read_selection_key="ctrl_r",
        read_selection_double_tap=True,
        read_selection_double_tap_seconds=0.45,
        read_selection_max_tap_seconds=0.25,
    ), cb


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


def test_own_paste_does_not_cancel():
    print("test: своя вставка (Ctrl+V) не отменяет диктовку")
    mgr, cb = new_mgr()
    mgr.on_press(CTRL_R)          # пользователь начал диктовать
    cb.ignore = True              # приложение шлёт свой Ctrl+V
    mgr.on_press(KEY_V)
    mgr.on_release(KEY_V)
    cb.ignore = False             # вставка закончилась
    mgr.on_release(CTRL_R)
    check("события = [start, commit] (без cancel)", cb.events == ["start", "commit"])

    print("test: чужая клавиша по-прежнему отменяет")
    mgr, cb = new_mgr()
    mgr.on_press(CTRL_R)
    mgr.on_press(KEY_V)           # ignore=False → это шорткат Ctrl+V пользователя
    mgr.on_release(CTRL_R)
    check("есть cancel, нет commit", cb.events == ["start", "cancel"])


def test_toggle():
    print("test: Scroll Lock -> toggle на каждое нажатие")
    mgr, cb = new_mgr()
    mgr.on_press(SCROLL)
    mgr.on_release(SCROLL)
    mgr.on_press(SCROLL)
    mgr.on_release(SCROLL)
    check("два toggle", cb.events == ["toggle", "toggle"])


def test_double_tap_reads_selection():
    print("test: двойной короткий правый Ctrl -> чтение выделенного")
    mgr, cb = new_mgr_with_read_selection()
    mgr.on_press(CTRL_R)
    mgr.on_release(CTRL_R)
    time.sleep(0.05)
    mgr.on_press(CTRL_R)
    mgr.on_release(CTRL_R)
    check(
        "второй тап отменяет PTT и вызывает read_selection",
        cb.events == ["start", "commit", "start", "cancel", "read_selection"],
    )


def test_collapse_repeats():
    print("test: схлопывание зацикленных повторов")
    from app.engine import collapse_repeats

    # Реальные случаи пользователя
    junk1 = "ьные предметные действия " + "1." * 100 + " в под ко"
    out1 = collapse_repeats(junk1)
    check("«1.1.1.…» схлопнулось", len(out1) < 60 and "предметные действия" in out1)

    junk2 = "в конце я протянул " + "и" * 200
    out2 = collapse_repeats(junk2)
    check("«ииии…» ×200 схлопнулось", len(out2) < 40 and out2.startswith("в конце"))

    # Нормальный текст не должен пострадать
    ok = "Привет, это обычная фраза с многоточием... и продолжением."
    check("обычный текст не тронут", collapse_repeats(ok) == ok)
    check("пустая строка ок", collapse_repeats("") == "")


def test_recordings_cache():
    print("test: кэш последних записей диктовки")
    import shutil, tempfile, wave
    import numpy as np
    from app.files import save_recording

    folder = os.path.join(tempfile.gettempdir(), "vs_rec_test")
    shutil.rmtree(folder, ignore_errors=True)
    tone = (0.2 * np.sin(np.linspace(0, 100, 16000))).astype(np.float32)

    paths = []
    for _ in range(4):
        p = save_recording(folder, tone, 16000, keep=3)
        if p:
            paths.append(p)
        time.sleep(1.05)   # имена по секундам — разводим во времени

    check("файлы созданы", len(paths) == 4)
    left = os.listdir(folder)
    check("хранится только keep=3", len(left) == 3)
    check("самый старый удалён", os.path.basename(paths[0]) not in left)

    with wave.open(paths[-1], "rb") as w:
        check("WAV: моно 16 кГц", w.getnchannels() == 1 and w.getframerate() == 16000)
        check("WAV: есть данные", w.getnframes() == 16000)

    check("keep=0 отключает", save_recording(folder, tone, 16000, keep=0) is None)
    shutil.rmtree(folder, ignore_errors=True)


def test_chunking():
    print("test: нарезка длинной диктовки по тишине")
    import numpy as np
    from app.chunking import should_cut
    from app.config import DEFAULT_CONFIG, SAMPLE_RATE

    cfg = dict(DEFAULT_CONFIG)
    cfg["chunk_min_seconds"] = 10.0
    cfg["chunk_max_seconds"] = 30.0
    cfg["chunk_silence_seconds"] = 0.4
    cfg["chunk_silence_rms"] = 0.012

    speech_9s = np.full(int(9 * SAMPLE_RATE), 0.04, dtype=np.float32)
    check("до min_seconds не режет", not should_cut(speech_9s, cfg))

    speech = np.full(int(11 * SAMPLE_RATE), 0.04, dtype=np.float32)
    silence = np.zeros(int(0.8 * SAMPLE_RATE), dtype=np.float32)
    check("после min_seconds режет на паузе", should_cut(np.concatenate((speech, silence)), cfg))

    no_pause = np.full(int(12 * SAMPLE_RATE), 0.04, dtype=np.float32)
    check("без паузы не режет раньше max", not should_cut(no_pause, cfg))

    long_no_pause = np.full(int(31 * SAMPLE_RATE), 0.04, dtype=np.float32)
    check("max_seconds режет даже без паузы", should_cut(long_no_pause, cfg))


def test_window_import():
    print("test: окно управления")
    import app.window  # noqa
    check("window импортируется", True)


def test_tts_import():
    print("test: TTS модуль")
    import app.tts  # noqa
    check("tts импортируется", True)


def test_history():
    print("test: история последних распознаваний")
    import collections
    from app.service import VoiceService
    svc = VoiceService.__new__(VoiceService)          # без загрузки модели
    svc.history = collections.deque(maxlen=10)
    for i in range(13):
        svc.remember(f"фраза {i}")
    svc.remember("")                                   # пустое не запоминаем
    check("хранит максимум 10", len(svc.history) == 10)
    check("новые первыми", svc.history[0] == "фраза 12")
    check("пустое не попало", "" not in svc.history)


def test_config():
    print("test: конфиг")
    cfg = load_config()
    check("ptt_key=ctrl_r", cfg["ptt_key"] == "ctrl_r")
    check("toggle_key=scroll_lock", cfg["toggle_key"] == "scroll_lock")
    check("есть ptt_beep_delay", "ptt_beep_delay" in cfg)
    check("есть file_insert_at_cursor", "file_insert_at_cursor" in cfg)
    check("есть inbox_keep_processed", "inbox_keep_processed" in cfg)
    check("chunking включен по умолчанию", cfg["toggle_chunking_enabled"] is True)
    check("chunk partial insert включен по умолчанию", cfg["chunk_insert_partials"] is True)
    check("chunk separator = пробел", cfg["chunk_insert_separator"] == " ")
    check("tts_provider есть", "tts_provider" in cfg)
    check("tts_volume есть", "tts_volume" in cfg)
    check("tts_piper_exe есть", "tts_piper_exe" in cfg)
    check("tts_silero_model есть", "tts_silero_model" in cfg)
    check("tts_yandex_voice есть", "tts_yandex_voice" in cfg)
    check("tts_google_lang есть", "tts_google_lang" in cfg)
    check("read_selected_key есть", "read_selected_key" in cfg)


def test_imports():
    print("test: импорт всех модулей")
    import app.capture, app.engine, app.files, app.output, app.service, app.tray, app.tts  # noqa
    import sounddevice, pyperclip, pystray  # noqa
    from PIL import Image  # noqa
    check("все модули импортированы", True)


def test_model():
    print("test: загрузка модели + распознавание тишины и файла")
    import os, tempfile, wave
    import numpy as np
    from app.engine import Transcriber, load_model
    cfg = dict(DEFAULT_CONFIG)
    cfg["model"] = "small"
    model, device = load_model(cfg)
    tr = Transcriber(model, cfg)
    out = tr.transcribe(np.zeros(16000, dtype=np.float32), "auto")
    check(f"модель на {device}, тишина (массив) -> пусто", out == "")

    # Распознавание ПО ПУТИ К ФАЙЛУ (тихий WAV) — проверяем тракт работы с файлами.
    p = os.path.join(tempfile.gettempdir(), "vs_silent.wav")
    with wave.open(p, "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x00\x00" * 16000)
    out_file = tr.transcribe(p, "auto")
    check("файл по пути -> пусто (без ошибок)", out_file == "")


def main():
    test_imports()
    test_key_names()
    test_ptt_clean()
    test_ptt_cancel_by_other_key()
    test_ptt_cancel_once()
    test_own_paste_does_not_cancel()
    test_toggle()
    test_double_tap_reads_selection()
    test_collapse_repeats()
    test_recordings_cache()
    test_chunking()
    test_window_import()
    test_tts_import()
    test_history()
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
