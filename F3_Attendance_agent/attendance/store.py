"""저장소 — SQLite 한 파일 (data/attendance.db). 표준 라이브러리만.

원천 값과 사용자 값을 나눈다 (F1 items/events, F2 courses/overrides 와 같은 생각).
회차 자체는 저장하지 않는다 — 시간표 × 학사일정으로 매번 만든다(sessions.py). 저장하는 것은:
  semesters  학기 범위·휴업일을 내가 고친 값 (학사일정에서 못 찾았을 때, F3-R11)
  courses    학기별 과목 — e클래스에서 온 것(eclass) + 직접 추가한 것(manual, F3-R05).
             과목 설정(한도 비율·지각 환산, F3-R04) · 누적 직접 조정(F3-R23) · 제외(수강 취소) ·
             마지막으로 알린 단계(F3-R33) · 시간표 자동 수집 결과(원문·상태)
  meetings   시간표 판 — 과목 하나에 여러 판(적용 시작일별, F3-R17). filled_by 로 자동/내가 고침 구분(F3-R02a)
  marks      회차 하나에 대한 내 기록 — 출결 · 휴강/되돌리기 · 메모 (회차 id `cl:<과목>:<날짜>` 로 붙는다)
  makeups    내가 추가한 보강 회차 (F3-R16)
  alerts     만든 경고 알림 (같은 단계 반복 알림 막기)
  meta       updated_at · period_map(교시 시각을 내가 고친 값) · warning_gpa · schema(아래 _migrate)
"""
from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS semesters (
    id          TEXT PRIMARY KEY,
    user_start  TEXT,
    user_end    TEXT,
    holidays    TEXT NOT NULL DEFAULT '[]',
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS courses (
    semester          TEXT NOT NULL,
    id                TEXT NOT NULL,
    name              TEXT NOT NULL,
    short             TEXT NOT NULL,
    code              TEXT NOT NULL DEFAULT '',
    section           TEXT NOT NULL DEFAULT '',
    source            TEXT NOT NULL,
    color             TEXT,
    limit_ratio       REAL,
    late_to_absence   INTEGER,
    adjust_absent     INTEGER NOT NULL DEFAULT 0,
    adjust_late       INTEGER NOT NULL DEFAULT 0,
    excluded          INTEGER NOT NULL DEFAULT 0,
    alert_level       TEXT,
    tt_status         TEXT,
    tt_message        TEXT,
    tt_raw            TEXT,
    tt_auto           TEXT,
    tt_checked_at     TEXT,
    seq               INTEGER NOT NULL DEFAULT 0,
    created_at        TEXT NOT NULL,
    updated_at        TEXT NOT NULL,
    PRIMARY KEY (semester, id)
);
CREATE TABLE IF NOT EXISTS meetings (
    semester    TEXT NOT NULL,
    course_id   TEXT NOT NULL,
    valid_from  TEXT NOT NULL DEFAULT '',
    data        TEXT NOT NULL,
    filled_by   TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (semester, course_id, valid_from)
);
CREATE TABLE IF NOT EXISTS marks (
    id          TEXT PRIMARY KEY,
    semester    TEXT NOT NULL,
    course_id   TEXT NOT NULL,
    date        TEXT NOT NULL,
    attendance  TEXT,
    state       TEXT,
    memo        TEXT,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS marks_course ON marks(semester, course_id);
CREATE TABLE IF NOT EXISTS makeups (
    id          TEXT PRIMARY KEY,
    semester    TEXT NOT NULL,
    course_id   TEXT NOT NULL,
    date        TEXT NOT NULL,
    periods     TEXT NOT NULL,
    memo        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    semester    TEXT NOT NULL,
    course_id   TEXT NOT NULL,
    level       TEXT NOT NULL,
    title       TEXT NOT NULL,
    body        TEXT NOT NULL,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_initialized: set[str] = set()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def loads(s: Optional[str], default: Any = None) -> Any:
    try:
        return json.loads(s) if s else default
    except ValueError:
        return default


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout = 15000")
        if str(C.DB_PATH) not in _initialized or not C.DB_PATH.exists():
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(SCHEMA)
            _migrate(con)
            con.commit()
            _initialized.add(str(C.DB_PATH))
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_meta(con: sqlite3.Connection, key: str) -> Optional[str]:
    r = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else None


def set_meta(con: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    if value is None:
        con.execute("DELETE FROM meta WHERE key = ?", (key,))
        return
    con.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value))


def touch(con: sqlite3.Connection) -> str:
    """무언가 바뀌었다 — 화면이 /api/status 의 attendance.updatedAt 을 보고 다시 부른다."""
    t = datetime.now().isoformat(timespec="milliseconds")
    set_meta(con, "updated_at", t)
    return t


SCHEMA_VERSION = 2
_OLD_ID = re.compile(r"^(cl:.+:\d{4}-\d{2}-\d{2}):\d+(?:-\d+)*(:mk)?$")


def _migrate(con: sqlite3.Connection) -> None:
    """옛 기록을 지금 규칙으로 (한 번).
    v2 (2026-09-29) — 회차가 '교시'에서 '날(日)' 단위로 바뀌었다: id `cl:<과목>:<날짜>:<교시>[:mk]` → `cl:<과목>:<날짜>[:mk]`.
                      같은 날 기록이 둘이면 출결이 있는 쪽을 남긴다. 조퇴 입력이 없어졌다: early → late."""
    if int(get_meta(con, "schema") or 1) >= SCHEMA_VERSION:
        return
    for table in ("marks", "makeups"):
        for r in con.execute(f"SELECT * FROM {table}").fetchall():
            m = _OLD_ID.match(r["id"])
            if not m:
                continue
            new = m.group(1) + (m.group(2) or "")
            clash = con.execute(f"SELECT * FROM {table} WHERE id = ?", (new,)).fetchone()
            if clash is None:
                con.execute(f"UPDATE {table} SET id = ? WHERE id = ?", (new, r["id"]))
            elif table == "marks" and not clash["attendance"] and r["attendance"]:
                con.execute("DELETE FROM marks WHERE id = ?", (new,))
                con.execute("UPDATE marks SET id = ? WHERE id = ?", (new, r["id"]))
            else:
                con.execute(f"DELETE FROM {table} WHERE id = ?", (r["id"],))
    con.execute("UPDATE marks SET attendance = 'late' WHERE attendance = 'early'")
    set_meta(con, "schema", str(SCHEMA_VERSION))
