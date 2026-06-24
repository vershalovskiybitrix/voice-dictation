"""Иконка и меню в системном трее."""

import os
import threading

from .config import inbox_dir
from .files import pick_audio_file
from .util import log


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

    def do_quit(icon, item):
        icon.stop()
        os._exit(0)

    menu = pystray.Menu(
        Item(lambda item: f"Статус: {service.status}", None, enabled=False),
        pystray.Menu.SEPARATOR,
        Item("Язык: Авто", set_lang("auto"), checked=lang_checked("auto"), radio=True),
        Item("Язык: Русский", set_lang("ru"), checked=lang_checked("ru"), radio=True),
        Item("Язык: English", set_lang("en"), checked=lang_checked("en"), radio=True),
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
