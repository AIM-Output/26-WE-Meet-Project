@echo off
chcp 65001 >nul
rem ============================================================
rem  eclass_agent 최초 설치 (한 번만)
rem   1) 이 폴더에 .venv 가상환경 생성 (Python 3.12 권장)
rem   2) requirements.txt 패키지 설치
rem   3) Playwright Chromium 을 .venv\pw-browsers 에 내려받음
rem  다시 실행해도 안전하다 (이미 된 단계는 건너뛴다).
rem ============================================================
cd /d "%~dp0"
set PYTHONUTF8=1
set PLAYWRIGHT_BROWSERS_PATH=%~dp0.venv\pw-browsers

if exist ".venv\Scripts\python.exe" goto pip
echo [1/3] 가상환경(.venv) 만드는 중...
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Python 을 찾지 못했습니다. https://www.python.org/downloads/ 에서 Python 3.12 를 설치하고
  echo   설치 화면의 "Add python.exe to PATH" 에 체크한 뒤 이 파일을 다시 실행하세요.
  pause
  exit /b 1
)

:pip
echo [2/3] 패키지 설치 중...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo   패키지 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.
  pause
  exit /b 1
)

echo [3/3] 브라우저(Chromium) 내려받는 중... (수백 MB, 몇 분 걸릴 수 있음)
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
  echo   브라우저 내려받기에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.
  pause
  exit /b 1
)

echo.
echo 설치 완료. 다음 단계:  .\login.cmd  (e클래스 로그인)
if "%~1"=="" pause
exit /b 0
