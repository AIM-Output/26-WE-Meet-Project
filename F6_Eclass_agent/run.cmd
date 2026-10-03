@echo off
chcp 65001 >nul
rem F6 명령줄:  run.cmd list  ^|  run.cmd list --tab past  ^|  run.cmd runs  ^|  run.cmd status  ^|  run.cmd interval 4
rem 보기 명령은 표준 라이브러리만 쓴다 — 수집은 sync.cmd.
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\C3_Login_agent\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
"%PY%" -m eclass %*
