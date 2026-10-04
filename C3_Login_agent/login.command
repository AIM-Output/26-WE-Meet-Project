#!/bin/bash
# 학교 SSO 로그인 창 (맥) — Windows login.cmd 와 같다. 설치가 안 돼 있으면 setup 부터 한다.
# 자동 재로그인(setup-creds · --auto)은 아직 Windows 전용이다 (DPAPI — 맥 키체인은 다음 단계).
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt --chromium || exit 1
export PLAYWRIGHT_BROWSERS_PATH="$PWD/.venv/pw-browsers"
exec "$UNIVUS_PY" -m login "$@"
