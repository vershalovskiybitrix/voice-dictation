@echo off
REM Запуск VoiceService в фоне (иконка в трее, без окна консоли).
cd /d "%~dp0"
start "" "..\runtime\.venv\Scripts\pythonw.exe" voiceservice.py
