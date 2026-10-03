"""학사일정(F1)에서 시험에 필요한 기간만 읽는다 — 개강·종강 · 중간/최종 수업평가 · 중간/기말고사. 읽기 전용.

F1_Bachelor_agent/data/academic.db 의 items 표(원천 값)를 SQLite 읽기 전용 모드로 연다 (F3 academic_calendar 와 같은 방식).
쓰는 열: title · start_date · end_date · removed_at

실측(2026-10-01) — 학사일정 표에는 이런 행이 있다:
    '제2학기 개강' 2026-09-01 · '제2학기 종강' 2026-12-21                 → 학기 범위
    '제2학기 중간 수업평가' 2026-10-12 ~ 10-23                             → 중간고사 임의 일정을 잡는 기간 (사용자 요청)
    '제2학기 중간고사'     2026-10-19 ~ 10-23                             → 그 안에서 먼저 고르는 주간
    '제2학기 최종 수업평가' 2026-12-15 ~ 12-31                             → 기말고사 임의 일정 기간 (종강까지로 자른다)
    '제2학기 기말고사'     2026-12-15 ~ 12-21
  학과 공지에서 온 '중간고사 시험기간 302호, 402호 강의실 … 열람' 같은 행도 있다 — 이름이 **정확히** 맞는 행만 쓴다.

F1 이 없거나 아직 수집 전이면 available=False 를 주고, 임의 일정을 만들지 않는다(날짜를 지어내지 않는다).
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path
from typing import Any, Optional

from . import config as C

_T = r"^\s*제\s*([12])\s*학기\s*"
_PATTERNS = {
    "open": re.compile(_T + r"개강\s*$"),
    "close": re.compile(_T + r"종강\s*$"),
    "midEval": re.compile(_T + r"중간\s*수업\s*평가\s*$"),
    "finalEval": re.compile(_T + r"(?:최종|기말)\s*수업\s*평가\s*$"),
    "midExam": re.compile(_T + r"중간\s*고사\s*$"),
    "finalExam": re.compile(_T + r"기말\s*고사\s*$"),
}

_cache: dict[str, Any] = {"key": None, "value": None}


def _d(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def _semester(term: str, start: date) -> str:
    """'제2학기' + 시작일 → '2026-2'. 2학기 평가가 1~2월로 넘어가면 앞 해의 2학기다."""
    year = start.year - 1 if term == "2" and start.month <= 2 else start.year
    return f"{year}-{term}"


def _rows(db: Path) -> Optional[list[sqlite3.Row]]:
    if not db.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    con.row_factory = sqlite3.Row
    try:
        return list(con.execute("SELECT title, start_date, end_date FROM items WHERE removed_at IS NULL"))
    except sqlite3.Error:
        return None
    finally:
        con.close()


def load(db: Optional[Path] = None) -> dict:
    """{available, semesters: {'2026-2': {open, close, midEval, midExam, finalEval, finalExam}}}  각 값은 (시작, 끝) 또는 날짜."""
    path = Path(db or C.F1_DB)
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError:
        key = (str(path), None, None)
    if _cache["key"] == key:
        return _cache["value"]
    rows = _rows(path)
    if rows is None:
        value = {"available": False, "semesters": {}}
        _cache.update(key=key, value=value)
        return value
    sems: dict[str, dict] = {}
    for r in rows:
        title = r["title"] or ""
        start = _d(r["start_date"])
        if not start:
            continue
        end = _d(r["end_date"]) or start
        for name, pat in _PATTERNS.items():
            m = pat.match(title)
            if not m:
                continue
            slot = sems.setdefault(_semester(m.group(1), start), {})
            span = (start, max(start, end))
            # 같은 이름이 둘이면(원천 두 곳) 더 넓은 기간을 쓴다
            old = slot.get(name)
            slot[name] = span if old is None else (min(old[0], span[0]), max(old[1], span[1]))
    value = {"available": True, "semesters": sems}
    _cache.update(key=key, value=value)
    return value


def periods(semester: str, db: Optional[Path] = None) -> dict:
    """한 학기의 시험 관련 기간. 없으면 None. 날짜는 date.

    {available, semester, start, end,
     midterm: {evaluation, exam, window}, final: {evaluation, exam, window}}
      window = 임의 일정을 잡는 기간 — 수업평가 기간(없으면 시험 주간), 종강을 넘지 않게 자른다
    """
    cal = load(db)
    s = cal["semesters"].get(semester, {})
    start = (s.get("open") or (None, None))[0]
    end = (s.get("close") or (None, None))[0]

    def part(ev: str, ex: str) -> dict:
        evaluation, exam = s.get(ev), s.get(ex)
        window = evaluation or exam
        if window and end and window[1] > end:
            window = (window[0], max(window[0], end))       # 최종 수업평가는 종강 뒤까지 간다 — 수업은 종강까지다
        return {"evaluation": evaluation, "exam": exam, "window": window}

    return {"available": cal["available"], "semester": semester, "start": start, "end": end,
            "midterm": part("midEval", "midExam"), "final": part("finalEval", "finalExam")}


def label(span: Optional[tuple[date, date]]) -> str:
    if not span:
        return ""
    a, b = span
    return f"{a.month}/{a.day}~{b.month}/{b.day}" if a != b else f"{a.month}/{a.day}"


def reset_cache() -> None:
    _cache.update(key=None, value=None)


__all__ = ["load", "periods", "label", "reset_cache"]
