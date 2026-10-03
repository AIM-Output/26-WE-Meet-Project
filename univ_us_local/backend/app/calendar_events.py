"""C1 서비스 캘린더 — ../C1_Calendar_agent 의 API(calendar_core.api)를 이 서버에 붙인다.

캘린더 본체(내 일정·할 일 저장, /api/events 의 합치기·검사 규칙)는 전부 C1_Calendar_agent 에 있다. 여기서는
  - 라우터(GET/POST/PATCH/DELETE /api/events)를 include 하고,
  - 캘린더에 얹을 다른 소스(F6 마감 · F1 학사 · F3 수업)를 넘겨주고,
  - /api/status 에 건수·분류표를 싣는다.
C1 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.

C1 폴더가 없거나 불러오지 못하면 캘린더 자체가 없는 것이다 → /api/events 가 붙지 않고
/api/status 의 calendar.available=false 로 알린다. 나머지 화면(과제·학사·졸업요건·출결)은 그대로 돈다.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional, Sequence

from . import config as C

# 캘린더에 얹을 다른 기능의 일정을 주는 함수: (start, end) → FullCalendar 이벤트 목록 (C1 3절)
Source = Callable[[Optional[str], Optional[str]], list[dict]]

_error: Optional[str] = None
_NO_COUNTS = {"total": 0, "todos": 0, "done": 0}


def _load():
    global _error
    if not (C.C1_AGENT_DIR / "calendar_core" / "api.py").exists():
        _error = f"C1_Calendar_agent 가 없습니다: {C.C1_AGENT_DIR}"
        return None
    if str(C.C1_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C1_AGENT_DIR))
    try:
        from calendar_core import api as c1_api    # type: ignore[import-not-found]
        return c1_api
    except Exception as e:                         # noqa: BLE001 — 어떤 이유로든 C1 이 못 뜨면 나머지는 살린다
        _error = f"C1 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


c1 = _load()


def init() -> None:
    """서버가 뜰 때 한 번 — 표 만들기 + 2026-09-30 이전에 univ_us_local/data 에 있던 DB 를 C1 폴더로 옮기기."""
    if not c1:
        return
    from calendar_core import store as c1store     # type: ignore[import-not-found]
    c1store.init()


def router(sources: Sequence[Source] = ()):
    return c1.build_router(sources) if c1 else None


def summary() -> dict:
    """available · DB 자리 · 건수 · 분류표 — /api/status 가 한 번만 부른다."""
    if not c1:
        return {"available": False, "error": _error, "counts": dict(_NO_COUNTS), "categories": {}}
    try:
        return c1.status_summary()
    except Exception as e:                         # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}",
                "counts": dict(_NO_COUNTS), "categories": {}}


def take_legacy_profile() -> Optional[dict]:
    """일정 DB(kv)에 잠깐 두었던 옛 프로필 — C2 로 옮길 때 student_profile.py 가 한 번 부른다."""
    if not c1:
        return None
    try:
        from calendar_core import store as c1store    # type: ignore[import-not-found]
        return c1store.take_legacy_profile()
    except Exception:                              # noqa: BLE001 — 옮기기 실패로 서버가 안 뜨면 안 된다
        return None
