# Читалки VoiceService

## Рабочие провайдеры

- `piper`: локальный Piper в `runtime/tts/piper`. После фикса stdin текст передаётся в `piper.exe` как UTF-8.
- `silero`: локальный русский Silero. PyTorch Hub cache и модель должны лежать в `runtime/tts/silero`, а не в профиле пользователя на диске C. `v5_ru` рассчитан на русский текст; английский надо отдавать другому провайдеру или отдельной EN-модели.
- `yandex`: Yandex SpeechKit. Секреты читаются из `.env`; голоса и роли выбираются из списков.

## Тестовые / проблемные

- `google_old`: тестовый прямой Google Translate TTS. В текущем endpoint нет нормального выбора голоса, пола или preset; скорость меняется локальной постобработкой WAV.

## Yandex SpeechKit

Текущий код использует API v1 `speech/v1/tts:synthesize`, поэтому в настройках показываются только русские голоса из документации Yandex, у которых есть версия v1:

- `alena`: `neutral`, `good`
- `filipp`: без роли
- `ermil`: `neutral`, `good`
- `jane`: `neutral`, `good`, `evil`
- `omazh`: `neutral`, `evil`
- `zahar`: `neutral`, `good`
- `marina`: `neutral`, `whisper`, `friendly`
- `madi_ru`: без роли

## Проверка

```powershell
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --status
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider piper "Проверка Piper."
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider silero "Проверка Silero."
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider yandex "Проверка Yandex."
```

## Yandex `.env`

```text
YANDEX_CLOUD_API_KEY
YANDEX_CLOUD_FOLDER_ID
```

Значения не хранить в Markdown и не коммитить.
