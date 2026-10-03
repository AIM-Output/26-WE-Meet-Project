@echo off
chcp 65001 >nul
rem F5 시험 공부 일정 명령줄:  run.cmd status  ^|  run.cmd sync  ^|  run.cmd preview ex:...  ^|  run.cmd plan ex:...  ^|  run.cmd progress
rem 설치할 것이 없다 — 표준 라이브러리만 쓴다. 시험은 e클래스 공지에서 찾고(수집은 F6), 분량은 강의자료(F4)의 쪽수를 읽는다.
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m exams %*
