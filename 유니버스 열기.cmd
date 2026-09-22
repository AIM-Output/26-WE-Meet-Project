@echo off
rem ============================================================
rem  유니버스 열기 - 로컬 서버가 안 떠 있으면 켜고, 브라우저로 페이지를 연다.
rem  서버 창은 최소화된 "Univ-Us Local Server" 창이다. 그 창을 닫으면 서버가 꺼진다.
rem ============================================================
setlocal
set "ROOT=%~dp0"
set "URL=http://localhost:8000"
set "SERVER=%ROOT%univ_us_local\backend\run.cmd"

if not exist "%SERVER%" (
  echo run.cmd 를 찾을 수 없습니다: %SERVER%
  pause
  exit /b 1
)

rem 이미 떠 있으면 바로 연다
curl -s -o NUL --max-time 2 "%URL%/api/status" && goto open

echo 로컬 서버를 시작합니다...
start "Univ-Us Local Server" /min cmd /c ""%SERVER%""

rem 응답할 때까지 최대 90초 기다린다 (처음 실행이면 파이썬 패키지 설치 때문에 오래 걸릴 수 있음)
for /l %%i in (1,1,90) do (
  curl -s -o NUL --max-time 2 "%URL%/api/status" && goto open
  ping -n 2 127.0.0.1 >nul
)
echo.
echo 서버가 90초 안에 응답하지 않았습니다. 최소화된 "Univ-Us Local Server" 창의 메시지를 확인하세요.
pause
exit /b 1

:open
start "" "%URL%"
exit /b 0
