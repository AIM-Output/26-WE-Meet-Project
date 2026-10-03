@echo off
chcp 65001 >nul
rem Called by Task Scheduler (register-task.ps1). Runs once a day: skips if today's 08:00 collection already succeeded,
rem retries after 5/15/45 min when every source failed (usually network). Log follows F1_STATE_DIR like run-sync.cmd.
cd /d "%~dp0"
set PYTHONUTF8=1
set "STATE=state"
if defined F1_STATE_DIR set "STATE=%F1_STATE_DIR%"
if not exist "%STATE%" mkdir "%STATE%"
if exist ".venv\Scripts\python.exe" goto run
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt >> "%STATE%\sync.log" 2>&1
:run
".venv\Scripts\python.exe" -m bachelor tick --log "%STATE%\sync.log" %*
