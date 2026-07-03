@echo off
REM SmartFlow AI — one command starts the full platform
cd /d "%~dp0"
echo Installing Python dependencies if needed...
pip install -r requirements.txt -q
echo Starting SmartFlow AI (Web/API + Telegram bot in parallel + admin UI)...
python run.py start
pause
