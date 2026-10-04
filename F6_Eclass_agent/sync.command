#!/bin/bash
# F6 e클래스 수집 (맥) — Windows sync.cmd 와 같다.  예: ./sync.command --dry-run · ./sync.command --only assign,deadlines
# 로그인·브라우저는 C3_Login_agent 의 .venv 를 빌린다 (먼저 ../C3_Login_agent/setup.command · login.command).
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
C3="$UNIVUS_ROOT/C3_Login_agent"
if [ ! -x "$C3/.venv/bin/python" ]; then
  echo "C3_Login_agent 가 설치되어 있지 않습니다. ../C3_Login_agent/setup.command 를 먼저 실행하세요."
  exit 1
fi
export PLAYWRIGHT_BROWSERS_PATH="$C3/.venv/pw-browsers"
exec "$C3/.venv/bin/python" -m eclass sync "$@"
