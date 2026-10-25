"""F12 대외활동(맞춤 기회) — ../F12_Activity_agent 의 API(activity.api)를 이 서버에 붙인다.

수집·추출·관심사 등급·초안 코드는 전부 F12_Activity_agent 에 있다(게시판 수집기·원천 목록은 F11 것을 그대로 빌려 쓴다). 여기서는
  - 라우터(/api/opportunities*)를 include 하고,
  - 등급 재료로 C2 프로필(관심사 interests · 소속 · 학년)을 넘기고,
  - 담기·'캘린더에 넣기 · 할 일로 보내기'를 C1 내 일정·할 일로 만들고(출처 act:<id>, 담기를 풀면 그 일정을 지운다),
  - 초안 재료가 비어 있으면 F11 장학 초안 재료를 불러오게 넘기고(같은 사람이 두 번 적지 않게),
  - 알림을 대시보드 알림 센터(F1 notifications, kind=opportunity)에 넣고, /api/status 에 타일 숫자를 싣는다.
F12 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 더 설치할 것이 없다. 수집(requests·bs4)은 자식 프로세스(`-m activity sync`).

F12 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C
from . import scholarship, student_profile

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F12_AGENT_DIR / "activity" / "api.py").exists():
        _error = f"F12_Activity_agent 가 없습니다: {C.F12_AGENT_DIR}"
        return None
    for d in (C.F11_AGENT_DIR, C.F12_AGENT_DIR):          # F12 는 F11 의 scholarship 패키지(수집기·원천 목록)를 빌려 쓴다
        if str(d) not in sys.path:
            sys.path.insert(0, str(d))
    try:
        from activity import api as f12_api         # type: ignore[import-not-found]
        return f12_api
    except Exception as e:                          # noqa: BLE001 — 어떤 이유로든 F12 가 못 뜨면 나머지는 살린다
        _error = f"F12 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f12 = _load()


def get_profile() -> Optional[dict]:
    """C2 프로필 전체(화면 모양) — 관심사(interests)·소속·학년. 프로필이 없으면 None."""
    return student_profile.get_full_profile()


def _remove_event(event_id: str) -> None:
    try:
        from calendar_core import store as c1store    # type: ignore[import-not-found]
    except Exception:                               # noqa: BLE001
        return
    try:
        c1store.delete_event(int(event_id))
    except (TypeError, ValueError):
        pass


def _shared_materials() -> Optional[dict]:
    """F11 장학 초안 재료(진로·활동·강조점) — F12 재료가 비어 있을 때 재료 카드에 미리 채운다."""
    if not scholarship.f11:
        return None
    from scholarship import service as f11service, store as f11store   # type: ignore[import-not-found]
    with f11store.connect() as con:
        m = f11service.materials(con)
    return m if m.get("exists") else None


def _push(nid: str, ref_id: str, title: str, body: str, href: Optional[str], upsert: bool = False) -> None:
    try:
        from bachelor import notify as f1notify, store as f1store   # type: ignore[import-not-found]
    except Exception:                               # noqa: BLE001 — F1 이 없으면 알림 센터가 없다
        return
    with f1store.connect() as con:
        f1notify.push(con, "opportunity", ref_id, title, body, href, nid=nid, upsert=upsert)


def router():
    # C1 일정 만들기는 장학과 같은 함수(출처가 같으면 새로 만들지 않는다)를 쓴다
    return f12.build_router(get_profile, scholarship._add_event, _remove_event, _shared_materials) if f12 else None


def touch() -> None:
    """프로필(관심사·소속)이 바뀌었다 → 대외활동 목록을 다시 매겨 보여 주도록 updatedAt 을 올린다 (F12-R15)."""
    if not f12:
        return
    try:
        f12.touch()
    except Exception:                               # noqa: BLE001
        pass


def brief(days: int = 3) -> list[dict]:
    """F10 브리핑 — 담아 둔 것의 마감만 (F12-R34)."""
    if not f12:
        return []
    try:
        return f12.brief(get_profile, days)
    except Exception:                               # noqa: BLE001
        return []


def status() -> dict:
    if not f12:
        return {"available": False, "error": _error}
    try:
        return f12.status_summary(get_profile, _push)
    except Exception as e:                          # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
