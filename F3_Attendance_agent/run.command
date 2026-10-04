#!/bin/bash
# F3 출결 명령줄 (맥) — Windows run.cmd 와 같다.  예: ./run.command status
# 대시보드 백엔드의 .venv python 을 쓰고, 없으면 시스템 python (표준 라이브러리만 쓰는 부분).
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
PY=../univ_us_local/backend/.venv/bin/python
[ -x "$PY" ] || PY="$(univus_base_python)" || exit 1
exec "$PY" -m attendance "$@"
