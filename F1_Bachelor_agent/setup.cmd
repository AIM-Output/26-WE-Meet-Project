@echo off
chcp 65001 >nul
rem ============================================================
rem  F1_Bachelor_agent 최초 설치 (한 번만)
rem   1) 이 폴더에 .venv 가상환경 생성 (Python 3.12 권장)
rem   2) requirements.txt 패키지 설치 (requests, beautifulsoup4, lxml, pypdf …)
rem  다시 실행해도 안전하다. 대시보드의 "학사일정 동기화" 버튼을 처음 누를 때도 자동으로 설치된다.
rem ============================================================
cd /d "%~dp0"
set PYTHONUTF8=1

if exist ".venv\Scripts\python.exe" goto pip
echo [1/2] 가상환경(.venv) 만드는 중...
py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Python 을 찾지 못했습니다. https://www.python.org/downloads/ 에서 Python 3.12 를 설치하고
  echo   설치 화면의 "Add python.exe to PATH" 에 체크한 뒤 이 파일을 다시 실행하세요.
  pause
  exit /b 1
)

:pip
echo [2/2] 패키지 설치 중...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
  echo   패키지 설치에 실패했습니다. 인터넷 연결을 확인하고 다시 실행하세요.
  pause
  exit /b 1
)
if not exist "state" mkdir state

echo.
echo 설치 완료. 다음 단계:  .\sync.cmd   (학사일정 수집 — 처음엔 1분쯤)
if "%~1"=="" pause
exit /b 0
