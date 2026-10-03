@echo off
chcp 65001 >nul
rem e클래스 수집 (창 없이, 출력은 state\sync.log) — 대시보드 버튼과 같은 실행. 인자는 그대로 넘긴다.
cd /d "%~dp0"
set PYTHONUTF8=1
set "STATE=state"
if defined F6_STATE_DIR set "STATE=%F6_STATE_DIR%"
if not exist "%STATE%" mkdir "%STATE%"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0..\C3_Login_agent\.venv\pw-browsers"
"..\C3_Login_agent\.venv\Scripts\python.exe" -m eclass sync --log "%STATE%\sync.log" %*
