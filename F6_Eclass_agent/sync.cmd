@echo off
chcp 65001 >nul
rem e클래스 수집을 이 창에서 실행한다 (진행 상황이 화면에 보임).
rem   sync.cmd                          전체 (자료·공지·과제·마감)
rem   sync.cmd --dry-run                내려받지 않고 목록만
rem   sync.cmd --only assign,deadlines  과제·마감만 빠르게
rem   sync.cmd --course 74261           특정 과목만
rem 브라우저·로그인은 C3_Login_agent 의 것을 빌린다 (먼저 C3_Login_agent\setup.cmd).
cd /d "%~dp0"
set PYTHONUTF8=1
set "PY=..\C3_Login_agent\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo C3_Login_agent 가 설치되어 있지 않습니다. ..\C3_Login_agent\setup.cmd 를 먼저 실행하세요.
  exit /b 1
)
set "PLAYWRIGHT_BROWSERS_PATH=%~dp0..\C3_Login_agent\.venv\pw-browsers"
"%PY%" -m eclass sync %*
