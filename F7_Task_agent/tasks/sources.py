"""명령줄(run.cmd)용 — 다른 기능 폴더의 데이터를 직접 읽는다. 대시보드에서는 쓰지 않는다(백엔드가 함수로 넘겨준다).

전부 읽기만 하고, 하나를 못 읽어도 나머지로 계산한다 (못 읽은 것은 problems 에 적어 보여 준다).
다른 기능의 패키지(eclass · calendar_core · attendance · exams)는 모두 표준 라이브러리만 쓰는 모듈만 import 한다
— api.py(fastapi)는 부르지 않는다.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Optional

from . import config as C

problems: list[str] = []


def _path(p: Path) -> None:
    if str(p) not in sys.path:
        sys.path.append(str(p))


def assignments() -> list[dict]:
    """F6 과제 원장 → 화면용 과제 목록 (완료 포함 — 거르는 것은 rules.rank)."""
    if not (C.F6_AGENT_DIR / "eclass" / "service.py").exists():
        problems.append(f"F6 과제 원장이 없습니다: {C.F6_AGENT_DIR}")
        return []
    _path(C.F6_AGENT_DIR)
    try:
        from eclass import service, store       # type: ignore[import-not-found]
        with store.connect() as con:
            service.ensure_reconciled(con)
            return service.list_assignments(con, None)["items"]
    except Exception as e:                      # noqa: BLE001
        problems.append(f"F6 과제를 읽지 못했습니다: {type(e).__name__}: {e}")
        return []


def events(start: Optional[str], end: Optional[str]) -> list[dict]:
    """오늘 남은 시간에서 뺄 일정 — C1 내 일정 + F3 수업 (+ F5 시험)."""
    out: list[dict] = []
    if (C.C1_AGENT_DIR / "calendar_core" / "store.py").exists():
        _path(C.C1_AGENT_DIR)
        try:
            from calendar_core import store as c1store      # type: ignore[import-not-found]
            out += c1store.list_events()
        except Exception as e:                  # noqa: BLE001
            problems.append(f"C1 내 일정을 읽지 못했습니다: {type(e).__name__}: {e}")
    if (C.F3_AGENT_DIR / "attendance" / "service.py").exists():
        _path(C.F3_AGENT_DIR)
        try:
            from attendance import service as f3, store as f3store    # type: ignore[import-not-found]
            with f3store.connect() as con:
                out += f3.calendar_events(con, start, end)
        except Exception as e:                  # noqa: BLE001
            problems.append(f"F3 수업을 읽지 못했습니다: {type(e).__name__}: {e}")
    if (C.F5_AGENT_DIR / "exams" / "service.py").exists():
        _path(C.F5_AGENT_DIR)
        try:
            from exams import service as f5, store as f5store         # type: ignore[import-not-found]
            with f5store.connect() as con:
                out += f5.calendar_events(con, start, end)
        except Exception as e:                  # noqa: BLE001
            problems.append(f"F5 시험을 읽지 못했습니다: {type(e).__name__}: {e}")
    return out


def study_minutes() -> float:
    """오늘 아직 체크하지 않은 학습 분량(분) — F5."""
    if not (C.F5_AGENT_DIR / "exams" / "service.py").exists():
        return 0.0
    _path(C.F5_AGENT_DIR)
    try:
        from exams import service as f5, store as f5store             # type: ignore[import-not-found]
        with f5store.connect() as con:
            blocks = f5.today_block(con, date.today())["blocks"]
        return float(sum(b["minutes"] or 0 for b in blocks if not b["done"]))
    except Exception as e:                      # noqa: BLE001
        problems.append(f"F5 학습 분량을 읽지 못했습니다: {type(e).__name__}: {e}")
        return 0.0
