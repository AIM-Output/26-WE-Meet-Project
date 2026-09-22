"""사용자 일정·할 일 저장소 — SQLite (표준 라이브러리만 사용).

한 테이블(user_events)에 일정과 할 일을 같이 둔다 (Notion Routine Planner 의 Schedule DB 와 같은 구조).
  is_todo=1 이면 "할 일" — 캘린더에도 보이고 To Do List 에서 완료(done) 체크를 할 수 있다.

날짜는 프론트가 준 문자열을 그대로 둔다:
  종일   start='YYYY-MM-DD', end='YYYY-MM-DD'(exclusive) 또는 NULL
  시간   start='YYYY-MM-DDTHH:MM:SS', end=같은 형식 또는 NULL
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS user_events (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    title      TEXT NOT NULL,
    start      TEXT NOT NULL,
    end        TEXT,
    all_day    INTEGER NOT NULL DEFAULT 0,
    category   TEXT NOT NULL DEFAULT 'personal',
    memo       TEXT NOT NULL DEFAULT '',
    is_todo    INTEGER NOT NULL DEFAULT 0,
    done       INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""

# 예전 DB 에 없던 열 — 있으면 건너뛴다
MIGRATIONS = {
    "is_todo": "ALTER TABLE user_events ADD COLUMN is_todo INTEGER NOT NULL DEFAULT 0",
    "done": "ALTER TABLE user_events ADD COLUMN done INTEGER NOT NULL DEFAULT 0",
}

FIELDS = ("title", "start", "end", "all_day", "category", "memo", "is_todo", "done")
BOOL_FIELDS = {"all_day", "is_todo", "done"}


def init() -> None:
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript(SCHEMA)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(user_events)")}
        for col, sql in MIGRATIONS.items():
            if col not in cols:
                con.execute(sql)


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(C.DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        yield con
        con.commit()
    finally:
        con.close()


def _row_to_event(r: sqlite3.Row) -> dict:
    cat = C.CATEGORIES.get(r["category"], C.CATEGORIES["etc"])
    return {
        "id": str(r["id"]),
        "title": r["title"],
        "start": r["start"],
        "end": r["end"],
        "allDay": bool(r["all_day"]),
        "editable": True,
        "extendedProps": {
            "kind": "user",
            "category": r["category"],
            "categoryLabel": cat["label"],
            "color": cat["color"],
            "memo": r["memo"],
            "isTodo": bool(r["is_todo"]),
            "done": bool(r["done"]),
        },
    }


def list_events() -> list[dict]:
    with _conn() as con:
        rows = con.execute("SELECT * FROM user_events ORDER BY start").fetchall()
    return [_row_to_event(r) for r in rows]


def get_event(event_id: int) -> Optional[dict]:
    with _conn() as con:
        r = con.execute("SELECT * FROM user_events WHERE id = ?", (event_id,)).fetchone()
    return _row_to_event(r) if r else None


def create_event(**fields) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    values = {k: fields.get(k) for k in FIELDS}
    for k in BOOL_FIELDS:
        values[k] = int(bool(values[k]))
    values["memo"] = values["memo"] or ""
    values["category"] = values["category"] or "personal"
    with _conn() as con:
        cur = con.execute(
            "INSERT INTO user_events (title, start, end, all_day, category, memo, is_todo, done, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (*[values[k] for k in FIELDS], now, now),
        )
        new_id = cur.lastrowid
    return get_event(int(new_id))  # type: ignore[return-value]


def update_event(event_id: int, fields: dict) -> Optional[dict]:
    sets = {k: v for k, v in fields.items() if k in FIELDS}
    for k in BOOL_FIELDS & sets.keys():
        sets[k] = int(bool(sets[k]))
    if not sets:
        return get_event(event_id)
    sets["updated_at"] = datetime.now().isoformat(timespec="seconds")
    cols = ", ".join(f"{k} = ?" for k in sets)
    with _conn() as con:
        cur = con.execute(f"UPDATE user_events SET {cols} WHERE id = ?", (*sets.values(), event_id))
        if cur.rowcount == 0:
            return None
    return get_event(event_id)


def delete_event(event_id: int) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM user_events WHERE id = ?", (event_id,))
        return cur.rowcount > 0


def count_events() -> dict:
    with _conn() as con:
        total = int(con.execute("SELECT COUNT(*) FROM user_events").fetchone()[0])
        todos = int(con.execute("SELECT COUNT(*) FROM user_events WHERE is_todo = 1").fetchone()[0])
        done = int(con.execute("SELECT COUNT(*) FROM user_events WHERE is_todo = 1 AND done = 1").fetchone()[0])
    return {"total": total, "todos": todos, "done": done}
