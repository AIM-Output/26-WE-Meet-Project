@echo off
chcp 65001 >nul
rem 완전 무인 재로그인용 아이디·비밀번호 저장 (DPAPI 암호화, 이 Windows 계정에서만 풀린다)
rem   setup-creds.cmd          저장/갱신
rem   setup-creds.cmd --show   저장된 아이디만 보기
rem   setup-creds.cmd --clear  지우기 (반자동으로)
cd /d "%~dp0"
set PYTHONUTF8=1
".venv\Scripts\python.exe" -m login creds %*
