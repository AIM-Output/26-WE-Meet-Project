"""F7 과제 우선순위 — ../F7_Task_agent 의 API(tasks.api)를 이 서버에 붙인다.

그룹·여유·이유 한 줄·오늘 남은 시간 계산은 전부 F7_Task_agent 에 있다. 여기서는
  - 라우터(/api/priority* · /api/settings/priority)를 include 하고,
  - 계산 재료를 넘겨준다: F6 과제 원장(마감·제출·내가 체크함·소요시간) · 오늘 일정(C1 내 일정 + F3 수업 + F5 시험)
    · 오늘 남은 학습 분량(F5),
  - /api/status 에 타일 숫자(지금 해야 함 · 놓친 마감 · 상위 3건)를 싣는다.
F7 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.

과제별 소요시간 수정은 F6 의 PATCH /api/assignments/{id} 그대로다(값이 F6 원장에 있어 재수집이 덮어쓰지 않는다, F7-R03).
F7 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

from . import config as C
from . import eclass_data, exams

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F7_AGENT_DIR / "tasks" / "api.py").exists():
        _error = f"F7_Task_agent 가 없습니다: {C.F7_AGENT_DIR}"
        return None
    if str(C.F7_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F7_AGENT_DIR))
    try:
        from tasks import api as f7_api        # type: ignore[import-not-found]
        return f7_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 F7 이 못 뜨면 나머지는 살린다
        _error = f"F7 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f7 = _load()


def _study_minutes() -> float:
    """오늘 아직 체크하지 않은 학습 분량(분) — F5 블록은 날짜 단위라 시각 없이 덩어리로 뺀다."""
    blocks = exams.today_block().get("blocks") or []
    return float(sum(b.get("minutes") or 0 for b in blocks if not b.get("done")))


def router(load_events: Callable[[Optional[str], Optional[str]], list[dict]],
           on_change: Optional[Callable[[], None]] = None):
    """load_events(start, end) — 오늘 수업·내 일정·시험 (main.py 가 C1 합치기로 만든다)."""
    if not f7:
        return None
    return f7.build_router(eclass_data.load_assignments, load_events, _study_minutes, on_change=on_change)


def ranked() -> list[dict]:
    """급한 순 과제 목록(F7 items, 순서 그대로) — F8 공강 배치가 이 순서대로 넣는다 (F7-R34)."""
    if not f7:
        return []
    return f7.overview(eclass_data.load_assignments, top_n=0)["items"]


def brief(n: int = 3) -> dict:
    """'먼저 할 것' 상위 n건 + 총 소요시간 — F10 아침 브리핑·F9 대화가 읽는다 (F7-R33)."""
    if not f7:
        return {"items": [], "totalHours": 0, "totalText": "", "text": "", "overdue": 0}
    try:
        return f7.brief(eclass_data.load_assignments, n)
    except Exception:                           # noqa: BLE001
        return {"items": [], "totalHours": 0, "totalText": "", "text": "", "overdue": 0}


def status() -> dict:
    if not f7:
        return {"available": False, "error": _error}
    try:
        return f7.status_summary(eclass_data.load_assignments)
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
