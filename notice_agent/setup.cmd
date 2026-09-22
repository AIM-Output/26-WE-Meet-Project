@echo off
REM notice_agent 최초 설치: .venv 생성 + 패키지 설치. (Playwright 브라우저는 eclass_agent 것을 재사용하므로 내려받지 않음)
cd /d "%~dp0"
set PYTHONUTF8=1
chcp 65001 >nul
if not exist ".venv\Scripts\python.exe" py -3.12 -m venv .venv || python -m venv .venv
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt
if not exist ".env" copy ".env.example" ".env" >/dev/null && echo .env 를 만들었습니다. LLM_MAIN_* 를 채우세요.
if not exist "data\profile.json" echo 프로필: assets\profile.example.json 을 data\profile.json 으로 복사해 채우거나  run.cmd profile_from_hakstd  를 실행하세요.
echo 설치 완료. 예:  run.cmd pipeline --pages 2
