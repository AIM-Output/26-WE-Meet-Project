"""F5 시험 공부 일정 — ../F5_Test_agent 의 API(exams.api)를 이 서버에 붙인다.

공지에서 시험 찾기·역산 계산·학습 블록 등록·진도 추적은 전부 F5_Test_agent 에 있다. 여기서는
  - 라우터(/api/exams* · /api/study-plans*)를 include 하고 과목 목록(e클래스 courses.json)을 넘겨주고,
  - /api/events 에 시험(kind=exam)과 학습 블록(kind=study)을 섞고 (C1 3절),
  - /api/status 에 타일 숫자(오늘 분량 · 다가오는 시험 · 확인 필요 · 밀림)를 싣고,
  - 시험 연기·진도 밀림 알림을 대시보드 알림 센터(F1 notifications 표, 헤더 종)에 넣는다.
F5 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.
분량은 F5 가 F4_Textbook_agent 의 자료 목록을 직접 읽는다(쪽수 합계) — 이 서버가 중개하지 않는다.

F5 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C
from . import eclass_data

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F5_AGENT_DIR / "exams" / "api.py").exists():
        _error = f"F5_Test_agent 가 없습니다: {C.F5_AGENT_DIR}"
        return None
    if str(C.F5_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F5_AGENT_DIR))
    try:
        from exams import api as f5_api        # type: ignore[import-not-found]
        return f5_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 F5 가 못 뜨면 나머지는 살린다
        _error = f"F5 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f5 = _load()


def _notify(alert: dict) -> None:
    """시험 연기·진도 밀림 → 알림 센터 (F5-R34 · 8절). 알림 표는 F1 이 처음 만들었다(kind='exam')."""
    try:
        from bachelor import notify as f1notify, store as f1store   # type: ignore[import-not-found]
    except Exception:                           # noqa: BLE001 — F1 이 없으면 화면의 배너로만 알린다
        return
    with f1store.connect() as con:
        f1notify.push(con, "exam", alert["refId"], alert["title"], alert["body"], alert["href"],
                      nid=f"exam:{alert['refId']}:{alert['at']}")


def router():
    if not f5:
        return None
    return f5.build_router(eclass_data.load_courses, notify=_notify)


def calendar_events(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    if not f5:
        return []
    try:
        return f5.calendar_events(start, end, eclass_data.load_courses)
    except Exception:                           # noqa: BLE001 — 시험 DB 문제로 캘린더 전체가 죽지 않게
        return []


def today_block() -> dict:
    """'오늘 공부: 운영체제 15쪽 (38분)' — F10 아침 브리핑·F9 대화가 읽는다 (F5-R36)."""
    if not f5:
        return {"blocks": [], "text": "", "nextExam": None}
    try:
        return f5.today_block(eclass_data.load_courses)
    except Exception:                           # noqa: BLE001
        return {"blocks": [], "text": "", "nextExam": None}


def sync() -> dict:
    """e클래스 수집이 끝났다 — 새 공지에서 시험을 찾는다 (F5-R01)."""
    if not f5:
        return {"available": False, "error": _error}
    try:
        return f5.sync(eclass_data.load_courses, notify=_notify)
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def touch() -> None:
    if not f5:
        return
    try:
        f5.touch()
    except Exception:                           # noqa: BLE001
        pass


def status() -> dict:
    if not f5:
        return {"available": False, "error": _error}
    try:
        return f5.status_summary(eclass_data.load_courses, notify=_notify)
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
