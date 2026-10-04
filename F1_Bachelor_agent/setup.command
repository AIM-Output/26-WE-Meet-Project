#!/bin/bash
# F1 학사일정 수집기 설치 (맥) — Windows setup.cmd 와 같다. 다시 실행해도 안전하다.
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt || exit 1
mkdir -p state
echo ""
echo "설치 완료. 다음 단계:  ./sync.command   (학사일정 수집 — 처음엔 1분쯤)"
