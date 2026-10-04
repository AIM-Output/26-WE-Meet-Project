#!/bin/bash
# F1 학사일정 수집 (맥) — Windows sync.cmd 와 같다.  예: ./sync.command --source jnu_calendar
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt || exit 1
exec "$UNIVUS_PY" -m bachelor sync "$@"
