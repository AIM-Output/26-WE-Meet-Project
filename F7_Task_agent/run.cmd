@echo off
chcp 65001 >nul
rem F7 과제 우선순위 명령줄:  run.cmd list  ^|  run.cmd top  ^|  run.cmd today  ^|  run.cmd settings --bed 01:00
rem 설치할 것이 없다 — 표준 라이브러리만 쓴다. 과제는 F6 원장을 읽기만 하고, 설정(data/settings.json)만 쓴다.
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m tasks %*
