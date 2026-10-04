#!/bin/bash
# C3_Login_agent 최초 설치 (맥) — Windows setup.cmd 와 같다. 다시 실행해도 안전하다 (이미 된 단계는 건너뛴다).
#   1) .venv 가상환경  2) requirements.txt 패키지  3) Playwright Chromium 을 .venv/pw-browsers 에
cd "$(dirname "$0")" || exit 1
source ../C0_Platform_agent/univus.sh
univus_venv "$PWD/.venv" requirements.txt --chromium || exit 1
echo ""
echo "설치 완료. 다음 단계:  ./login.command  (학교 SSO 로그인 창)"
