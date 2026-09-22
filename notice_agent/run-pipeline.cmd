@echo off
REM 작업 스케줄러용: 파이프라인을 돌리고 출력을 data\logs\pipeline.log 에 쌓는다.
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
if not exist "data\logs" mkdir "data\logs"
echo ======== %DATE% %TIME% ======== >> "data\logs\pipeline.log"
call run.cmd pipeline %* >> "data\logs\pipeline.log" 2>&1
