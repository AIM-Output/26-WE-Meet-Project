"""과제 원장 — SQLite 한 파일 (data/eclass.db). 표준 라이브러리만 쓴다.

수집기(runner, C3 .venv)가 수집 직후 반영(reconcile)하고, 대시보드 백엔드가 같은 파일을 읽고 '내가 체크함'을 쓴다
→ WAL + busy_timeout.

표
  items    과제·퀴즈·동영상 마감 하나 (id = 'dl:<cmid>'). e클래스 값(이름·마감·제출 상태 …)은 수집할 때마다 덮어쓰고,
           **사용자 값(user_done · estimate_hours)은 수집이 건드리지 않는다** (F6-R34).
           사라지면 지우지 않고 removed_at 만 적는다 (F6-R23). 마감이 바뀌면 prev_due · changed_at (F6-R22).
  changes  신규·마감 변경·삭제·제출 확인·승격 이력. notified=0 인 것은 백엔드가 알림 센터로 보낸다 (F6-R42·R43)
  meta     updated_at(화면 갱신 판단) · reconciled(마지막으로 반영한 deadlines.json 의 updated_at) · 알림 설정
  feed     새 글·자료 (공지 게시판 글 · 자료실 글 · 강의자료 파일) — manifest.json 에서 만든다(feed.py). 읽음 · 알림 보냄 · 기준선
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS items (
    id             TEXT PRIMARY KEY,
    cmid           TEXT,
    mod            TEXT,
    type           TEXT NOT NULL,
    source         TEXT NOT NULL,
    course         TEXT NOT NULL DEFAULT '',
    course_id      TEXT NOT NULL DEFAULT '',
    name           TEXT NOT NULL,
    url            TEXT NOT NULL DEFAULT '',
    start          TEXT NOT NULL DEFAULT '',
    due            TEXT NOT NULL DEFAULT '',
    status         TEXT NOT NULL DEFAULT '',
    submitted      INTEGER NOT NULL DEFAULT 0,
    graded         TEXT NOT NULL DEFAULT '',
    description    TEXT NOT NULL DEFAULT '',
    attachments    TEXT NOT NULL DEFAULT '[]',
    first_seen     TEXT NOT NULL,
    last_seen      TEXT NOT NULL,
    removed_at     TEXT,
    changed_at     TEXT,
    prev_due       TEXT,
    submitted_at   TEXT,
    promoted_at    TEXT,
    user_done      INTEGER NOT NULL DEFAULT 0,
    user_done_at   TEXT,
    estimate_hours REAL,
    baseline       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS items_due ON items(due);
CREATE TABLE IF NOT EXISTS changes (
    seq      INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id  TEXT NOT NULL,
    kind     TEXT NOT NULL,
    before   TEXT,
    after    TEXT,
    at       TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS changes_item ON changes(item_id);
CREATE TABLE IF NOT EXISTS feed (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    course      TEXT NOT NULL DEFAULT '',
    course_id   TEXT NOT NULL DEFAULT '',
    board       TEXT NOT NULL DEFAULT '',
    title       TEXT NOT NULL,
    url         TEXT NOT NULL DEFAULT '',
    path        TEXT NOT NULL DEFAULT '',
    posted_at   TEXT,
    fetched_at  TEXT,
    size        INTEGER,
    attachments TEXT NOT NULL DEFAULT '[]',
    first_seen  TEXT NOT NULL,
    read_at     TEXT,
    notified    INTEGER NOT NULL DEFAULT 0,
    baseline    INTEGER NOT NULL DEFAULT 0,
    removed_at  TEXT
);
CREATE INDEX IF NOT EXISTS feed_seen ON feed(first_seen);
"""

_initialized: set[str] = set()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout = 15000")
        key = str(C.DB_PATH)
        if key not in _initialized:
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(SCHEMA)
            _initialized.add(key)
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_meta(con: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    r = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r["value"] if r and r["value"] is not None else default


def set_meta(con: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    con.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value))


def get_json(con: sqlite3.Connection, key: str, default: Any) -> Any:
    raw = get_meta(con, key)
    if raw is None:
        return default
    try:
        return json.loads(raw)
    except ValueError:
        return default


def set_json(con: sqlite3.Connection, key: str, value: Any) -> None:
    set_meta(con, key, json.dumps(value, ensure_ascii=False))


def touch(con: sqlite3.Connection) -> str:
    """화면이 다시 불러오게 updated_at 을 올린다 (수집 반영 · 내가 체크함 · 소요시간)."""
    t = datetime.now().isoformat(timespec="milliseconds")
    set_meta(con, "updated_at", t)
    return t


def add_change(con: sqlite3.Connection, item_id: str, kind: str, before: Any = None, after: Any = None,
               notified: bool = False, at: Optional[str] = None) -> None:
    con.execute("INSERT INTO changes(item_id, kind, before, after, at, notified) VALUES (?, ?, ?, ?, ?, ?)",
                (item_id, kind, None if before is None else json.dumps(before, ensure_ascii=False),
                 None if after is None else json.dumps(after, ensure_ascii=False), at or now_iso(), int(notified)))
