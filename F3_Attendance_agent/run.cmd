@echo off
chcp 65001 >nul
rem F3 출결 명령줄:  run.cmd status  ^|  run.cmd sessions 운영체제  ^|  run.cmd import  ^|  run.cmd semester  ^|  run.cmd parse 월5월6수5
rem 설치할 것이 없다 — 표준 라이브러리만 쓴다 (시간표 조회도 로그인이 필요 없는 공개 화면이라 브라우저가 필요 없다).
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m attendance %*
