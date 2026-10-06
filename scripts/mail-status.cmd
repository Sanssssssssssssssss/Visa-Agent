@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -X utf8 scripts\mail_service.py status
pause
