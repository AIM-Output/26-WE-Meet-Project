@echo off
chcp 65001 >nul
rem F8 공강 학습 플랜 명령줄:  run.cmd preview  ^|  run.cmd apply  ^|  run.cmd list  ^|  run.cmd settings --evening 19:00-24:00
rem 설치할 것이 없다 — 표준 라이브러리만 쓴다. 다른 기능 데이터는 읽기만 하고, 블록(data/placement.db)·설정(data/settings.json)만 쓴다.
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m placement %*
