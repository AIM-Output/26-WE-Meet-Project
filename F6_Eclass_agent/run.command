#!/bin/bash
# F6 보기 명령줄 (맥) — Windows run.cmd 와 같다.  예: ./run.command status · ./run.command list
# 수집(sync)은 sync.command. C3 .venv python 이 있으면 그것을, 없으면 백엔드 .venv · 시스템 python.
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
PY=../C3_Login_agent/.venv/bin/python
[ -x "$PY" ] || PY=../univ_us_local/backend/.venv/bin/python
[ -x "$PY" ] || PY="$(univus_base_python)" || exit 1
exec "$PY" -m eclass "$@"
