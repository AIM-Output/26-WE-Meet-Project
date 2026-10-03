"""학사일정(F1)에서 수업 회차에 필요한 것만 읽는다 — 개강·종강 · 휴업일 · 학교 지정 보강일. 읽기 전용.

F1_Bachelor_agent/data/academic.db 의 items 표(원천 값)를 SQLite 읽기 전용 모드로 연다. 쓰는 열:
    title · type · start_date · end_date · removed_at
F1 이 없거나 아직 수집 전이면 빈 값을 주고, 화면이 '직접 입력'을 연다 (F3-R11, 9절 '공휴일 정보가 없음').

실측(2026-09-28) — 학사일정 표에는 이런 행이 있다:
    '제2학기 개강' 2026-09-01 · '제2학기 종강' 2026-12-21                          → 학기 범위
    '추석연휴 (휴업)' 2026-09-24~25 (F1 이 type=holiday 로 만든다)                   → 휴업일
    '9. 24.(목) 추석연휴 보강' 2026-12-10                                            → 학교 지정 보강일
    '자체 보강일' 2026-12-08                                                        → 교수 재량 — 자동으로 넣지 않는다
"""
from __future__ import annotations

import re
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from . import config as C

_OPEN = re.compile(r"^\s*제\s*([12])\s*학기\s*개강\s*$")
_CLOSE = re.compile(r"^\s*제\s*([12])\s*학기\s*종강\s*$")
_MAKEUP = re.compile(r"^\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*\(\s*[월화수목금토일]\s*\)\s*(.+?)\s*보강\s*$")
_CLEAN = re.compile(r"\s*\(\s*휴업\s*\)\s*$")


def _rows(db: Optional[Path] = None) -> Optional[list[sqlite3.Row]]:
    path = Path(db or C.F1_DB)
    if not path.exists():
        return None
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        con.row_factory = sqlite3.Row
        return con.execute(
            "SELECT title, type, start_date, end_date FROM items "
            "WHERE removed_at IS NULL AND start_date IS NOT NULL").fetchall()
    except sqlite3.Error:
        return None
    finally:
        con.close()


def _d(s: Optional[str]) -> Optional[date]:
    try:
        return date.fromisoformat((s or "")[:10])
    except ValueError:
        return None


def load(db: Optional[Path] = None) -> dict:
    """{available, semesters: {'2026-2': {start, end}}, holidays: {날짜: 이름}, makeups: [{date, original, name}]}"""
    rows = _rows(db)
    if rows is None:
        return {"available": False, "semesters": {}, "holidays": {}, "makeups": []}
    sems: dict[str, dict] = {}
    holidays: dict[str, str] = {}
    makeups: list[dict] = []
    for r in rows:
        title = r["title"] or ""
        s = _d(r["start_date"])
        if not s:
            continue
        if m := _OPEN.match(title):
            sems.setdefault(f"{s.year}-{m.group(1)}", {})["start"] = s.isoformat()
        elif m := _CLOSE.match(title):
            # 2학기 종강이 해를 넘기면(1월) 학기 연도는 전년도
            y = s.year - 1 if m.group(1) == "2" and s.month <= 2 else s.year
            sems.setdefault(f"{y}-{m.group(1)}", {})["end"] = s.isoformat()
        elif r["type"] == "holiday":
            e = _d(r["end_date"]) or s
            name = _CLEAN.sub("", title).strip() or "휴업일"
            d = s
            while d <= e and (d - s).days < 31:
                holidays.setdefault(d.isoformat(), name)
                d += timedelta(days=1)
        elif m := _MAKEUP.match(title):
            try:
                orig = date(s.year, int(m.group(1)), int(m.group(2)))
            except ValueError:
                continue
            if orig > s:                                  # 1월 보강일이 전년도 12월 휴일을 메우는 경우
                orig = orig.replace(year=s.year - 1)
            makeups.append({"date": s.isoformat(), "original": orig.isoformat(), "name": m.group(3).strip()})
    return {"available": True, "semesters": sems, "holidays": holidays,
            "makeups": sorted(makeups, key=lambda x: x["date"])}


def fixed_holidays(start: date, end: date) -> dict[str, str]:
    """양력 고정 공휴일 (학사일정이 없을 때의 최소 보강)."""
    out = {}
    for y in range(start.year, end.year + 1):
        for md, name in C.FIXED_HOLIDAYS.items():
            d = date.fromisoformat(f"{y}-{md}")
            if start <= d <= end:
                out[d.isoformat()] = name
    return out


def semester_of(d: date) -> str:
    """날짜가 속한(또는 방학이면 가까운) 정규 학기 id — 학사일정이 없을 때의 추정. 3~8월 1학기, 9~2월 2학기."""
    if 3 <= d.month <= 8:
        return f"{d.year}-1"
    return f"{d.year if d.month >= 9 else d.year - 1}-2"


def semester_label(sid: str) -> str:
    y, t = sid.split("-")
    return f"{y}-{t}학기" if t in ("1", "2") else sid
