#!/bin/bash
# 자동 재로그인용 아이디·비밀번호 저장 (맥) — Windows setup-creds.cmd 와 같다. 맥은 로그인 키체인에 넣는다.
#   ./setup-creds.command            저장/갱신
#   ./setup-creds.command --show     저장된 아이디만
#   ./setup-creds.command --clear    삭제
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt --chromium || exit 1
exec "$UNIVUS_PY" -m login creds "$@"
