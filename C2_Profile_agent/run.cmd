@echo off
chcp 65001 >nul
rem C2 프로필 명령줄:  run.cmd show  ^|  run.cmd dept 인공지능  ^|  run.cmd set grade=3  ^|  run.cmd import  ^|  run.cmd master-sync
rem 설치할 것이 없다 — 표준 라이브러리만 쓰고, 학사정보시스템 가져오기(import)만 C3_Login_agent 의 .venv 를 빌려 쓴다.
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m student %*
