@echo off
chcp 65001 >nul
rem 학사일정 수집을 이 창에서 실행한다 (진행 상황이 화면에 보임).
rem   sync.cmd                          켜진 원천 전부
rem   sync.cmd --dry-run                저장하지 않고 무엇을 찾는지만
rem   sync.cmd --source jnu_notice      원천 하나만
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" call "%~dp0setup.cmd" nopause
".venv\Scripts\python.exe" -m bachelor sync %*
