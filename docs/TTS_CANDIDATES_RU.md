# Читалки VoiceService

## Рабочие провайдеры

- `piper`: локальный Piper в `runtime/tts/piper`. После фикса stdin текст передаётся в `piper.exe` как UTF-8.
- `yandex`: Yandex SpeechKit. Секреты читаются из `.env`; голоса и роли выбираются из списков.
- `amazon_polly_maxim`: Amazon Polly, русский голос Maxim. Секреты читаются из `.env`.
- `google_translate`: прямой Google Translate TTS. В текущем endpoint нет нормального выбора голоса, пола или preset; скорость меняется локальной постобработкой WAV.

## Тестовые / проблемные

- Старый SVOX/Google-робот: отдельный кандидат для исследования, не тот же провайдер, что `google_translate`.

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
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider yandex "Проверка Yandex."
D:\Progs\VoiceService\runtime\.venv\Scripts\python.exe application\tts_test.py --provider amazon_polly_maxim "Проверка Maxim."
```

## Yandex `.env`

```text
YANDEX_CLOUD_API_KEY
YANDEX_CLOUD_FOLDER_ID
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_REGION
```

Значения не хранить в Markdown и не коммитить.
