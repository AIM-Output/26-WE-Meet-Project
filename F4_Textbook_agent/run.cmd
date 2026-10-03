@echo off
chcp 65001 >nul
rem F4 강의자료 명령줄:  run.cmd status  ^|  run.cmd list 운영체제  ^|  run.cmd courses  ^|  run.cmd scan --force  ^|  run.cmd path 오리엔테이션
rem 설치할 것이 없다 — 표준 라이브러리만 쓴다. 파일을 새로 내려받지 않는다 (e클래스 수집은 F6_Eclass_agent 가 한다).
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m textbook %*
