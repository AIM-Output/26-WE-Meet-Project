#!/bin/bash
# 대시보드 로컬 서버 (맥) — Windows run.cmd 와 같다. 보통은 프로젝트 폴더의 "유니버스 열기.command" 가 부른다.
# 처음이면 .venv 를 만들고 requirements.txt 를 설치한다 (목록이 바뀌면 다시 설치).
cd "$(dirname "$0")" || exit 1
source ../../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt || exit 1
exec "$UNIVUS_PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 "$@"
