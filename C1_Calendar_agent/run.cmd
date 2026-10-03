@echo off
chcp 65001 >nul
rem C1 서비스 캘린더 명령줄:  run.cmd list  ^|  run.cmd add "회의" 2026-10-02T19:00  ^|  run.cmd done 3  ^|  run.cmd count
rem 설치할 것이 없다 — 표준 라이브러리만 쓴다 (라우터만 fastapi 를 쓰고, 그건 대시보드 백엔드가 부른다).
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m calendar_core %*
