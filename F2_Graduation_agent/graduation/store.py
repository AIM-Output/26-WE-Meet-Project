"""저장소 — SQLite 한 파일 (data/graduation.db). 표준 라이브러리만.

원천 값과 사용자 값을 나눈다 (F1 의 items/events 와 같은 생각 — 다시 가져와도 내 지정이 사라지지 않게, F2-R05)
  courses         학사정보시스템 기이수성적 — 가져올 때마다 통째로 바뀐다
  manual_courses  직접 입력한 과목 (타대 학점인정·편입·누락분, F2-R04) — 가져오기와 무관하게 남는다
  overrides       과목 하나에 대한 내 값: 영역 지정(area) · 계산 제외(excluded)
  category_map    '교과구분 → 영역' 내 지정 (한 번 고르면 다음부터 자동, F2 8절)
  certs           졸업인증 체크·메모 (F2-R41)
  rulesets        룰셋 내 수정본 — 학과·전공·입학년도·이수유형 하나당 하나 (F2-R13)
  plans           가정 계산 '내 계획' (F2-R53)
  meta            imported_at · import_count · updated_at(화면이 다시 부를지 판단)
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id           TEXT PRIMARY KEY,
    year         INTEGER,
    semester     TEXT,
    code         TEXT,
    name         TEXT NOT NULL,
    credits      REAL NOT NULL,
    grade        TEXT,
    raw_category TEXT,
    ge_area      TEXT,
    status       TEXT,
    retake       TEXT,
    seq          INTEGER,
    fetched_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS manual_courses (
    id           TEXT PRIMARY KEY,
    year         INTEGER,
    semester     TEXT,
    code         TEXT,
    name         TEXT NOT NULL,
    credits      REAL NOT NULL,
    grade        TEXT,
    raw_category TEXT,
    ge_area      TEXT,
    memo         TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS overrides (
    course_id  TEXT PRIMARY KEY,
    area       TEXT,
    excluded   INTEGER,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS category_map (
    raw        TEXT PRIMARY KEY,
    area       TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS certs (
    key        TEXT PRIMARY KEY,
    state      TEXT NOT NULL,
    memo       TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rulesets (
    target       TEXT PRIMARY KEY,
    data         TEXT NOT NULL,
    base_id      TEXT,
    base_version INTEGER,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    track       TEXT NOT NULL,
    assumptions TEXT NOT NULL,
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


def loads(s: Optional[str]) -> Any:
    try:
        return json.loads(s) if s else None
    except ValueError:
        return None


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
    """무언가 바뀌었다 — 화면이 /api/status 의 updatedAt 을 보고 다시 부른다."""
    t = datetime.now().isoformat(timespec="milliseconds")
    set_meta(con, "updated_at", t)
    return t


def course_id(year: Any, semester: Any, code: Any, name: Any) -> str:
    """학사정보시스템 과목 id — 같은 학기·같은 과목이면 다시 가져와도 같은 id (내 지정이 따라간다)."""
    raw = f"{year}|{semester}|{(code or '').strip().upper()}|{(name or '').strip()}"
    return "gc:" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
