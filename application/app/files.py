"""Работа с аудиофайлами: выбор файла (нативный диалог) и папка-приёмник."""

import ctypes
import os
import shutil
import time
from ctypes import wintypes

from .util import log

# Форматы, которые умеет декодировать PyAV (включая голосовые мессенджеров).
AUDIO_EXTS = {
    ".ogg", ".opus", ".oga", ".mp3", ".m4a", ".aac", ".wav",
    ".flac", ".wma", ".webm", ".mp4", ".mka", ".amr", ".3gp",
}


# --------------------------------------------------------------------------- #
#  Нативный диалог открытия файла (comdlg32.GetOpenFileNameW)
# --------------------------------------------------------------------------- #
class _OPENFILENAME(ctypes.Structure):
    _fields_ = [
        ("lStructSize", wintypes.DWORD),
        ("hwndOwner", wintypes.HWND),
        ("hInstance", wintypes.HINSTANCE),
        ("lpstrFilter", wintypes.LPCWSTR),
        ("lpstrCustomFilter", wintypes.LPWSTR),
        ("nMaxCustFilter", wintypes.DWORD),
        ("nFilterIndex", wintypes.DWORD),
        ("lpstrFile", wintypes.LPWSTR),
        ("nMaxFile", wintypes.DWORD),
        ("lpstrFileTitle", wintypes.LPWSTR),
        ("nMaxFileTitle", wintypes.DWORD),
        ("lpstrInitialDir", wintypes.LPCWSTR),
        ("lpstrTitle", wintypes.LPCWSTR),
        ("Flags", wintypes.DWORD),
        ("nFileOffset", wintypes.WORD),
        ("nFileExtension", wintypes.WORD),
        ("lpstrDefExt", wintypes.LPCWSTR),
        ("lCustData", wintypes.LPARAM),
        ("lpfnHook", wintypes.LPVOID),
        ("lpTemplateName", wintypes.LPCWSTR),
        ("pvReserved", wintypes.LPVOID),
        ("dwReserved", wintypes.DWORD),
        ("FlagsEx", wintypes.DWORD),
    ]


def pick_audio_file():
    """Показывает системный диалог выбора аудиофайла. Возвращает путь или None."""
    exts = ";".join("*" + e for e in sorted(AUDIO_EXTS))
    # Пары строк, разделённые \0, с двойным \0 в конце.
    flt = f"Аудиофайлы\0{exts}\0Все файлы\0*.*\0\0"
    buf = ctypes.create_unicode_buffer(2048)

    ofn = _OPENFILENAME()
    ofn.lStructSize = ctypes.sizeof(_OPENFILENAME)
    ofn.lpstrFilter = flt
    ofn.lpstrFile = ctypes.cast(buf, wintypes.LPWSTR)
    ofn.nMaxFile = len(buf)
    ofn.lpstrTitle = "Выберите аудиофайл для распознавания"
    # OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR | OFN_EXPLORER
    ofn.Flags = 0x1000 | 0x0800 | 0x0008 | 0x00080000

    try:
        ok = ctypes.windll.comdlg32.GetOpenFileNameW(ctypes.byref(ofn))
    except Exception as e:
        log(f"Не удалось открыть диалог выбора файла: {e}")
        return None
    return buf.value if ok else None


# --------------------------------------------------------------------------- #
#  Папка-приёмник: бросил файл → распознался
# --------------------------------------------------------------------------- #
def _retire(path, done_dir, keep):
    """Убирает обработанный файл: при keep<=0 удаляет, иначе переносит в done и подрезает."""
    if keep <= 0:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    os.makedirs(done_dir, exist_ok=True)
    base, ext = os.path.splitext(os.path.basename(path))
    dest = os.path.join(done_dir, base + ext)
    i = 1
    while os.path.exists(dest):
        dest = os.path.join(done_dir, f"{base}_{i}{ext}")
        i += 1
    try:
        shutil.move(path, dest)
    except OSError as e:
        log(f"Не удалось переместить обработанный файл: {e}")
        return
    # Подрезаем done/ до keep последних по времени изменения.
    files = [os.path.join(done_dir, f) for f in os.listdir(done_dir)]
    files = [f for f in files if os.path.isfile(f)]
    files.sort(key=os.path.getmtime, reverse=True)
    for old in files[keep:]:
        try:
            os.remove(old)
        except OSError:
            pass


def watch_inbox(folder, on_file, keep, poll=1.0):
    """Фоновый цикл: новые аудиофайлы в folder → on_file(path) → убираем в done/."""
    os.makedirs(folder, exist_ok=True)
    done_dir = os.path.join(folder, "done")
    seen_sizes = {}
    log(f"Слежу за папкой-приёмником: {folder}")
    while True:
        try:
            for name in os.listdir(folder):
                path = os.path.join(folder, name)
                if not os.path.isfile(path):
                    continue
                if os.path.splitext(name)[1].lower() not in AUDIO_EXTS:
                    continue
                size = os.path.getsize(path)
                # Ждём, пока файл допишется (размер стабилен между опросами).
                if seen_sizes.get(path) != size:
                    seen_sizes[path] = size
                    continue
                seen_sizes.pop(path, None)
                try:
                    on_file(path)
                finally:
                    _retire(path, done_dir, keep)
        except Exception as e:
            log(f"Ошибка слежения за папкой: {e}")
        time.sleep(poll)
