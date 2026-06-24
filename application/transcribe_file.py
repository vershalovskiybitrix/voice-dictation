"""
Добавить аудиофайл(ы) в очередь распознавания работающего приложения.

    python transcribe_file.py <аудиофайл> [ещё файлы...]

Копирует файлы в папку-приёмник runtime/inbox — их подхватит запущенное приложение
(модель уже в памяти, результат почти мгновенный). Оригиналы остаются на месте.
Удобно повесить на «Открыть с помощью» в Проводнике.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.config import inbox_dir, load_config
from app.files import AUDIO_EXTS


def main(argv):
    if not argv:
        print("Использование: python transcribe_file.py <аудиофайл> [...]")
        return 1

    folder = inbox_dir(load_config())
    os.makedirs(folder, exist_ok=True)

    added = 0
    for src in argv:
        if not os.path.isfile(src):
            print(f"Пропущен (не файл): {src}")
            continue
        if os.path.splitext(src)[1].lower() not in AUDIO_EXTS:
            print(f"Пропущен (не аудио): {src}")
            continue
        base, ext = os.path.splitext(os.path.basename(src))
        dst = os.path.join(folder, base + ext)
        i = 1
        while os.path.exists(dst):
            dst = os.path.join(folder, f"{base}_{i}{ext}")
            i += 1
        shutil.copy2(src, dst)
        print(f"В очередь: {os.path.basename(dst)}")
        added += 1

    if added:
        print(f"Добавлено: {added}. Распознавание идёт в работающем приложении (значок в трее).")
    else:
        print("Нечего добавить.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
