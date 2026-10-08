"""C2 사용자 프로필·학과 마스터 — ../C2_Profile_agent 의 API(student.api)를 이 서버에 붙인다.

프로필 하나를 F1(학사일정 대상 판정)·F2(졸업요건)·F11(장학 매칭)이 같이 쓴다(전역 결정 G3). 다른 기능은 여기의
get_profile() 로 읽는다. C2 쪽 모듈은 표준 라이브러리 + fastapi 만 써서 더 설치할 것이 없다.

C2 폴더가 없거나 불러오지 못해도 나머지 화면은 동작해야 한다 → 프로필은 None(프로필 없음)으로 본다.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

from . import calendar_events
from . import config as C

_error: Optional[str] = None


def _load():
    global _error
    if not (C.C2_AGENT_DIR / "student" / "api.py").exists():
        _error = f"C2_Profile_agent 가 없습니다: {C.C2_AGENT_DIR}"
        return None
    if str(C.C2_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C2_AGENT_DIR))
    try:
        from student import api as c2_api        # type: ignore[import-not-found]
        return c2_api
    except Exception as e:                       # noqa: BLE001
        _error = f"C2 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


c2 = _load()


def get_profile() -> Optional[dict]:
    """다른 기능용 프로필 (F1 audience 가 읽는 grade·enrollment·college·department·major …). 없으면 None."""
    if not c2:
        return None
    try:
        return c2.profile_for_matching()
    except Exception:                            # noqa: BLE001 — 프로필 DB 문제로 다른 화면이 죽지 않게
        return None


def router(on_change: Optional[Callable[[], None]] = None):
    return c2.build_router(on_change) if c2 else None


def migrate_legacy() -> None:
    """F1 을 붙일 때 임시로 C1 일정 DB(univus.db 의 kv)에 두었던 프로필이 남아 있으면 C2 로 옮기고 지운다 (한 번)."""
    if not c2:
        return
    legacy = calendar_events.take_legacy_profile()
    if not legacy:
        return
    from student import service, store as c2store   # type: ignore[import-not-found]
    with c2store.connect() as con:
        service.migrate_legacy(con, legacy)


def error() -> Optional[str]:
    return _error
