"""저장소 — SQLite 한 파일 (data/placement.db). 표준 라이브러리만.

  blocks  등록된 학습 블록 한 줄 — 캘린더 id 는 `pb:<id>`
          task_type assignment(F7 과제) | todo(C1 할 일) | study(공강 공부 — 시험) · ref_id(dl:<활동> · todo:<id> · ex:<시험>)
          (exam = 2026-10-06 판의 F5 하루치 배치 — 지금은 만들지 않는다)
          date · start · end(HH:MM, 끝은 24:00 까지) · minutes · reason(근거 한 줄)
          placed_by auto(자동 배치) | user(내가 옮김 → 고정, F8-R30) · done(완료 체크, F8-R33)
  meta    updated_at · schema

**미리보기는 저장하지 않는다.** `배치하기`(service.register)를 눌렀을 때만 여기 들어온다 (F8 D4 · Frontend-Route 13-6).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    task_type   TEXT NOT NULL,                     -- exam | assignment
    ref_id      TEXT NOT NULL,                     -- st:<계획>:<날짜> (F5) · dl:<활동> (F6/F7)
    title       TEXT NOT NULL,
    course      TEXT NOT NULL DEFAULT '',
    color       TEXT NOT NULL DEFAULT '',
    date        TEXT NOT NULL,                     -- YYYY-MM-DD
    start       TEXT NOT NULL,                     -- HH:MM
    "end"       TEXT NOT NULL,                     -- HH:MM (24:00 까지)
    minutes     INTEGER NOT NULL,
    reason      TEXT NOT NULL DEFAULT '',          -- 무엇을 왜 여기에 (F8-R22)
    slot        TEXT NOT NULL DEFAULT '',          -- gap | evening — 배치될 때의 자리
    href        TEXT NOT NULL DEFAULT '',          -- 작업 화면 (/exams?exam=… · /assignments?item=…)
    placed_by   TEXT NOT NULL DEFAULT 'auto',      -- auto | user (옮기면 고정 — F8-R30)
    done        INTEGER NOT NULL DEFAULT 0,
    done_at     TEXT,
    batch       TEXT NOT NULL DEFAULT '',          -- 같은 '배치하기'로 들어온 것끼리 같은 값
    extra       TEXT NOT NULL DEFAULT '{}',        -- JSON — 공부 블록의 시험 날짜·유형·진도 (공부 캘린더가 쓴다)
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_blocks_date ON blocks(date);
CREATE INDEX IF NOT EXISTS ix_blocks_ref ON blocks(ref_id);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# 컬럼을 더할 때는 여기에 (이름, 정의)를 적는다
_ADDED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("extra", "TEXT NOT NULL DEFAULT '{}'"),          # 2026-10-07 — 공강 공부 블록
)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    C.ensure_dirs()
    con = sqlite3.connect(str(C.DB_PATH), timeout=10)
    con.row_factory = sqlite3.Row
    try:
        con.executescript(SCHEMA)            # IF NOT EXISTS 라 싸다 — 파일을 지워도 다음 연결에서 다시 생긴다
        cols = {r["name"] for r in con.execute("PRAGMA table_info(blocks)")}
        for name, ddl in _ADDED_COLUMNS:
            if name not in cols:                 # 옛 DB 는 열릴 때 조용히 따라온다
                con.execute(f"ALTER TABLE blocks ADD COLUMN {name} {ddl}")
        con.execute("INSERT OR IGNORE INTO meta(key, value) VALUES ('schema', '1')")
        yield con
        con.commit()
    finally:
        con.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def touch(con: sqlite3.Connection) -> str:
    """블록이 바뀌었다 — 화면이 /api/status 의 placement.updatedAt 을 보고 캘린더를 다시 받는다."""
    t = datetime.now().isoformat(timespec="microseconds")
    con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('updated_at', ?)", (t,))
    return t


def updated_at(con: sqlite3.Connection) -> Optional[str]:
    r = con.execute("SELECT value FROM meta WHERE key = 'updated_at'").fetchone()
    return r["value"] if r else None


def rows(con: sqlite3.Connection, start: Optional[str] = None, end: Optional[str] = None) -> list[sqlite3.Row]:
    sql, args = "SELECT * FROM blocks", []
    cond = []
    if start:
        cond.append("date >= ?")
        args.append(start)
    if end:
        cond.append("date <= ?")
        args.append(end)
    if cond:
        sql += " WHERE " + " AND ".join(cond)
    return list(con.execute(sql + " ORDER BY date, start, id", args))


def get(con: sqlite3.Connection, block_id: int) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM blocks WHERE id = ?", (block_id,)).fetchone()


def insert(con: sqlite3.Connection, b: dict, batch: str) -> int:
    t = now()
    cur = con.execute(
        'INSERT INTO blocks(task_type, ref_id, title, course, color, date, start, "end", minutes, reason, slot, href, '
        "placed_by, batch, extra, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'auto', ?, ?, ?, ?)",
        (b["taskType"], b["refId"], b["title"], b.get("course") or "", b.get("color") or "", b["date"], b["start"],
         b["end"], b["minutes"], b.get("reason") or "", b.get("slot") or "", b.get("href") or "", batch,
         json.dumps({k: b[k] for k in EXTRA_KEYS if b.get(k) is not None}, ensure_ascii=False), t, t))
    return int(cur.lastrowid)


EXTRA_KEYS = ("examDate", "typeLabel", "percent")


def extra(r: Any) -> dict:
    try:
        v = json.loads(r["extra"] or "{}")
        return v if isinstance(v, dict) else {}
    except (ValueError, IndexError, KeyError):
        return {}


def update(con: sqlite3.Connection, block_id: int, fields: dict[str, Any]) -> None:
    if not fields:
        return
    cols = ", ".join(f'"{k}" = ?' for k in fields)
    con.execute(f"UPDATE blocks SET {cols}, updated_at = ? WHERE id = ?", (*fields.values(), now(), block_id))


def delete(con: sqlite3.Connection, ids: list[int]) -> int:
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    return con.execute(f"DELETE FROM blocks WHERE id IN ({marks})", ids).rowcount
