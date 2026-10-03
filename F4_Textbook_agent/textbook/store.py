"""저장소 — SQLite 한 파일 (data/textbook.db). 표준 라이브러리만.

**원본 파일은 옮기지 않는다.** e클래스 수집분은 F6_Eclass_agent/data 에 그대로 두고, 이 표에는
어디에 있는 무슨 파일인지와 우리가 읽어 낸 값(쪽수·텍스트 유무·해시·상태)만 적는다.
직접 추가한 파일만 이 폴더(data/uploads)에 들어온다.

  materials  자료 한 줄 — id `mt:<해시12>` · 과목 · 종류(강의자료·게시판 첨부·과제 첨부·직접 추가) ·
             경로(root+상대경로) · 어디서 왔는지(origin_path) · 어떻게 들여놨는지(stored) ·
             쪽수 · 텍스트 유무 · 내용 해시 · 중복 표시 · 인덱싱 상태
  meta       scanned_at · updated_at · manifest_stamp(마지막으로 반영한 manifest.json) · schema

인덱싱 상태(index_state)는 AI팀 파이프라인이 붙기 전까지 전부 `pending` 이다. 다만 **붙여도 소용없는 것**은
스캔 때 미리 갈라 둔다 — `locked`(암호) · `ocr_needed`(텍스트 없음) · `unsupported`(확장자) · `duplicate`(같은 파일).
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS materials (
    id            TEXT PRIMARY KEY,
    course_id     TEXT NOT NULL,
    course        TEXT NOT NULL DEFAULT '',
    title         TEXT NOT NULL,
    root          TEXT NOT NULL,                 -- eclass | upload (실제 폴더는 config 가 정한다)
    rel_path      TEXT NOT NULL,                 -- root 기준 상대 경로 (posix)
    origin_path   TEXT NOT NULL DEFAULT '',      -- 어디서 들여왔나 — F6 기준 'data/<과목>/…' (수집분만)
    stored        TEXT NOT NULL DEFAULT '',      -- link | copy | upload | eclass(들여놓지 못함)
    detached      INTEGER NOT NULL DEFAULT 0,    -- e클래스 목록에서는 빠졌지만 보관본은 남아 있다
    source        TEXT NOT NULL,                 -- eclass | upload
    kind          TEXT NOT NULL,                 -- lecture | board | assignment | upload
    ext           TEXT NOT NULL DEFAULT '',
    activity      TEXT NOT NULL DEFAULT '',      -- e클래스 활동·게시판 이름
    post          TEXT NOT NULL DEFAULT '',      -- 게시판 글 제목 (첨부일 때)
    url           TEXT NOT NULL DEFAULT '',      -- e클래스 원문 주소
    source_key    TEXT NOT NULL DEFAULT '',      -- manifest 의 파일 키 (id 를 만든 근거)
    week          INTEGER,
    week_guess    INTEGER NOT NULL DEFAULT 1,    -- 이름에서 추정한 주차인가
    size          INTEGER NOT NULL DEFAULT 0,
    mtime         REAL,                          -- 파일 수정 시각 (바뀌면 다시 읽는다)
    pages         INTEGER,
    text_state    TEXT NOT NULL DEFAULT 'unknown',   -- text | none | unknown
    content_hash  TEXT,
    dup_of        TEXT,                          -- 같은 내용의 먼저 들어온 자료 id (F4 8절)
    meta_state    TEXT NOT NULL DEFAULT 'pending',   -- pending | done | failed (쪽수·해시 읽기)
    meta_error    TEXT NOT NULL DEFAULT '',
    index_state   TEXT NOT NULL DEFAULT 'pending',   -- pending | running | done | failed | ocr_needed | locked | unsupported | duplicate
    index_error   TEXT NOT NULL DEFAULT '',
    collected_at  TEXT,                          -- e클래스가 내려받은 시각 / 직접 추가한 시각
    added_at      TEXT NOT NULL,                 -- 이 목록에 처음 들어온 시각
    seen_at       TEXT NOT NULL,                 -- 마지막 스캔에서 확인한 시각
    missing       INTEGER NOT NULL DEFAULT 0     -- 파일이 사라졌다 (목록에는 두고 표시만)
);
CREATE INDEX IF NOT EXISTS ix_materials_course ON materials(course_id);
CREATE INDEX IF NOT EXISTS ix_materials_hash ON materials(content_hash);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# 컬럼을 더할 때는 여기에 (name, 정의)를 적는다 — 이미 있는 DB 는 열릴 때 조용히 따라온다.
_ADDED_COLUMNS = (
    ("origin_path", "TEXT NOT NULL DEFAULT ''"),
    ("stored", "TEXT NOT NULL DEFAULT ''"),
    ("detached", "INTEGER NOT NULL DEFAULT 0"),
)

_initialized: set[str] = set()


def _migrate(con: sqlite3.Connection) -> None:
    have = {r["name"] for r in con.execute("PRAGMA table_info(materials)")}
    for name, ddl in _ADDED_COLUMNS:
        if name not in have:
            con.execute(f"ALTER TABLE materials ADD COLUMN {name} {ddl}")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    C.ensure_dirs()
    con = sqlite3.connect(C.DB_PATH, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        key = str(C.DB_PATH)
        if key not in _initialized:
            con.executescript(SCHEMA)
            _migrate(con)
            con.commit()
            _initialized.add(key)
        yield con
        con.commit()
    finally:
        con.close()


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_meta(con: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(con: sqlite3.Connection, **kw: Any) -> None:
    for k, v in kw.items():
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, None if v is None else str(v)))


def touch(con: sqlite3.Connection) -> str:
    """자료 목록이 바뀌었다 — 화면은 updated_at 이 달라졌을 때만 다시 부른다."""
    stamp = now()
    set_meta(con, updated_at=stamp)
    return stamp


def updated_at(con: sqlite3.Connection) -> Optional[str]:
    return get_meta(con, "updated_at")


def all_rows(con: sqlite3.Connection, course_id: Optional[str] = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM materials"
    args: tuple = ()
    if course_id:
        sql += " WHERE course_id = ?"
        args = (course_id,)
    sql += " ORDER BY course_id, week IS NULL, week, title"
    return list(con.execute(sql, args))


def row(con: sqlite3.Connection, material_id: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM materials WHERE id = ?", (material_id,)).fetchone()


def upsert(con: sqlite3.Connection, m: dict) -> bool:
    """자료 한 줄을 넣거나 갱신한다. 새로 생겼으면 True."""
    cur = con.execute("SELECT id FROM materials WHERE id = ?", (m["id"],)).fetchone()
    cols = [k for k in m if k != "id"]
    if cur is None:
        con.execute(f"INSERT INTO materials (id, {', '.join(cols)}) "
                    f"VALUES (:id, {', '.join(':' + c for c in cols)})", m)
        return True
    con.execute(f"UPDATE materials SET {', '.join(f'{c} = :{c}' for c in cols)} WHERE id = :id", m)
    return False


def delete(con: sqlite3.Connection, material_id: str) -> bool:
    return con.execute("DELETE FROM materials WHERE id = ?", (material_id,)).rowcount > 0


def ids(con: sqlite3.Connection, source: Optional[str] = None) -> set[str]:
    sql = "SELECT id FROM materials" + (" WHERE source = ?" if source else "")
    return {r["id"] for r in con.execute(sql, (source,) if source else ())}
