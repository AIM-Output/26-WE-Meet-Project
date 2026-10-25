"""C4 브리핑 — ../C4_Briefing_agent 의 API(briefing.api)를 이 서버에 붙인다.

섹션 조립·정시/놓침 판정·수집 기다리기·스냅샷 저장은 전부 C4_Briefing_agent 에 있다. 여기서는
  - 라우터(/api/briefing/today · /api/briefing/regenerate · /api/briefings* · /api/settings/briefing)를 include 하고,
  - 재료를 넘겨준다 — 각 기능이 브리핑용으로 내놓은 함수 그대로(숫자를 다시 계산하지 않는다, F10-R17):
      F3 오늘 수업·위험 과목 · C1 합친 캘린더(오늘 ~ D-3) · F7 먼저 할 것 3건 · F1 D-3 학사 · F5 오늘 공부 · F8 오늘 블록
      · F11 마감 임박 장학 · F12 담아 둔 것의 마감 · 알림 센터(F1 notifications)의 안 읽은 알림,
  - 지금 수집 중인 기능(F6 e클래스 · F1 학사 · F11 장학 · F12 대외활동)을 알려 수집이 끝난 뒤에 만들게 하고(F10 9절),
  - 만들어지면 알림 센터에 한 줄(kind=briefing) 넣고, /api/status 에 오늘 브리핑 상태를 싣는다(겸사겸사 만들 때가 됐으면 만든다).
C4 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.

C4 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Callable, Optional

from . import config as C
from . import academic, activity, attendance, eclass_data, exams, placement, priority, scholarship
from .student_profile import get_profile

_error: Optional[str] = None


def _load():
    global _error
    if not (C.C4_AGENT_DIR / "briefing" / "api.py").exists():
        _error = f"C4_Briefing_agent 가 없습니다: {C.C4_AGENT_DIR}"
        return None
    if str(C.C4_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C4_AGENT_DIR))
    try:
        from briefing import api as c4_api      # type: ignore[import-not-found]
        return c4_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 C4 가 못 뜨면 나머지는 살린다
        _error = f"C4 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


c4 = _load()

EventsLoader = Callable[[Optional[str], Optional[str]], list[dict]]
_sources = None                                 # router(...) 가 채운다 — /api/status 도 같은 재료를 쓴다


def _academic_upcoming() -> list[dict]:
    """F1 — 오늘부터 3일 안의 내 학사 일정 (F1-R35). C4 가 알림이 켜진 것만 고른다."""
    if not academic.f1:
        return []
    return academic.f1.upcoming(get_profile(), 3)


def _alerts() -> list[dict]:
    """알림 센터의 안 읽은 알림 — 알림 표는 F1 이 처음 만들었다. 어느 기능이 넣은 것이든 다 온다."""
    if not academic.f1:
        return []
    return academic.f1.notifications(get_profile(), unread_only=True)


def _collecting() -> list[str]:
    """지금 돌고 있는 수집 — 브리핑은 이것이 끝난 뒤에(최대 5분 기다림) 만든다."""
    out = []
    if eclass_data.sync_state().get("running"):
        out.append("e클래스")
    for name, mod in (("학사일정", "bachelor.runner"), ("장학", "scholarship.runner"), ("대외활동", "activity.runner")):
        m = sys.modules.get(mod)                # 그 기능이 붙어 있을 때만 (import 하지 않는다 — 없으면 건너뜀)
        try:
            if m is not None and m.sync_state().get("running"):
                out.append(name)
        except Exception:                       # noqa: BLE001
            continue
    return out


def _notify(nid: str, title: str, body: str, href: str, fire_at: datetime, missed: bool) -> None:
    """브리핑 도착 → 알림 센터 한 줄 (F10-R05). 알림 표는 F1 이 처음 만들었다(types.ts AppNotification.kind='briefing')."""
    try:
        from bachelor import notify as f1notify, store as f1store   # type: ignore[import-not-found]
    except Exception:                           # noqa: BLE001 — F1 이 없으면 알림 센터가 없다
        return
    with f1store.connect() as con:
        f1notify.push(con, "briefing", nid.split(":", 1)[-1], title, body, href, nid=nid, fire_at=fire_at, missed=missed)


def _build_sources(load_events: Optional[EventsLoader]):
    return c4.Sources(
        classes=attendance.today if attendance.f3 else None,
        events=load_events,
        priority=priority.brief if priority.f7 else None,
        academic=_academic_upcoming if academic.f1 else None,
        study=exams.today_block if exams.f5 else None,
        blocks=placement.today if placement.f8 else None,
        scholarships=scholarship.brief if scholarship.f11 else None,
        activities=activity.brief if activity.f12 else None,
        alerts=_alerts if academic.f1 else None,
        busy=_collecting,
        notify=_notify,
    )


def router(load_events: Optional[EventsLoader] = None, on_change: Optional[Callable[[], None]] = None):
    """load_events(start, end) — 합친 캘린더(main.py 의 CALENDAR_SOURCES + C1 내 일정·할 일)."""
    global _sources
    if not c4:
        return None
    _sources = _build_sources(load_events)
    return c4.build_router(_sources, on_change=on_change)


def sources():
    """명령줄(cli.py briefing today·make)이 앱과 같은 재료를 쓰게 — main.py 를 import 한 뒤에 부른다."""
    return _sources if _sources is not None else _build_sources(None)


def status() -> dict:
    if not c4:
        return {"available": False, "error": _error}
    try:
        return c4.status_summary(sources())
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
