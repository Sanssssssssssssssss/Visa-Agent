@echo off
cd /d "%~dp0.."
".venv\Scripts\python.exe" -X utf8 -m visa_agent.qq_mail samples --allow-samples on
pause
