@echo off
cd /d "%~dp0"
set PYTHONUTF8=1
set PLAYWRIGHT_BROWSERS_PATH=%~dp0.venv\pw-browsers
".venv\Scripts\python.exe" sync.py --log "state\sync.log" %*
