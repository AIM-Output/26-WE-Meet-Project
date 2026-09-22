@echo off
REM 사용:  run.cmd pipeline [옵션]  |  run.cmd collect --dry-run  |  run.cmd approve list  |  run.cmd profile_from_hakstd
REM 항상 이 폴더의 .venv Python 을 쓴다. Playwright 브라우저 경로는 scripts\sso_session.py 가 eclass_agent 것으로 자동 설정한다.
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
if "%~1"=="" ( ".venv\Scripts\python.exe" -m scripts.pipeline --help & exit /b 1 )
set MOD=%~1
shift
set ARGS=
:loop
if "%~1"=="" goto run
set ARGS=%ARGS% %1
shift
goto loop
:run
".venv\Scripts\python.exe" -m scripts.%MOD% %ARGS%
