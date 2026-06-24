"""
Живой тест распознавания с микрофона.

Запуск:
    .\.venv\Scripts\python.exe mic_test.py

Для каждой фразы: жмёшь Enter → читаешь вслух → снова Enter (стоп).
Скрипт распознаёт сказанное и в конце сохраняет сравнение «эталон / распознано»
в файл mic_test_result.txt (UTF-8).

Совет: перед запуском закрой работающее приложение (иконка в трее → «Выход»),
чтобы не делить микрофон и видеопамять.
"""

import os
import sys

# tests/ лежит внутри application/ — добавляем application/ в путь, чтобы найти пакет app.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.capture import Recorder
from app.config import DEFAULT_CONFIG, RUNTIME_DIR
from app.engine import Transcriber, load_model

# Фразы подобраны со «сложными» звуками, но это НЕ скороговорки.
PHRASES = [
    ("ru", "В четверг мы обсуждали ежемесячный отчёт и решили перенести встречу на девятое число."),
    ("ru", "Дождь шумел всю ночь, а утром свежий ветер принёс запах хвои и мокрой щепы."),
    ("ru", "Программист исправил ошибку в двадцати трёх файлах и запустил тесты заново."),
    ("en", "On Thursday the weather changed quickly, and three thousand visitors crowded the southern square."),
    ("en", "She thought the algorithm was thorough enough, although it threw an unexpected error twice."),
    ("en", "We've rescheduled the meeting to eleven thirty, right after the quarterly review."),
]

os.makedirs(RUNTIME_DIR, exist_ok=True)
RESULT_PATH = os.path.join(RUNTIME_DIR, "mic_test_result.txt")


def record_one(recorder):
    """Пишет, пока пользователь не нажмёт Enter; возвращает аудио."""
    recorder.start()
    input("   ▶ читай фразу, по окончании нажми Enter...")
    return recorder.stop()


def normalize(s):
    return "".join(c.lower() for c in s if c.isalnum() or c.isspace()).split()


def word_match(expected, got):
    e, g = normalize(expected), normalize(got)
    if not e:
        return 0.0
    common = 0
    gg = list(g)
    for w in e:
        if w in gg:
            gg.remove(w)
            common += 1
    return 100.0 * common / len(e)


def main():
    print("Загрузка модели (medium)...")
    cfg = dict(DEFAULT_CONFIG)
    model, device = load_model(cfg)
    tr = Transcriber(model, cfg)
    recorder = Recorder()
    print(f"Модель на {device}. Поехали!\n")

    results = []
    for i, (lang, text) in enumerate(PHRASES, 1):
        print(f"[{i}/{len(PHRASES)}] ({'рус' if lang == 'ru' else 'eng'}) ЭТАЛОН:")
        print(f"   {text}")
        input("   нажми Enter и читай...")
        audio = record_one(recorder)
        got = tr.transcribe(audio, lang)
        score = word_match(text, got)
        print(f"   РАСПОЗНАНО: {got}")
        print(f"   совпадение слов: {score:.0f}%\n")
        results.append((lang, text, got, score))

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        for i, (lang, text, got, score) in enumerate(results, 1):
            f.write(f"[{i}] ({lang}) совпадение слов: {score:.0f}%\n")
            f.write(f"  ЭТАЛОН:    {text}\n")
            f.write(f"  РАСПОЗНАНО: {got}\n\n")
        avg = sum(r[3] for r in results) / len(results)
        f.write(f"Среднее совпадение слов: {avg:.0f}%\n")

    print(f"Готово. Результат сохранён: {RESULT_PATH}")
    print("Скажи мне — я прочитаю файл и сравню.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
