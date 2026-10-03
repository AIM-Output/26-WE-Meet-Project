"""F3 출결·학사경고 예방 — ../F3_Attendance_agent 의 API(attendance.api)를 이 서버에 붙인다.

시간표 수집·회차 계산·출결 기록 코드는 전부 F3_Attendance_agent 에 있다. 여기서는
  - 라우터(/api/attendance/*)를 include 하고 과목 목록(e클래스 courses.json)·프로필(C2)을 넘겨주고,
  - /api/events 에 수업 일정(C1 kind=class)을 섞고, /api/status 에 타일 숫자(위험 과목·미입력)를 싣고,
  - 상태가 올라갈 때의 경고를 대시보드 알림 센터(F1 notifications 표, 헤더 종)에 넣는다.
F3 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.

F3 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C
from . import eclass_data
from .student_profile import get_profile

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F3_AGENT_DIR / "attendance" / "api.py").exists():
        _error = f"F3_Attendance_agent 가 없습니다: {C.F3_AGENT_DIR}"
        return None
    if str(C.F3_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F3_AGENT_DIR))
    try:
        from attendance import api as f3_api    # type: ignore[import-not-found]
        return f3_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 F3 가 못 뜨면 나머지는 살린다
        _error = f"F3 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f3 = _load()


def _notify(alert: dict) -> None:
    """출결 경고 → 알림 센터 (F3-R33·S09). 알림 표는 F1 이 처음 만들었다(types.ts AppNotification.kind='attendance')."""
    try:
        from bachelor import notify as f1notify, store as f1store   # type: ignore[import-not-found]
    except Exception:                           # noqa: BLE001 — F1 이 없으면 토스트(응답의 alerts)로만 알린다
        return
    with f1store.connect() as con:
        f1notify.push(con, "attendance", alert["refId"], alert["title"], alert["body"], alert["href"],
                      nid=f"att:{alert['refId']}:{alert['at']}")


def router():
    if not f3:
        return None
    return f3.build_router(eclass_data.load_courses, get_profile, notify=_notify)


def calendar_events(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    if not f3:
        return []
    try:
        return f3.calendar_events(start, end)
    except Exception:                           # noqa: BLE001 — 출결 DB 문제로 캘린더 전체가 죽지 않게
        return []


def touch() -> None:
    """프로필이 바뀌었다 — 학사경고 안내(직전 학기 평점)가 달라질 수 있으니 화면이 다시 부르게 한다 (C2-R08)."""
    if not f3:
        return
    try:
        f3.touch()
    except Exception:                           # noqa: BLE001
        pass


def status() -> dict:
    if not f3:
        return {"available": False, "error": _error}
    try:
        return f3.status_summary(eclass_data.load_courses, get_profile(), notify=_notify)
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
