"""C3 포털 자동 로그인 명령줄 (C3_Login_agent/.venv 의 python 으로):

    python -m login                  로그인 창 — 직접 SSO 로그인 (+휴대폰 2차 인증) → 세션·신뢰 기기 저장
    python -m login --auto           무인 로그인 시험 (저장된 자격증명 + 신뢰 기기)
    python -m login check            저장된 세션이 지금 살아 있는지 (창 없음)
    python -m login status           설치·세션·자격증명 파일 상태
    python -m login creds [--show | --clear]   자격증명 저장 / 아이디 보기 / 지우기

종료 코드: 0 성공 · 1 창을 닫음·설정 오류 · 2 로그인되지 않음
"""
from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    cmd = argv[0] if argv and not argv[0].startswith("-") else None
    rest = argv[1:] if cmd else argv
    if cmd == "status":
        from . import status
        print(json.dumps(status(), ensure_ascii=False, indent=2))
        return 0
    if cmd == "creds":
        from .creds import run
        return run(rest)
    if cmd == "check":
        from .session import check_cli
        return check_cli()
    if cmd in (None, "window"):
        from . import session
        return session.auto_login_cli() if "--auto" in rest else session.interactive_login()
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
