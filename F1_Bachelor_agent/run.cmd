@echo off
chcp 65001 >nul
rem 명령줄 도구:  run.cmd list  ^|  run.cmd list --tab review  ^|  run.cmd notify  ^|  run.cmd sources
rem              run.cmd approve ^<event_id^>  ^|  run.cmd add-source ^<학과 게시판 주소^> --dept 학과명
cd /d "%~dp0"
set PYTHONUTF8=1
if not exist ".venv\Scripts\python.exe" call "%~dp0setup.cmd" nopause
".venv\Scripts\python.exe" -m bachelor %*
