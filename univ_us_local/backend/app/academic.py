"""F1 학사 일정 — ../F1_Bachelor_agent 의 API(bachelor.api)를 이 서버에 붙인다.

수집·추출·등록·알림 코드는 전부 F1_Bachelor_agent 에 있다. 여기서는
  - 라우터(/api/academic/* · /api/sources* · /api/notifications*)를 include 하고
  - /api/events 에 학사 일정을 섞고, /api/status 에 학사 원천 상태를 싣는다.
F1 쪽 모듈(store·service·api)은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.
수집 자체(requests·bs4)는 F1 runner 가 자식 프로세스(`-m bachelor sync` — 앱 실행 파일 / 개발 venv)로 돌린다.

F1 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알리고 빈 값을 준다.
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C
from .student_profile import get_profile

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F1_AGENT_DIR / "bachelor" / "api.py").exists():
        _error = f"F1_Bachelor_agent 가 없습니다: {C.F1_AGENT_DIR}"
        return None
    if str(C.F1_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F1_AGENT_DIR))
    try:
        from bachelor import api as f1_api   # type: ignore[import-not-found]
        return f1_api
    except Exception as e:                   # noqa: BLE001 — 어떤 이유로든 F1 이 못 뜨면 나머지는 살린다
        _error = f"F1 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f1 = _load()


def router():
    return f1.build_router(get_profile) if f1 else None


def calendar_events(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    if not f1:
        return []
    try:
        return f1.calendar_events(get_profile(), start, end)
    except Exception:                        # noqa: BLE001 — 학사 DB 문제로 캘린더 전체가 죽지 않게
        return []


def touch() -> None:
    """프로필이 바뀌었다고 알린다 — '내 해당'이 다시 계산되므로 화면이 학사 일정을 다시 부르게 updatedAt 을 올린다(C2-R08)."""
    if not f1:
        return
    try:
        from bachelor import store as f1store     # type: ignore[import-not-found]
        with f1store.connect() as con:
            f1store.touch(con)
    except Exception:                        # noqa: BLE001
        pass


def status() -> dict:
    if not f1:
        return {"available": False, "error": _error}
    try:
        return f1.status_summary(get_profile())
    except Exception as e:                   # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
