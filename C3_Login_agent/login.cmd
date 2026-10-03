@echo off
chcp 65001 >nul
rem 전남대 SSO 로그인 창 — 직접 로그인(+휴대폰 2차 인증)하면 세션과 신뢰 기기(약 1년)가 저장된다.
rem   login.cmd          로그인 창
rem   login.cmd --auto   무인 로그인 시험 (setup-creds.cmd 로 저장한 자격증명)
rem   login.cmd check    저장된 세션이 살아 있는지
cd /d "%~dp0"
set PYTHONUTF8=1
set PLAYWRIGHT_BROWSERS_PATH=%~dp0.venv\pw-browsers
if not exist ".venv\Scripts\python.exe" call "%~dp0setup.cmd" nopause
".venv\Scripts\python.exe" -m login %*
