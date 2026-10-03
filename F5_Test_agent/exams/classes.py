"""과목별 수업 회차 — F3 출결이 만든 것을 **읽기만** 한다 (임의 시험 일정을 '그 과목의 수업 요일'로 잡으려고).

F3_Attendance_agent 를 sys.path 에 넣고 `attendance.service.build_semester` 를 부른다(다른 기능이 서로를 빌려 쓰는
방식 — scope.py 가 F4 를 읽는 것과 같다). `attendance.api` 는 부르지 않는다: fastapi 를 끌어와 명령줄에서 못 쓴다.

F3 의 회차는 이미 다음을 반영한 값이다 — 그래서 직접 요일을 세지 않고 빌려 온다:
  - 시간표(요일·교시) → 교시 시각 (월수금 50분 · 화목 75분 모듈)
  - 학사일정의 휴업일(추석·한글날…)은 빠지고, 학교 지정 보강일은 들어간다
  - 휴강(공지·내가 표시)은 state='canceled' — 여기서는 뺀다(그날은 수업이 없다)

F3 가 없거나 시간표가 없는 과목은 None/빈 목록 — 그러면 임의 일정은 시험 주간의 첫 평일로, 시각 없이 잡는다.
"""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Optional

from . import config as C

_error: Optional[str] = None
_f3: Any = None
_tried = False
_cache: dict[str, Any] = {"key": None, "value": None}


def _load() -> Any:
    global _f3, _error, _tried
    if _tried:
        return _f3
    _tried = True
    if not (C.F3_AGENT_DIR / "attendance" / "service.py").exists():
        _error = f"F3_Attendance_agent 가 없습니다: {C.F3_AGENT_DIR}"
        return None
    if str(C.F3_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F3_AGENT_DIR))
    try:
        from attendance import academic_calendar as f3_cal      # type: ignore[import-not-found]
        from attendance import config as f3_config              # type: ignore[import-not-found]
        from attendance import service as f3_service            # type: ignore[import-not-found]
        from attendance import store as f3_store                # type: ignore[import-not-found]
        _f3 = (f3_store, f3_service, f3_cal, f3_config)
    except Exception as e:                                      # noqa: BLE001 — F3 가 못 뜨면 시각 없이 잡는다
        _error = f"F3 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        _f3 = None
    return _f3


def reset() -> None:
    """테스트에서 F3 폴더를 갈아 끼울 때."""
    global _f3, _error, _tried
    _f3, _error, _tried = None, None, False
    _cache.update(key=None, value=None)


def available() -> bool:
    return _load() is not None


def error() -> Optional[str]:
    _load()
    return _error


def _stamp(mods: Any) -> tuple:
    """F3 DB 와 F1 DB 가 그대로면 다시 계산하지 않는다 (상태는 1분마다 불린다)."""
    _, _, _, f3c = mods
    out = []
    for p in (getattr(f3c, "DB_PATH", None), getattr(f3c, "F1_DB", None)):
        try:
            st = p.stat()
            out.append((str(p), st.st_mtime_ns, st.st_size))
        except (OSError, AttributeError):
            out.append((str(p), None, None))
    return tuple(out)


def stamp() -> Optional[tuple]:
    """F3·F1 DB 가 바뀌었는지 보는 도장 — 임의 일정 계산을 건너뛸지 정할 때 쓴다. F3 가 없으면 None."""
    mods = _load()
    return _stamp(mods) if mods else None


def sessions(semester: str) -> Optional[dict[str, list[dict]]]:
    """{과목 id: [{date, weekday, start, end}]} — 휴강은 뺀다. F3 를 못 읽으면 None."""
    mods = _load()
    if not mods:
        return None
    key = (semester, _stamp(mods))
    if _cache["key"] == key:
        return _cache["value"]
    f3_store, f3_service, f3_cal, _ = mods
    try:
        with f3_store.connect() as con:
            _, courses = f3_service.build_semester(con, semester, datetime.now(), f3_cal.load())
    except Exception:                                           # noqa: BLE001 — 출결 DB 문제로 시험 화면이 죽지 않게
        return None
    out: dict[str, list[dict]] = {}
    for c in courses:
        out[str(c["id"])] = sorted(
            ({"date": s["date"], "weekday": s["weekday"], "start": s["start"], "end": s["end"]}
             for s in c.get("sessions") or [] if s.get("state") != "canceled"),
            key=lambda s: (s["date"], s["start"]))
    _cache.update(key=key, value=out)
    return out


__all__ = ["sessions", "stamp", "available", "error", "reset"]
