"""저장소 — SQLite 한 파일 (data/briefing.db). 표준 라이브러리만.

  briefings  날짜마다 한 줄 = 그날 브리핑 **스냅샷**(F10 7절). 다시 만들기(manual)는 같은 줄을 덮어쓴다(F10-R04).
             first_source · first_generated_at 은 처음 만들 때 값 그대로 — 다시 만들어도 '놓친 브리핑'이었다는 사실은 남는다.
  meta       settings(JSON — 기본값과 다른 값만) · updated_at(화면이 다시 받을 신호) · waiting_since(수집 기다림 시작)
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS briefings (
    date                TEXT PRIMARY KEY,                  -- YYYY-MM-DD (대상 날짜)
    generated_at        TEXT NOT NULL,                     -- 실제로 (마지막에) 만든 시각
    scheduled_for       TEXT NOT NULL,                     -- 예정 시각 HH:MM (그때의 설정)
    source              TEXT NOT NULL,                     -- scheduled | catchup | manual
    first_source        TEXT NOT NULL,
    first_generated_at  TEXT NOT NULL,
    headline            TEXT,                              -- LLM 한 줄 — 실패하면 NULL (그 줄만 빠진다)
    summary             TEXT NOT NULL DEFAULT '',          -- 규칙 한 줄 '수업 3 · 마감 3' (접힘·알림 본문)
    sections            TEXT NOT NULL DEFAULT '[]',        -- JSON
    counts              TEXT NOT NULL DEFAULT '{}',        -- JSON
    gaps                TEXT NOT NULL DEFAULT '[]',        -- JSON — 못 읽은 재료(기능 이름)
    model               TEXT,
    prompt_version      TEXT
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    C.ensure_dirs()
    con = sqlite3.connect(str(C.DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)            # IF NOT EXISTS 라 싸다 — 파일을 지워도 다음 연결에서 다시 생긴다
        yield con
        con.commit()
    finally:
        con.close()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_meta(con: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    r = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r["value"] if r and r["value"] is not None else default


def set_meta(con: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    if value is None:
        con.execute("DELETE FROM meta WHERE key = ?", (key,))
    else:
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))


def touch(con: sqlite3.Connection) -> str:
    """브리핑·설정이 바뀌었다 — 화면이 /api/status 의 briefing.updatedAt 을 보고 다시 받는다."""
    t = datetime.now().isoformat(timespec="microseconds")
    set_meta(con, "updated_at", t)
    return t


def loads(raw: Optional[str], default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def get(con: sqlite3.Connection, day: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM briefings WHERE date = ?", (day,)).fetchone()


def latest_before(con: sqlite3.Connection, day: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM briefings WHERE date < ? ORDER BY date DESC LIMIT 1", (day,)).fetchone()


def put(con: sqlite3.Connection, b: dict) -> None:
    """같은 날짜가 있으면 덮어쓴다 — 처음 만든 source·시각은 그대로 둔다."""
    old = get(con, b["date"])
    first_source = old["first_source"] if old else b["source"]
    first_at = old["first_generated_at"] if old else b["generatedAt"]
    con.execute(
        "INSERT OR REPLACE INTO briefings(date, generated_at, scheduled_for, source, first_source, first_generated_at, "
        "headline, summary, sections, counts, gaps, model, prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (b["date"], b["generatedAt"], b["scheduledFor"], b["source"], first_source, first_at, b.get("headline"),
         b.get("summary") or "", dumps(b.get("sections") or []), dumps(b.get("counts") or {}), dumps(b.get("gaps") or []),
         b.get("model"), b.get("promptVersion")))


def rows(con: sqlite3.Connection, limit: int = 60) -> list[sqlite3.Row]:
    return list(con.execute("SELECT * FROM briefings ORDER BY date DESC LIMIT ?", (limit,)))


def delete_before(con: sqlite3.Connection, day: str) -> int:
    """보관 기간이 지난 것부터 지운다 (F10 9절)."""
    return con.execute("DELETE FROM briefings WHERE date < ?", (day,)).rowcount
