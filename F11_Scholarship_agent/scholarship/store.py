"""저장소 — SQLite 한 파일 (data/scholarship.db). 표준 라이브러리만.

판정(시스템)과 진행 상태(사용자)는 **다른 표**다 (F11 5절 '두 축 분리').
  notices     수집한 공지·상시 장학 + 추출한 요건(req JSON). 수집기(자식 프로세스)가 쓴다
  user_state  사용자가 뒤집은 판정 · 진행 상태(신청 예정 → 신청함 → 선정/탈락 · 관심 없음) · 캘린더·할 일 연결 · 알림 기록
  sources     원천마다 켜고 끈 것(사용자) · 마지막 수집 결과 · 찾아 둔 학과 게시판
  meta        updated_at · baseline_at(첫 수집 = 알림 기준선) · catalog_at · title_key_ver(같은 글 묶음을 지은 제목 키의 판)
판정 결과는 저장하지 않는다 — 부를 때마다 지금 프로필로 계산한다(재판정 규칙 F11 5절: 프로필이 바뀌면 전체 재판정).
신청서 초안(drafts 표)·초안 재료(meta materials)는 2026-11-19 폐기 — 예전 DB 에 남은 것은 _migrate 가 지운다.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable, Iterator, Optional

from . import config as C
from .textutil import title_key

REFRESH_COMMIT_SEC = 0.3        # 공지를 다시 뽑는 동안 이만큼마다 저장한다 — 쓰기 잠금을 오래 잡지 않게 (refresh_stale)

SCHEMA = """
CREATE TABLE IF NOT EXISTS notices (
    id            TEXT PRIMARY KEY,
    source        TEXT NOT NULL,
    source_name   TEXT NOT NULL,
    unit_key      TEXT,
    kind          TEXT NOT NULL DEFAULT 'notice',
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
    is_result     INTEGER NOT NULL DEFAULT 0,
    title_key     TEXT NOT NULL DEFAULT '',
    dup_of        TEXT,
    req           TEXT,
    extract_ver   INTEGER NOT NULL DEFAULT 0,
    reader_ver    INTEGER NOT NULL DEFAULT 0,
    first_seen    TEXT NOT NULL,
    fetched_at    TEXT NOT NULL,
    changed_at    TEXT
);
CREATE INDEX IF NOT EXISTS notices_title_key ON notices(title_key);
CREATE TABLE IF NOT EXISTS user_state (
    notice_id       TEXT PRIMARY KEY,
    override        TEXT,
    override_reason TEXT,
    override_at     TEXT,
    progress        TEXT,
    progress_at     TEXT,
    applied_at      TEXT,
    result_at       TEXT,
    amount          TEXT,
    note            TEXT,
    calendar_id     TEXT,
    todos           TEXT NOT NULL DEFAULT '{}',
    alerted_at      TEXT,
    deadline_alerts TEXT NOT NULL DEFAULT '[]',
    asked_applied   INTEGER NOT NULL DEFAULT 0
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


def _migrate(con: sqlite3.Connection) -> None:
    """예전 DB 를 지금 모양으로 — 앱을 새 판으로 처음 열 때(프로세스마다 첫 연결) 한 번 돈다. 여러 번 돌아도 같다.
      - reader_ver 칸(첨부·이미지를 읽은 방법의 판, 2026-10-25 HWP·OCR)을 붙인다.
      - 신청서 초안 폐기(2026-11-19): 초안(drafts 표)과 초안 재료(meta materials — 이름·학번·연락처·진로·형편)를 지운다.
        진행 상태 '초안 대기'(draft)는 '신청 예정'(approved)으로 — 초안을 만든 글은 신청하려던 글이고 마감 D-3·D-1 알림도 이어서 받는다.
      - 제목 키의 판(config.TITLE_KEY_VERSION)이 바뀌었으면 같은 글 묶음을 한 번 다시 짓는다 (2026-11-19)."""
    cols = {r[1] for r in con.execute("PRAGMA table_info(notices)")}
    if "reader_ver" not in cols:
        con.execute("ALTER TABLE notices ADD COLUMN reader_ver INTEGER NOT NULL DEFAULT 0")
    drop_drafts(con)
    con.execute("UPDATE user_state SET progress = 'approved' WHERE progress = 'draft'")
    if get_meta(con, "title_key_ver") != str(C.TITLE_KEY_VERSION):
        regroup(con)
        set_meta(con, "title_key_ver", str(C.TITLE_KEY_VERSION))


def drop_drafts(con: sqlite3.Connection) -> bool:
    """폐기한 신청서 초안(drafts 표)·초안 재료(meta materials)를 지운다 — 지운 자리는 0 으로 덮어(secure_delete) 이름·학번·연락처가
    DB 파일의 빈 페이지에 남지 않게 한다. F12(activity.store)도 같은 모양이라 이 함수를 쓴다. 지운 것이 있으면 True."""
    had = bool(con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'drafts'").fetchone()
               or get_meta(con, "materials") is not None)
    if had:
        con.execute("PRAGMA secure_delete = ON")
        con.execute("DROP TABLE IF EXISTS drafts")
        set_meta(con, "materials", None)
        con.execute("PRAGMA secure_delete = OFF")
    return had


def refresh_stale(con: sqlite3.Connection, stale_sql: str, args: tuple,
                  rebuild: Callable[[sqlite3.Connection, sqlite3.Row], Any], lock: threading.Lock) -> int:
    """규칙 판(EXTRACT_VERSION)이 바뀐 뒤 처음 목록을 부를 때 — 판이 낮은 공지(stale_sql)를 rebuild 로 다시 뽑아 저장한다.
    다시 뽑은 수를 돌려준다. F12(activity)도 같은 모양의 표에 이 함수를 쓴다.
      - 한 번에 한 요청만 한다(lock). 같이 들어온 요청은 끝나기를 기다렸다가 저장된 결과를 쓴다 — 같은 일을 두 번 하지 않는다.
      - REFRESH_COMMIT_SEC 마다 저장해 쓰기 잠금을 오래 잡지 않는다.
      - 부른 쪽이 이미 쓰는 중(트랜잭션)이면 하지 않는다 — 그 트랜잭션을 중간에 저장하거나 서로 기다리며 멈추지 않게.
        그때는 공지마다(service._info·_req) 다시 뽑는다.
    예전에는 목록 요청이 공지를 하나씩 다시 뽑으며 끝까지 쓰기 잠금을 잡았다 — 대외활동 600건에 15초, 같이 들어온
    상태 확인(/api/status)이 'database is locked' 로 실패했다(2026-11-19 실측, 2026-11-23 고침)."""
    if con.in_transaction or not con.execute(f"{stale_sql} LIMIT 1", args).fetchall():
        return 0
    with lock:
        rows = con.execute(stale_sql, args).fetchall()      # 기다리는 사이 다른 요청이 다 뽑았으면 빈 목록
        last = time.monotonic()
        for i, row in enumerate(rows, 1):
            rebuild(con, row)
            if time.monotonic() - last >= REFRESH_COMMIT_SEC or i == len(rows):
                con.commit()
                last = time.monotonic()
        return len(rows)


def regroup(con: sqlite3.Connection, key_fn: Callable[[str], str] = title_key) -> dict:
    """저장된 공지의 제목 키를 key_fn 으로 다시 매기고 같은 글 묶음(dup_of)을 처음부터 다시 짓는다 — find_dup 과 같은 규칙
    (키 8자 이상, 먼저 들어온 글이 원글). 단 진행 상태가 있는 글(관심 없음 제외)은 묶음 안에 숨기지 않는다.
    묶음에서 풀려 새로 보이는 글은 알림을 보낸 것으로 친다(alerted_at) — 오래전에 모은 글이 새 공지 알림으로 쏟아지지 않게.
    F12(activity.store)도 같은 모양의 표에 이 함수를 쓴다."""
    kept = {r[0] for r in con.execute("SELECT notice_id FROM user_state WHERE progress IS NOT NULL AND progress != 'skipped'")}
    rows = sorted(con.execute("SELECT id, title, dup_of FROM notices ORDER BY first_seen, id").fetchall(),
                  key=lambda r: r["id"] not in kept)            # 안정 정렬 — 손댄 글이 먼저 원글이 된다
    first: dict[str, str] = {}
    freed, stamp = 0, now_iso()
    for r in rows:
        tk = key_fn(r["title"])
        dup = first.get(tk) if len(tk) >= 8 and r["id"] not in kept else None
        if dup is None:
            first.setdefault(tk, r["id"])
            if r["dup_of"]:
                freed += 1
                con.execute("INSERT INTO user_state(notice_id, alerted_at) VALUES (?, ?) ON CONFLICT(notice_id) "
                            "DO UPDATE SET alerted_at = COALESCE(alerted_at, excluded.alerted_at)", (r["id"], stamp))
        con.execute("UPDATE notices SET title_key = ?, dup_of = ? WHERE id = ?", (tk, dup, r["id"]))
    return {"rows": len(rows), "freed": freed}


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


def touch(con: sqlite3.Connection) -> None:
    """화면이 다시 부르게 updatedAt 을 올린다 (/api/status 의 scholarship.updatedAt)."""
    set_meta(con, "updated_at", now_iso())


# ── 공지 ────────────────────────────────────────────────────

def notice_rows(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM notices ORDER BY COALESCE(posted_at, first_seen) DESC").fetchall()


def notice(con: sqlite3.Connection, nid: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM notices WHERE id = ?", (nid,)).fetchone()


def upsert_notice(con: sqlite3.Connection, n: dict) -> str:
    """수집기가 부른다. 반환: new / changed / same. 바뀐 공지는 changed_at 을 남긴다(상세의 changedAt)."""
    old = notice(con, n["id"])
    now = now_iso()
    cols = ("source", "source_name", "unit_key", "kind", "title", "url", "posted_at", "writer", "category", "body",
            "attach_text", "attachments", "image_only", "content_hash", "is_result", "title_key", "dup_of", "req",
            "extract_ver", "reader_ver")
    vals = {k: n.get(k) for k in cols}
    vals["attachments"] = dumps(n.get("attachments") or [])
    vals["req"] = dumps(n["req"]) if n.get("req") is not None else None
    vals["image_only"] = int(bool(n.get("image_only")))
    vals["reader_ver"] = int(n.get("reader_ver") or 0)
    vals["is_result"] = int(bool(n.get("is_result")))
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


def set_req(con: sqlite3.Connection, nid: str, req: dict, ver: int) -> None:
    con.execute("UPDATE notices SET req = ?, extract_ver = ? WHERE id = ?", (dumps(req), ver, nid))


def find_dup(con: sqlite3.Connection, title_key: str, nid: str) -> Optional[str]:
    """같은 제목 키의 다른 공지(먼저 들어온 것) — 여러 게시판에 같은 글이 올라온 경우 하나로 묶는다 (F11 9절)."""
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


# ── 원천 ────────────────────────────────────────────────────

def source_rows(con: sqlite3.Connection) -> dict[str, sqlite3.Row]:
    return {r["key"]: r for r in con.execute("SELECT * FROM sources")}


def put_source(con: sqlite3.Connection, key: str, **fields) -> None:
    con.execute("INSERT INTO sources(key) VALUES (?) ON CONFLICT(key) DO NOTHING", (key,))
    if fields:
        con.execute(f"UPDATE sources SET {', '.join(f'{k} = ?' for k in fields)} WHERE key = ?", (*fields.values(), key))


def overrides(con: sqlite3.Connection) -> dict[str, bool]:
    return {r["key"]: bool(r["enabled"]) for r in con.execute("SELECT key, enabled FROM sources WHERE enabled IS NOT NULL")}
