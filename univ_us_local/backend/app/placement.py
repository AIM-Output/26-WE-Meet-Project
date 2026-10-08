"""F8 공강 학습 플랜 — ../F8_Plan_agent 의 API(placement.api)를 이 서버에 붙인다.

슬롯 계산·배치·등록·충돌 감지는 전부 F8_Plan_agent 에 있다. 여기서는
  - 라우터(/api/placement* · /api/settings/availability)를 include 하고,
  - 계산 재료를 넘겨준다: 다른 일정(F3 수업 · C1 내 일정·할 일 · F5 시험 — F1 학사 일정은 넣지 않는다) · F5 공강 공부 대상(시험·진도율) · F7 순위,
  - /api/events 에 과제·할 일 블록(kind=study)을 섞고 (C1 3절 — 충돌이면 extendedProps.conflict),
  - **공강 공부 블록은 전체 캘린더에 넣지 않고 F5 공부 캘린더에만** 넘겨준다(study_source — F5 D7 과 같은 규칙, 두 캘린더는 따로다),
  - /api/status 에 타일 숫자(앞으로 남은 블록 · 오늘 블록 · updatedAt)를 싣는다.
F8 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.

F8 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

from . import config as C
from . import exams, priority

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F8_AGENT_DIR / "placement" / "api.py").exists():
        _error = f"F8_Plan_agent 가 없습니다: {C.F8_AGENT_DIR}"
        return None
    if str(C.F8_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F8_AGENT_DIR))
    try:
        from placement import api as f8_api                # type: ignore[import-not-found]
        return f8_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 F8 이 못 뜨면 나머지는 살린다
        _error = f"F8 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f8 = _load()

EventsLoader = Callable[[Optional[str], Optional[str]], list[dict]]


def _exams(with_progress: bool = True) -> list[dict]:
    """F5 공강 공부 대상 — 다가오는 시험 · 남은 진도율 (공부 블록 과목 고르기 · 충돌의 '시험 지남')."""
    return exams.study_targets(with_progress)


def router(load_events: EventsLoader, on_change: Optional[Callable[[], None]] = None):
    """load_events(start, end) — 수업 · 내 일정·할 일 · 시험 (main.py 가 C1 합치기로 만든다. 학사 일정·학습 블록·마감은 넣지 않는다)."""
    if not f8:
        return None
    return f8.build_router(load_events, _exams, priority.ranked, on_change=on_change)


def calendar_source(load_events: EventsLoader) -> Callable[[Optional[str], Optional[str]], list[dict]]:
    """/api/events 에 섞는 학습 블록 소스 — 앞으로 남은 블록이 있을 때만 다른 일정을 읽어 충돌을 단다."""
    def source(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
        if not f8:
            return []
        try:
            return f8.calendar_events(start, end, load_events, _exams, priority.ranked)
        except Exception:                       # noqa: BLE001 — 배치 DB 문제로 캘린더 전체가 죽지 않게
            return []
    return source


def study_source(load_events: EventsLoader) -> Callable[[str, str], list[dict]]:
    """F5 공부 캘린더에 섞을 공강 공부 블록 소스 — 충돌(겹침 · 시험 지남)까지 단다.
    F8 이 없거나 깨지면 빈 목록 (공부 캘린더는 계획 블록만 보인다)."""
    def source(start: str, end: str) -> list[dict]:
        if not f8:
            return []
        try:
            return f8.study_blocks(start, end, load_events, _exams, priority.ranked)
        except Exception:                       # noqa: BLE001
            return []
    return source


def today() -> dict:
    """오늘 학습 블록 — F10 아침 브리핑 · F9 대화가 읽는다."""
    if not f8:
        return {"blocks": [], "text": "", "totalMinutes": 0, "remainingMinutes": 0}
    try:
        return f8.today()
    except Exception:                           # noqa: BLE001
        return {"blocks": [], "text": "", "totalMinutes": 0, "remainingMinutes": 0}


def touch() -> None:
    """수업·일정이 바뀌었다 — 화면이 캘린더를 다시 받아 충돌 표시를 새로 하게 한다."""
    if not f8:
        return
    try:
        f8.touch()
    except Exception:                           # noqa: BLE001
        pass


def status() -> dict:
    if not f8:
        return {"available": False, "error": _error}
    try:
        return f8.status_summary()
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
