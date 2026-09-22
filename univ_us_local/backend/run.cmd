@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
)
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 %*
