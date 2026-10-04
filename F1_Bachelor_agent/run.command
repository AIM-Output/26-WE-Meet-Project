#!/bin/bash
# F1 명령줄 (맥) — Windows run.cmd 와 같다.  예: ./run.command list
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt || exit 1
exec "$UNIVUS_PY" -m bachelor "$@"
