@echo off
rem  유니버스 종료 - 8000 포트에서 듣고 있는 로컬 서버 프로세스를 끝낸다.
setlocal
set "FOUND="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr LISTENING') do (
  set "FOUND=1"
  taskkill /PID %%p /F >nul 2>&1 && echo 서버를 종료했습니다. ^(PID %%p^)
)
if not defined FOUND echo 켜져 있는 서버가 없습니다.
ping -n 3 127.0.0.1 >nul
