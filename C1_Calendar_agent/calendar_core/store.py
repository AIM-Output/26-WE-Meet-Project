"""C1 내 일정·할 일 저장소 — SQLite (표준 라이브러리만 사용).

한 테이블(user_events)에 일정과 할 일을 같이 둔다 (Notion Routine Planner 의 Schedule DB 와 같은 구조).
  is_todo=1 이면 "할 일" — 캘린더에도 보이고 To Do List 에서 완료(done) 체크를 할 수 있다.

여기에 있는 것은 캘린더 소스 중 **내 일정**(C1 3절 kind=user)뿐이다. 학사(F1)·마감(F6)·수업(F3)은
각 기능 폴더의 DB 에 있고 /api/events 에서 합쳐진다.

날짜는 프론트가 준 문자열을 그대로 둔다:
  종일   start='YYYY-MM-DD', end='YYYY-MM-DD'(exclusive) 또는 NULL
  시간   start='YYYY-MM-DDTHH:MM:SS', end=같은 형식 또는 NULL
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
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
    origin     TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

# 예전 DB 에 없던 열 — 있으면 건너뛴다
MIGRATIONS = {
    "is_todo": "ALTER TABLE user_events ADD COLUMN is_todo INTEGER NOT NULL DEFAULT 0",
    "done": "ALTER TABLE user_events ADD COLUMN done INTEGER NOT NULL DEFAULT 0",
    "origin": "ALTER TABLE user_events ADD COLUMN origin TEXT",
}

# origin = 이 일정을 어디서 가져왔는지 (학사 일정 '내 일정에 넣기' → 'ac:…'). 만들 때만 정하고 고치지 않는다.
FIELDS = ("title", "start", "end", "all_day", "category", "memo", "is_todo", "done")
CREATE_FIELDS = (*FIELDS, "origin")
BOOL_FIELDS = {"all_day", "is_todo", "done"}


def init() -> None:
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    _adopt_legacy_db()
    with _conn() as con:
        con.executescript(SCHEMA)
        cols = {r["name"] for r in con.execute("PRAGMA table_info(user_events)")}
        for col, sql in MIGRATIONS.items():
            if col not in cols:
                con.execute(sql)


def _adopt_legacy_db() -> None:
    """2026-09-30 이전에 쓰던 univ_us_local/data/univus.db 를 이 폴더로 **한 번만** 옮긴다.

    옛 자리가 비어 있거나 새 자리에 이미 DB 가 있으면 아무것도 하지 않는다.
    서버가 아직 옛 코드로 떠 있어 파일이 잠겨 있으면 옮기지 못하므로 복사만 하고 알린다
    (그 서버를 끄고 다시 켜면 이 함수는 더 이상 할 일이 없다).
    """
    if C.DB_PATH.exists() or not C.LEGACY_DB.exists() or C.LEGACY_DB == C.DB_PATH:
        return
    try:
        shutil.move(str(C.LEGACY_DB), str(C.DB_PATH))
    except OSError as e:                          # 옛 서버가 파일을 붙잡고 있다 (Windows)
        shutil.copy2(str(C.LEGACY_DB), str(C.DB_PATH))
        print(f"[C1] 옛 일정 DB 를 복사했습니다(옮기지 못함: {e}). "
              f"옛 서버를 끈 뒤 {C.LEGACY_DB} 를 지우세요.", file=sys.stderr)


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
            "origin": r["origin"],
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


def find_by_origin(origin: str) -> Optional[dict]:
    with _conn() as con:
        r = con.execute("SELECT * FROM user_events WHERE origin = ? ORDER BY id LIMIT 1", (origin,)).fetchone()
    return _row_to_event(r) if r else None


def create_event(**fields) -> dict:
    now = datetime.now().isoformat(timespec="seconds")
    values = {k: fields.get(k) for k in CREATE_FIELDS}
    for k in BOOL_FIELDS:
        values[k] = int(bool(values[k]))
    values["memo"] = values["memo"] or ""
    values["category"] = values["category"] or "personal"
    with _conn() as con:
        cur = con.execute(
            f"INSERT INTO user_events ({', '.join(CREATE_FIELDS)}, created_at, updated_at) "
            f"VALUES ({', '.join('?' * (len(CREATE_FIELDS) + 2))})",
            (*[values[k] for k in CREATE_FIELDS], now, now),
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


# ---------------------------------------------------------------- 옛 프로필 (옮기기용)
# 프로필은 C2_Profile_agent 로 옮겼다. F1 을 붙일 때 잠깐 이 DB 의 kv 표에 두었던 것이
# 남아 있으면 백엔드(app/student_profile.py)가 한 번 꺼내서 C2 로 옮긴다.

def take_legacy_profile() -> Optional[dict]:
    """kv 의 옛 프로필을 꺼내고 지운다. 없으면 None."""
    with _conn() as con:
        r = con.execute("SELECT value FROM kv WHERE key = 'profile'").fetchone()
        if not r:
            return None
        con.execute("DELETE FROM kv WHERE key = 'profile'")
    try:
        p = json.loads(r["value"])
    except ValueError:
        return None
    return p if isinstance(p, dict) else None


def count_events() -> dict:
    with _conn() as con:
        total = int(con.execute("SELECT COUNT(*) FROM user_events").fetchone()[0])
        todos = int(con.execute("SELECT COUNT(*) FROM user_events WHERE is_todo = 1").fetchone()[0])
        done = int(con.execute("SELECT COUNT(*) FROM user_events WHERE is_todo = 1 AND done = 1").fetchone()[0])
    return {"total": total, "todos": todos, "done": done}
