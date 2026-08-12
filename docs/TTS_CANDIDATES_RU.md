# Локальные и облачные читалки для VoiceService

## Текущий статус

- `sapi`: работает через Windows SAPI. Сейчас найдены голоса `Microsoft Irina Desktop - Russian` и `Microsoft Zira Desktop - English (United States)`.
- `piper`: подключён локально. Бинарник и модель лежат в `runtime/tts/piper`, активная модель: `ru_RU-irina-medium`.
- `silero`: подключён локально через PyTorch Hub. Активная модель: `v5_ru`, голоса: `aidar`, `baya`, `kseniya`, `eugene`, `xenia`.
- `yandex`: подключён через Yandex SpeechKit API v1. Секреты читаются из `.env`, в git не добавляются.
- `rhvoice`: отдельный `RHVoice-client` не найден. На Windows этот вариант разумнее использовать через SAPI-голоса, если RHVoice будет установлен в систему.
- `google_old`: подключён как экспериментальный robot/fun-режим через старый endpoint Google Translate TTS. Это не официальный Google Cloud TTS и может зависеть от доступности веб-сервиса.

## Проверка

```powershell
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --status
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider piper "Проверка Piper."
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider silero "Проверка Silero."
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider yandex "Проверка Yandex."
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider google_old "Проверка Google robot."
```

## Секреты

Yandex TTS использует только имена переменных:

```text
YANDEX_CLOUD_API_KEY
YANDEX_CLOUD_FOLDER_ID
```

Значения должны лежать в `runtime/.env` или корневом `.env`. В Markdown и git их не добавлять.

## Примечания

Piper сейчас самый простой локальный путь: маленький бинарник, отдельная ONNX-модель, без тяжёлого Python-стека.

Silero тяжелее: нужны `torch`, `soundfile`, `scipy`, `omegaconf`, а модель хранится в cache PyTorch Hub. Зато есть несколько русских голосов для сравнения.

Yandex нужен как облачный fallback и эталон качества. По умолчанию приложение оставлено на локальном провайдере, чтобы чтение не зависело от сети и денег.

Google-robot добавлен именно как забавный/ностальгический пресет. Для важных задач лучше сравнивать Piper, Silero и Yandex.
