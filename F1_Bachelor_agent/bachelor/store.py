"""저장소 — SQLite 한 파일 (data/academic.db). 표준 라이브러리만 쓴다.

수집기(자식 프로세스)와 대시보드 백엔드(univ_us_local)가 같은 파일을 연다 → WAL + busy_timeout.

표
  sources        원천 4곳 (학교 학사일정 표 · 학사안내 · 내 학부 · 내 단과대학). 켜짐, 마지막 수집 시각·결과·건수 (F1-R04),
                 user_config(게시판 직접 지정) · runtime(찾아 둔 내 소속 홈페이지·게시판)
  posts          처리한 공지 글 (내용 해시로 '이미 처리한 글은 다시 처리하지 않는다', F1-R02)
  items          원천 하나가 준 일정 하나 (병합 전). 원문 값만 담는다 — 수집할 때마다 덮어쓴다
  events         화면에 보이는 학사 일정 하나 (병합 후). **사용자 값만** 담는다 — 숨김·승인·메모·알림 (D6)
                 → 재동기화가 사용자 값을 건드리지 않는다 (F1-R24)
  notifications  배달된 알림 (앱 내 알림, 놓친 알림 표시)
  meta           updated_at(화면 갱신 판단) · 알림 기준 시각 같은 설정
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
CREATE TABLE IF NOT EXISTS sources (
    key         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    kind        TEXT NOT NULL,
    config      TEXT NOT NULL,
    priority    INTEGER NOT NULL DEFAULT 3,
    builtin     INTEGER NOT NULL DEFAULT 0,
    enabled     INTEGER NOT NULL DEFAULT 1,
    last_run_at TEXT,
    last_ok_at  TEXT,
    last_result TEXT,
    last_count  INTEGER,
    last_error  TEXT,
    user_config TEXT NOT NULL DEFAULT '{}',
    runtime     TEXT NOT NULL DEFAULT '{}',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS posts (
    source_key   TEXT NOT NULL,
    post_id      TEXT NOT NULL,
    title        TEXT,
    url          TEXT,
    posted_at    TEXT,
    writer       TEXT,
    content_hash TEXT,
    fetched_at   TEXT,
    relevant     INTEGER NOT NULL DEFAULT 1,
    n_items      INTEGER NOT NULL DEFAULT 0,
    flags        TEXT NOT NULL DEFAULT '[]',
    version      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (source_key, post_id)
);
CREATE TABLE IF NOT EXISTS items (
    ident           TEXT PRIMARY KEY,
    event_id        TEXT NOT NULL,
    source_key      TEXT NOT NULL,
    post_id         TEXT,
    title           TEXT NOT NULL,
    norm            TEXT NOT NULL,
    start_date      TEXT,
    start_time      TEXT,
    end_date        TEXT,
    end_time        TEXT,
    type            TEXT NOT NULL,
    audience        TEXT NOT NULL,
    evidence        TEXT NOT NULL,
    confidence      REAL NOT NULL,
    semester        TEXT,
    url             TEXT,
    posted_at       TEXT,
    action_url      TEXT,
    action_label    TEXT,
    flags           TEXT NOT NULL DEFAULT '[]',
    first_seen      TEXT NOT NULL,
    last_seen       TEXT NOT NULL,
    removed_at      TEXT,
    prev            TEXT,
    changed_at      TEXT
);
CREATE INDEX IF NOT EXISTS items_event ON items(event_id);
CREATE INDEX IF NOT EXISTS items_source ON items(source_key, post_id);
CREATE TABLE IF NOT EXISTS events (
    id              TEXT PRIMARY KEY,
    user_status     TEXT,
    user_dates      TEXT,
    pinned          INTEGER NOT NULL DEFAULT 0,
    memo            TEXT NOT NULL DEFAULT '',
    reminders       TEXT,
    notify_since    TEXT,
    first_seen      TEXT NOT NULL,
    changed_at      TEXT,
    changed_before  TEXT,
    updated_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS notifications (
    id           TEXT PRIMARY KEY,
    kind         TEXT NOT NULL,
    ref_id       TEXT,
    title        TEXT NOT NULL,
    body         TEXT NOT NULL DEFAULT '',
    fire_at      TEXT NOT NULL,
    delivered_at TEXT NOT NULL,
    read_at      TEXT,
    missed       INTEGER NOT NULL DEFAULT 0,
    href         TEXT
);
CREATE INDEX IF NOT EXISTS notifications_fire ON notifications(fire_at);
"""


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def loads(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except ValueError:
        return default


_initialized: set[str] = set()


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """트랜잭션 하나. 끝나면 commit. 처음 열 때 표를 만들고 기본 원천을 넣는다."""
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout = 15000")
        if str(C.DB_PATH) not in _initialized or not C.DB_PATH.exists():
            con.execute("PRAGMA journal_mode = WAL")
            con.executescript(SCHEMA)
            _migrate(con)
            seed_sources(con)
            con.commit()
            _initialized.add(str(C.DB_PATH))
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ── meta ────────────────────────────────────────────────────

def get_meta(con: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    r = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r["value"] if r else default


def set_meta(con: sqlite3.Connection, key: str, value: Optional[str]) -> None:
    con.execute("INSERT INTO meta(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value))


def touch(con: sqlite3.Connection) -> None:
    """데이터가 바뀌었다는 표시 — 화면은 /api/status 의 academic.updatedAt 이 바뀔 때만 다시 불러온다."""
    set_meta(con, "updated_at", datetime.now().isoformat(timespec="milliseconds"))


# ── sources ─────────────────────────────────────────────────

def _migrate(con: sqlite3.Connection) -> None:
    """예전 DB 에 없던 열을 더한다."""
    cols = {r["name"] for r in con.execute("PRAGMA table_info(sources)")}
    for col in ("user_config", "runtime"):
        if col not in cols:
            con.execute(f"ALTER TABLE sources ADD COLUMN {col} TEXT NOT NULL DEFAULT '{{}}'")


def seed_sources(con: sqlite3.Connection) -> None:
    """기본 원천 4곳을 넣는다. 이미 있으면 설정만 최신으로 — 사용자가 바꾼 켜짐(enabled)·직접 지정(user_config)·
    찾아 둔 게시판(runtime)은 그대로 둔다. 목록에 없는 원천(예전 기본값·사용자가 추가했던 게시판)은 지운다 —
    그 원천에서 온 일정은 '원문 삭제됨'으로 남아 사용자 메모·숨김이 보존되고, 화면에는 나오지 않는다."""
    now = now_iso()
    keys = [s["key"] for s in C.BUILTIN_SOURCES]
    for s in C.BUILTIN_SOURCES:
        cfg = {k: v for k, v in s.items() if k not in ("key", "name", "kind", "priority", "enabled")}
        con.execute(
            "INSERT INTO sources(key, name, kind, config, priority, builtin, enabled, created_at) "
            "VALUES (?, ?, ?, ?, ?, 1, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET name = excluded.name, kind = excluded.kind, config = excluded.config, "
            "priority = excluded.priority, builtin = 1",
            (s["key"], s["name"], s["kind"], dumps(cfg), s["priority"], int(s["enabled"]), now),
        )
    q = ",".join("?" * len(keys))
    for r in con.execute(f"SELECT key FROM sources WHERE key NOT IN ({q})", keys).fetchall():
        con.execute("UPDATE items SET removed_at = COALESCE(removed_at, ?) WHERE source_key = ?", (now, r["key"]))
        con.execute("DELETE FROM posts WHERE source_key = ?", (r["key"],))
        con.execute("DELETE FROM sources WHERE key = ?", (r["key"],))


def source_config(row: sqlite3.Row) -> dict:
    """sources 행 → 수집기에 넘길 설정 dict (key·name·kind·priority 포함).
    user = 사용자가 정한 값(게시판 직접 지정), runtime = 수집기가 찾아 둔 값(내 소속 홈페이지·게시판)."""
    cfg = loads(row["config"], {})
    return {**cfg, "key": row["key"], "name": row["name"], "kind": row["kind"], "priority": row["priority"],
            "enabled": bool(row["enabled"]), "builtin": bool(row["builtin"]),
            "user": loads(row["user_config"], {}) or {}, "runtime": loads(row["runtime"], {}) or {}}


def set_runtime(con: sqlite3.Connection, key: str, runtime: dict) -> None:
    con.execute("UPDATE sources SET runtime = ? WHERE key = ?", (dumps(runtime), key))


def set_user_config(con: sqlite3.Connection, key: str, user: dict) -> None:
    con.execute("UPDATE sources SET user_config = ? WHERE key = ?", (dumps(user), key))


def enabled_map(con: sqlite3.Connection) -> dict[str, bool]:
    """원천별 켜짐. 목록에 없는 원천(지워진 것)은 없음 → 그 일정은 보이지 않는다."""
    return {r["key"]: bool(r["enabled"]) for r in con.execute("SELECT key, enabled FROM sources")}


def list_sources(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM sources ORDER BY builtin DESC, priority, created_at").fetchall()


def get_source(con: sqlite3.Connection, key: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM sources WHERE key = ?", (key,)).fetchone()


def record_source_run(con: sqlite3.Connection, key: str, result: str, count: Optional[int], error: Optional[str]) -> None:
    now = now_iso()
    if result == "ok":
        con.execute("UPDATE sources SET last_run_at = ?, last_ok_at = ?, last_result = 'ok', last_count = ?, "
                    "last_error = NULL WHERE key = ?", (now, now, count, key))
    else:
        con.execute("UPDATE sources SET last_run_at = ?, last_result = ?, last_error = ? WHERE key = ?",
                    (now, result, error, key))


def priority_map(con: sqlite3.Connection) -> dict[str, int]:
    return {r["key"]: r["priority"] for r in con.execute("SELECT key, priority FROM sources")}


def source_names(con: sqlite3.Connection) -> dict[str, str]:
    """화면에 보일 출처 이름. 내 소속 공지는 찾아 둔 소속 이름으로 ('내 학부 공지' → '인공지능학부 공지')."""
    out = {}
    for r in con.execute("SELECT key, name, runtime FROM sources"):
        target = (loads(r["runtime"], {}) or {}).get("target")
        out[r["key"]] = f"{target} 공지" if target else r["name"]
    return out
