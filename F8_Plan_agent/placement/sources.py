"""명령줄(desktop/cli.py)용 — 다른 기능 폴더의 데이터를 직접 읽는다. 대시보드에서는 쓰지 않는다(백엔드가 함수로 넘겨준다).

전부 읽기만 하고, 하나를 못 읽어도 나머지로 계산한다 (못 읽은 것은 problems 에 적어 보여 준다).
다른 기능의 패키지(attendance · calendar_core · exams · eclass · tasks)는 표준 라이브러리만 쓰는 모듈만 import 한다
— api.py(fastapi)는 부르지 않는다.
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import config as C

problems: list[str] = []


def _path(p: Path) -> None:
    if str(p) not in sys.path:
        sys.path.append(str(p))


def events(start: Optional[str], end: Optional[str]) -> list[dict]:
    """수업(F3) · 내 일정·할 일(C1) · 시험(F5). 학사 일정(F1)은 배치에서 보지 않는다(내 일정에 넣은 것은 C1 에 있다)."""
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
    else:
        problems.append(f"F3 시간표가 없습니다: {C.F3_AGENT_DIR}")
    if (C.F5_AGENT_DIR / "exams" / "service.py").exists():
        _path(C.F5_AGENT_DIR)
        try:
            from exams import service as f5, store as f5store         # type: ignore[import-not-found]
            with f5store.connect() as con:
                out += f5.calendar_events(con, start, end)
        except Exception as e:                  # noqa: BLE001
            problems.append(f"F5 시험을 읽지 못했습니다: {type(e).__name__}: {e}")
    return out


def exams(with_progress: bool = True) -> list[dict]:
    """F5 공강 공부 대상 — 다가오는 시험과 남은 진도율."""
    if not (C.F5_AGENT_DIR / "exams" / "service.py").exists():
        return []
    _path(C.F5_AGENT_DIR)
    try:
        from exams import service as f5, store as f5store             # type: ignore[import-not-found]
        with f5store.connect() as con:
            return f5.study_targets(con, with_progress=with_progress)
    except Exception as e:                      # noqa: BLE001
        problems.append(f"F5 시험을 읽지 못했습니다: {type(e).__name__}: {e}")
        return []


def priority() -> list[dict]:
    """F7 순위 목록 — F6 과제 원장을 F7 규칙으로 줄 세운 것 (F7-R34: 순서를 다시 계산하지 않는다)."""
    if not (C.F6_AGENT_DIR / "eclass" / "service.py").exists() or not (C.F7_AGENT_DIR / "tasks" / "rules.py").exists():
        problems.append("F6 과제 원장이나 F7 우선순위가 없어 과제는 배치하지 않습니다")
        return []
    _path(C.F6_AGENT_DIR)
    _path(C.F7_AGENT_DIR)
    try:
        from eclass import service as f6, store as f6store             # type: ignore[import-not-found]
        from tasks import rules as f7rules, settings as f7settings      # type: ignore[import-not-found]
        with f6store.connect() as con:
            f6.ensure_reconciled(con)
            items = f6.list_assignments(con, None)["items"]
        return f7rules.rank(items, datetime.now(), f7settings.load())
    except Exception as e:                      # noqa: BLE001
        problems.append(f"F7 순위를 계산하지 못했습니다: {type(e).__name__}: {e}")
        return []
