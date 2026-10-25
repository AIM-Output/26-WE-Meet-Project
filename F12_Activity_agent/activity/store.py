"""저장소 — SQLite 한 파일 (data/activity.db). 표준 라이브러리만. F11 scholarship.db 와 같은 모양에 대외활동 칸을 더했다.

관심사 등급(시스템)과 진행 상태(사용자)는 **다른 표**다 (F11 5절 '두 축 분리'를 그대로).
  notices     수집한 공지 + 추출한 정보(info JSON: 분류·주관·대상·장소·기간·혜택·서류·방법). 수집기(자식 프로세스)가 쓴다
  user_state  사용자가 뒤집은 등급 · 진행 상태(담음 → 초안 대기 → 제출 예정 → 지원함 → 선정/탈락 · 관심 없음) · 캘린더·할 일 연결 · 알림 기록
  drafts      신청서 초안 (사용자가 고친 본문 그대로)
  sources     원천마다 켜고 끈 것(사용자, F11 과 따로) · 마지막 수집 결과 · 찾아 둔 학과 공지 게시판
  llm_grades  LLM 관련도 판단 캐시 — (공지, 관심사 해시) 마다 한 번 (F12-R21, 관심사를 바꾸면 다시)
  meta        updated_at · baseline_at(첫 수집 = 알림 기준선) · materials(초안 재료) · alert_day(하루 알림 수) · llm_day
등급은 저장하지 않는다 — 부를 때마다 지금 관심사로 계산한다(F12-R15: 관심사를 바꾸면 기존 공지를 다시 판정).
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_name   TEXT NOT NULL,
    unit_key      TEXT,
    title         TEXT NOT NULL,
    url           TEXT NOT NULL,
    posted_at     TEXT,
    writer        TEXT,
    category      TEXT,
    body          TEXT NOT NULL DEFAULT '',
    attach_text   TEXT NOT NULL DEFAULT '',
    attachments   TEXT NOT NULL DEFAULT '[]',
    image_only    INTEGER NOT NULL DEFAULT 0,
    content_hash  TEXT NOT NULL DEFAULT '',
    title_key     TEXT NOT NULL DEFAULT '',
    dup_of        TEXT,
    info          TEXT,
    extract_ver   INTEGER NOT NULL DEFAULT 0,
    first_seen    TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    changed_at    TEXT
);
CREATE INDEX IF NOT EXISTS notices_title_key ON notices(title_key);
CREATE TABLE IF NOT EXISTS user_state (
    notice_id       TEXT PRIMARY KEY,
    override        TEXT,
    override_at     TEXT,
    progress        TEXT,
    progress_at     TEXT,
    saved_at        TEXT,
    applied_at      TEXT,
    result_at       TEXT,
    note            TEXT,
    calendar_id     TEXT,
    todos           TEXT NOT NULL DEFAULT '{}',
    alerted_at      TEXT,
    deadline_alerts TEXT NOT NULL DEFAULT '[]',
    asked_applied   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS drafts (
    notice_id    TEXT PRIMARY KEY,
    body         TEXT NOT NULL,
    generated_by TEXT NOT NULL DEFAULT 'template',
    borrowed     TEXT NOT NULL DEFAULT '[]',
    source_hash  TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
    key           TEXT PRIMARY KEY,
    enabled       INTEGER,
    last_run_at   TEXT,
    last_ok_at    TEXT,
    last_count    INTEGER,
    last_new      INTEGER,
    last_error    TEXT,
    discovered    TEXT,
    discovered_at TEXT
);
CREATE TABLE IF NOT EXISTS llm_grades (
    notice_id  TEXT NOT NULL,
    ihash      TEXT NOT NULL,
    grade      TEXT NOT NULL,
    reason     TEXT,
    at         TEXT NOT NULL,
    PRIMARY KEY (notice_id, ihash)
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


def touch(con: sqlite3.Connection) -> None:
    """화면이 다시 부르게 updatedAt 을 올린다 (/api/status 의 activity.updatedAt)."""
    set_meta(con, "updated_at", now_iso())


# ── 공지 ────────────────────────────────────────────────────

def notice_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM notices ORDER BY COALESCE(posted_at, first_seen) DESC").fetchall()


def notice(con: sqlite3.Connection, nid: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM notices WHERE id = ?", (nid,)).fetchone()


def upsert_notice(con: sqlite3.Connection, n: dict) -> str:
    """수집기가 부른다. 반환: new / changed / same. 바뀐 공지는 changed_at 을 남겨 초안에 '원문이 바뀌었습니다'를 띄운다."""
    old = notice(con, n["id"])
    now = now_iso()
    cols = ("source", "source_name", "unit_key", "title", "url", "posted_at", "writer", "category", "body", "attach_text",
            "attachments", "image_only", "content_hash", "title_key", "dup_of", "info", "extract_ver")
    vals = {k: n.get(k) for k in cols}
    vals["attachments"] = dumps(n.get("attachments") or [])
    vals["info"] = dumps(n["info"]) if n.get("info") is not None else None
    vals["image_only"] = int(bool(n.get("image_only")))
    if old is None:
        con.execute(f"INSERT INTO notices(id, {', '.join(cols)}, first_seen, fetched_at) "
                    f"VALUES (?, {', '.join('?' * len(cols))}, ?, ?)",
                    (n["id"], *[vals[k] for k in cols], now, now))
        return "new"
    changed = old["content_hash"] != vals["content_hash"]
    con.execute(f"UPDATE notices SET {', '.join(f'{k} = ?' for k in cols)}, fetched_at = ?"
                + (", changed_at = ?" if changed else "") + " WHERE id = ?",
                (*[vals[k] for k in cols], now, *([now] if changed else []), n["id"]))
    return "changed" if changed else "same"


def set_info(con: sqlite3.Connection, nid: str, info: dict, ver: int) -> None:
    con.execute("UPDATE notices SET info = ?, extract_ver = ? WHERE id = ?", (dumps(info), ver, nid))


def find_dup(con: sqlite3.Connection, title_key: str, nid: str) -> Optional[str]:
    """같은 제목 키의 다른 공지(먼저 들어온 것) — 여러 게시판에 같은 글이 올라오면 하나로 묶는다 (F13-R08)."""
    if len(title_key) < 8:
        return None
    r = con.execute("SELECT id FROM notices WHERE title_key = ? AND id != ? AND dup_of IS NULL "
                    "ORDER BY first_seen LIMIT 1", (title_key, nid)).fetchone()
    return r["id"] if r else None


# ── 사용자 상태 ─────────────────────────────────────────────

def states(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["notice_id"]: r for r in con.execute("SELECT * FROM user_state")}


def state(con: sqlite3.Connection, nid: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM user_state WHERE notice_id = ?", (nid,)).fetchone()


def put_state(con: sqlite3.Connection, nid: str, **fields) -> None:
    if not fields:
        return
    con.execute("INSERT INTO user_state(notice_id) VALUES (?) ON CONFLICT(notice_id) DO NOTHING", (nid,))
    con.execute(f"UPDATE user_state SET {', '.join(f'{k} = ?' for k in fields)} WHERE notice_id = ?",
                (*fields.values(), nid))


# ── 초안 ────────────────────────────────────────────────────

def draft(con: sqlite3.Connection, nid: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM drafts WHERE notice_id = ?", (nid,)).fetchone()


def drafts(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM drafts ORDER BY updated_at DESC").fetchall()


def save_draft(con: sqlite3.Connection, nid: str, body: str, *, generated_by: Optional[str] = None,
               borrowed: Optional[list] = None, source_hash: Optional[str] = None) -> None:
    now = now_iso()
    old = draft(con, nid)
    if old is None:
        con.execute("INSERT INTO drafts(notice_id, body, generated_by, borrowed, source_hash, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (nid, body, generated_by or "template", dumps(borrowed or []), source_hash or "", now, now))
        return
    con.execute("UPDATE drafts SET body = ?, generated_by = COALESCE(?, generated_by), borrowed = COALESCE(?, borrowed), "
                "source_hash = COALESCE(?, source_hash), updated_at = ? WHERE notice_id = ?",
                (body, generated_by, dumps(borrowed) if borrowed is not None else None, source_hash, now, nid))


def delete_draft(con: sqlite3.Connection, nid: str) -> None:
    con.execute("DELETE FROM drafts WHERE notice_id = ?", (nid,))


# ── 원천 ────────────────────────────────────────────────────

def source_rows(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["key"]: r for r in con.execute("SELECT * FROM sources")}


def put_source(con: sqlite3.Connection, key: str, **fields) -> None:
    con.execute("INSERT INTO sources(key) VALUES (?) ON CONFLICT(key) DO NOTHING", (key,))
    if fields:
        con.execute(f"UPDATE sources SET {', '.join(f'{k} = ?' for k in fields)} WHERE key = ?", (*fields.values(), key))


def overrides(con: sqlite3.Connection) -> dict[str, bool]:
    return {r["key"]: bool(r["enabled"]) for r in con.execute("SELECT key, enabled FROM sources WHERE enabled IS NOT NULL")}


# ── LLM 관련도 판단 캐시 ────────────────────────────────────

def llm_grades(con: sqlite3.Connection, ihash: str) -> dict[str, dict]:
    return {r["notice_id"]: {"grade": r["grade"], "reason": r["reason"]}
            for r in con.execute("SELECT * FROM llm_grades WHERE ihash = ?", (ihash,))}


def put_llm_grade(con: sqlite3.Connection, nid: str, ihash: str, grade: str, reason: Optional[str]) -> None:
    con.execute("INSERT INTO llm_grades(notice_id, ihash, grade, reason, at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(notice_id, ihash) DO UPDATE SET grade = excluded.grade, reason = excluded.reason, at = excluded.at",
                (nid, ihash, grade, (reason or "")[:200] or None, now_iso()))
