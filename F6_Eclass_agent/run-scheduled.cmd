@echo off
chcp 65001 >nul
rem 작업 스케줄러가 부른다 (register-task.ps1). 이번 주기를 이미 돌았으면 건너뛰고, 네트워크 오류면 5·15·45분 뒤 다시.
cd /d "%~dp0"
set PYTHONUTF8=1
set "STATE=state"
if defined F6_STATE_DIR set "STATE=%F6_STATE_DIR%"
if not exist "%STATE%" mkdir "%STATE%"
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0..\C3_Login_agent\.venv\pw-browsers"
"..\C3_Login_agent\.venv\Scripts\python.exe" -m eclass tick --log "%STATE%\sync.log" %*
