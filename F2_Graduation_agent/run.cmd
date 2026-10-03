@echo off
chcp 65001 >nul
rem F2 졸업요건 명령줄:  run.cmd status  ^|  run.cmd courses  ^|  run.cmd import  ^|  run.cmd curriculum  ^|  run.cmd rulesets
rem 설치할 것이 없다 — 표준 라이브러리만 쓰고, 기이수성적 가져오기(import)만 C3_Login_agent 의 .venv 와 로그인 세션을 빌려 쓴다.
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\univ_us_local\backend\.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=py -3"
%PY% -m graduation %*
