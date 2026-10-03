@echo off
chcp 65001 >nul
rem 학사일정 수집 — 대시보드 "학사일정 동기화" 버튼과 작업 스케줄러(register-task.ps1)가 부른다.
rem 출력은 state\sync.log 에 쌓인다. 처음 실행이면 .venv 를 만들고 패키지를 설치한다(1분쯤).
rem 인자는 그대로 넘긴다:  run-sync.cmd --source jnu_calendar
cd /d "%~dp0"
set PYTHONUTF8=1
rem F1_STATE_DIR (tests / isolated server) moves the log together with the lock
set "STATE=state"
if defined F1_STATE_DIR set "STATE=%F1_STATE_DIR%"
if not exist "%STATE%" mkdir "%STATE%"
if exist ".venv\Scripts\python.exe" goto run
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt >> "%STATE%\sync.log" 2>&1
:run
".venv\Scripts\python.exe" -m bachelor sync --log "%STATE%\sync.log" %*
