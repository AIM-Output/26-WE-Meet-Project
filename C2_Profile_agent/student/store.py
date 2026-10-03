"""저장소 — SQLite 한 파일 (data/profile.db). 표준 라이브러리만.

표
  fields  항목 하나 = 한 줄 {key, value(JSON), filled_by(auto|user), edited, updated_at}
          항목마다 '자동(학사시스템)'인지 '내가 입력'인지 남긴다 → 재수집이 사용자 수정을 덮어쓰지 않는다 (C2-R05)
  meta    updated_at(마지막 변경) · imported_at · onboarding_skipped
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS fields (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    filled_by  TEXT NOT NULL,
    edited     INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
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


def rows(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["key"]: r for r in con.execute("SELECT * FROM fields")}
