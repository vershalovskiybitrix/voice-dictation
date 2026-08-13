# Читалки VoiceService

## Рабочие провайдеры

- `sapi`: системные Windows-голоса. Используется как простой fallback.
- `piper`: локальный Piper в `runtime/tts/piper`. После фикса stdin текст передаётся в `piper.exe` как UTF-8.
- `silero`: локальный Silero. PyTorch Hub cache и модель должны лежать в `runtime/tts/silero`, а не в профиле пользователя на диске C.
- `yandex`: Yandex SpeechKit. Секреты читаются из `.env`; голоса и роли выбираются из списков.

## Тестовые / проблемные

- `google_old`: тестовый Google Translate robot. Работает стабильно, но качество непригодное; запланирован к удалению.
- `rhvoice`: не отдельный portable-провайдер. На Windows RHVoice ставится как SAPI voice installer; после системной установки голос должен появиться в списке SAPI.

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
