"""F11 장학 공지 매칭·신청서 초안 — ../F11_Scholarship_agent 의 API(scholarship.api)를 이 서버에 붙인다.

수집·추출·판정·초안 코드는 전부 F11_Scholarship_agent 에 있다. 여기서는
  - 라우터(/api/scholarships*)를 include 하고,
  - 판정 재료로 C2 프로필을 **민감정보까지** 넘긴다(소득구간·거주 지역·출신 고교·해당 사항 — F11 판정에만 쓴다, C2 schema 의 이유 문구),
  - '캘린더에 넣기 · 할 일로 보내기'를 C1 내 일정·할 일로 만들고(출처 sch:<id> — 같은 것을 두 번 넣지 않는다),
  - 알림을 대시보드 알림 센터(F1 notifications, kind=scholarship)에 넣고, /api/status 에 타일 숫자를 싣는다.
F11 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 더 설치할 것이 없다. 수집(requests·bs4)은 자식 프로세스(`-m scholarship sync`).

F11 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C
from . import student_profile

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F11_AGENT_DIR / "scholarship" / "api.py").exists():
        _error = f"F11_Scholarship_agent 가 없습니다: {C.F11_AGENT_DIR}"
        return None
    if str(C.F11_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F11_AGENT_DIR))
    try:
        from scholarship import api as f11_api      # type: ignore[import-not-found]
        return f11_api
    except Exception as e:                          # noqa: BLE001 — 어떤 이유로든 F11 이 못 뜨면 나머지는 살린다
        _error = f"F11 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f11 = _load()


def get_profile() -> Optional[dict]:
    """C2 프로필 전체(화면 모양) — 판정에 소득구간·지역·해당 사항까지 쓴다. 프로필이 없으면 None."""
    return student_profile.get_full_profile()


def _add_event(ev: dict) -> Optional[dict]:
    """C1 내 일정·할 일 만들기 — 출처(origin)가 같은 것이 있으면 새로 만들지 않고 그것을 돌려준다."""
    try:
        from calendar_core import store as c1store    # type: ignore[import-not-found]
    except Exception:                               # noqa: BLE001 — C1 이 없으면 캘린더 연동만 빠진다
        return None
    if ev.get("origin"):
        old = c1store.find_by_origin(ev["origin"])
        if old:
            return old
    return c1store.create_event(**ev)


def _push(nid: str, ref_id: str, title: str, body: str, href: Optional[str]) -> None:
    try:
        from bachelor import notify as f1notify, store as f1store   # type: ignore[import-not-found]
    except Exception:                               # noqa: BLE001 — F1 이 없으면 알림 센터가 없다
        return
    with f1store.connect() as con:
        f1notify.push(con, "scholarship", ref_id, title, body, href, nid=nid)


def router():
    return f11.build_router(get_profile, _add_event) if f11 else None


def touch() -> None:
    """프로필이 바뀌었다 → 장학 목록을 다시 판정해 보여 주도록 updatedAt 을 올린다 (F11-R24)."""
    if not f11:
        return
    try:
        f11.touch()
    except Exception:                               # noqa: BLE001
        pass


def brief(days: int = 3) -> list[dict]:
    """F10 브리핑 — 마감 임박 장학만 (F11-R74)."""
    if not f11:
        return []
    try:
        return f11.brief(get_profile, days)
    except Exception:                               # noqa: BLE001
        return []


def status() -> dict:
    if not f11:
        return {"available": False, "error": _error}
    try:
        return f11.status_summary(get_profile, _push)
    except Exception as e:                          # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
