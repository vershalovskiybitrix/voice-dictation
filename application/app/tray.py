"""Иконка и меню в системном трее."""

import os
import threading

import pyperclip

from .config import inbox_dir, recordings_dir
from .files import pick_audio_file
from .util import log
from .window import open_control_window


def make_icon_image():
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (64, 64), (30, 30, 40))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([26, 12, 38, 40], radius=6, fill=(120, 200, 255))
    d.arc([20, 24, 44, 48], start=0, end=180, fill=(120, 200, 255), width=3)
    d.line([32, 48, 32, 56], fill=(120, 200, 255), width=3)
    d.line([24, 56, 40, 56], fill=(120, 200, 255), width=3)
    return img


def build_tray(service):
    import pystray
    from pystray import MenuItem as Item

    def set_lang(lang):
        def _set(icon, item):
            service.language = lang
            log(f"Язык переключён: {lang}")
        return _set

    def lang_checked(lang):
        return lambda item: service.language == lang

    def toggle_pause(icon, item):
        service.paused = not service.paused
        service.set_status("Paused" if service.paused else "Idle")

    def open_window(icon, item):
        open_control_window(service)

    def recognize_file(icon, item):
        def _run():
            path = pick_audio_file()
            if path:
                service.handle_file(path)
        threading.Thread(target=_run, daemon=True).start()

    def open_inbox(icon, item):
        folder = inbox_dir(service.cfg)
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)
        except Exception as e:
            log(f"Не удалось открыть папку: {e}")

    def toggle_file_insert(icon, item):
        service.set_file_insert(not service.file_insert)

    def copy_text(text):
        def _copy(icon, item):
            try:
                pyperclip.copy(text)
            except Exception as e:
                log(f"Не удалось скопировать в буфер: {e}")
        return _copy

    def retranscribe(path):
        def _run(icon, item):
            threading.Thread(target=service.handle_file, args=(path,), daemon=True).start()
        return _run

    def recording_items():
        folder = recordings_dir()
        try:
            names = sorted(os.listdir(folder), reverse=True)
        except OSError:
            names = []
        if not names:
            return [Item("(пока нет записей)", None, enabled=False)]
        return [Item(n[:-4], retranscribe(os.path.join(folder, n))) for n in names]

    def open_recordings(icon, item):
        folder = recordings_dir()
        os.makedirs(folder, exist_ok=True)
        try:
            os.startfile(folder)
        except Exception as e:
            log(f"Не удалось открыть папку записей: {e}")

    def history_items():
        if not service.history:
            return [Item("(пусто)", None, enabled=False)]
        items = []
        for text in service.history:
            preview = " ".join(text.split())
            if len(preview) > 60:
                preview = preview[:57] + "..."
            items.append(Item(preview, copy_text(text)))
        return items

    def do_quit(icon, item):
        service.quit_cleanly()
        os._exit(0)

    menu = pystray.Menu(
        Item("Открыть окно", open_window, default=True),
        Item(lambda item: f"Статус: {service.status}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item("Язык: Авто", set_lang("auto"), checked=lang_checked("auto"), radio=True),
        Item("Язык: Русский", set_lang("ru"), checked=lang_checked("ru"), radio=True),
        Item("Язык: English", set_lang("en"), checked=lang_checked("en"), radio=True),
        pystray.Menu.SEPARATOR,
        Item("Последние тексты текущего запуска (клик — в буфер)", pystray.Menu(history_items)),
        Item("Последние аудиозаписи (клик — перераспознать)", pystray.Menu(recording_items)),
        Item("Открыть папку записей", open_recordings),
        pystray.Menu.SEPARATOR,
        Item("Распознать аудиофайл…", recognize_file),
        Item("Открыть папку для распознавания", open_inbox),
        Item("Вставлять результат файла в курсор", toggle_file_insert,
             checked=lambda item: service.file_insert),
        pystray.Menu.SEPARATOR,
        Item("Пауза хоткеев", toggle_pause, checked=lambda item: service.paused),
        Item("Выход", do_quit),
    )
    icon = pystray.Icon("VoiceService", make_icon_image(), "VoiceService", menu)
    service.tray = icon
    return icon
