"""
Установщик VoiceService.

Создаёт виртуальное окружение в ../runtime/.venv и ставит туда зависимости
из requirements.txt. Запускать обычным Python 3.10+:

    python install.py

После установки запуск:
    Windows : run.bat   (или  ..\runtime\.venv\Scripts\pythonw.exe voiceservice.py)
    Linux/mac: ../runtime/.venv/bin/python voiceservice.py
"""

import os
import subprocess
import sys
import venv

APP_DIR = os.path.dirname(os.path.abspath(__file__))      # .../application
ROOT_DIR = os.path.dirname(APP_DIR)                       # корень репозитория
RUNTIME_DIR = os.path.join(ROOT_DIR, "runtime")
VENV_DIR = os.path.join(RUNTIME_DIR, ".venv")
REQUIREMENTS = os.path.join(APP_DIR, "requirements.txt")


def venv_python(venv_dir):
    if os.name == "nt":
        return os.path.join(venv_dir, "Scripts", "python.exe")
    return os.path.join(venv_dir, "bin", "python")


def run(cmd):
    print(">", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    if sys.version_info < (3, 10):
        sys.exit(f"Нужен Python 3.10+, а запущен {sys.version.split()[0]}.")

    os.makedirs(RUNTIME_DIR, exist_ok=True)

    if not os.path.isfile(venv_python(VENV_DIR)):
        print(f"Создаю виртуальное окружение: {VENV_DIR}")
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    else:
        print(f"Окружение уже есть: {VENV_DIR}")

    py = venv_python(VENV_DIR)
    print("Обновляю pip...")
    run([py, "-m", "pip", "install", "--upgrade", "pip"])
    print("Ставлю зависимости (это может занять несколько минут)...")
    run([py, "-m", "pip", "install", "-r", REQUIREMENTS])

    run_hint = (
        "run.bat" if os.name == "nt"
        else f"{os.path.relpath(py, ROOT_DIR)} application/voiceservice.py"
    )
    print("\nГотово! Запуск:")
    print(f"  {run_hint}")
    print("При первом запуске модель (~1.5 ГБ) скачается автоматически.")


if __name__ == "__main__":
    try:
        main()
    except subprocess.CalledProcessError as e:
        sys.exit(f"Команда завершилась с ошибкой ({e.returncode}). Установка прервана.")
