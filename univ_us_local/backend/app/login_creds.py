"""C3 자동 로그인 정보 — ../C3_Login_agent 의 API(login.api)를 이 서버에 붙인다 (/api/login/creds).

비밀번호 암호화·저장(Windows DPAPI · 맥 키체인)은 전부 C3_Login_agent/login/auth.py 에 있다. 여기서는 include 만 한다.
C3 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → 라우터 없음(화면은 '쓸 수 없음'으로 보인다).
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C

_error: Optional[str] = None


def _load():
    global _error
    if not (C.C3_AGENT_DIR / "login" / "api.py").exists():
        _error = f"C3_Login_agent 가 없습니다: {C.C3_AGENT_DIR}"
        return None
    if str(C.C3_AGENT_DIR) not in sys.path:
        sys.path.append(str(C.C3_AGENT_DIR))
    try:
        from login import api as c3_api         # type: ignore[import-not-found]
        return c3_api
    except Exception as e:                      # noqa: BLE001 — C3 가 못 뜨면 나머지는 살린다
        _error = f"C3 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


c3 = _load()


def router():
    return c3.build_router() if c3 else None
