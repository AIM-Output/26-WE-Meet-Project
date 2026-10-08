"""저장소 — SQLite 한 파일 (data/exams.db). 표준 라이브러리만.

  exams      시험 한 줄 — id `ex:<과목>:<해시8>` · 유형 · 일시·장소 · 범위 · 원천(공지/수기) ·
             근거 원문·신뢰도 · 승인 상태 · 사용자가 손댔는지(edited) · 지웠는지(removed_at)
  plans      학습 계획 — 어떤 시험의 계획인가 · 분량·환산 기준 · 복습일·제외일·상한 · 상태
             (id 는 정수 rowid, 화면에는 `pl:<n>` 으로 나간다 — 학습 블록 id 가 `st:<n>:<날짜>` 로 짧아진다)
  plan_days  날짜별 분량 — (계획, 날짜)가 열쇠다. 쪽·분 · study|review · 완료 · 사용자가 옮겼는지
  course_settings  과목별 시험 유무 — 중간·기말 (기본: 둘 다 본다. 시험이 없는 과목은 사용자가 끈다)
  meta       updated_at · notice_stamp(마지막으로 반영한 manifest.json) · defaults_stamp(임의 일정 계산) · schema

**초안(draft)은 저장하지 않는다.** 미리보기는 순수 계산(plan.compute)이고, `등록하기`를 눌렀을 때만 여기
`active` 로 들어온다 (F5 D3 — 일정이 통째로 밀려 들어오는 것을 막는다).

공지에서 추출한 시험을 사용자가 고치면 `edited=1` 이 되어 **재수집이 덮어쓰지 않는다** (F5-R03).
지운 것은 줄을 없애지 않고 `removed_at` 을 적는다 — 없애면 다음 수집 때 되살아난다.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator, Optional

from . import config as C

SCHEMA = """
CREATE TABLE IF NOT EXISTS exams (
    id            TEXT PRIMARY KEY,
    course_id     TEXT NOT NULL,
    course        TEXT NOT NULL DEFAULT '',        -- e클래스 과목 전체 이름 (목록을 못 받았을 때의 대비)
    type          TEXT NOT NULL,                   -- midterm | final | quiz | presentation | etc
    title         TEXT NOT NULL DEFAULT '',        -- 화면에 쓰는 이름 ('중간고사' · '기획서 발표')
    date          TEXT NOT NULL,                   -- YYYY-MM-DD
    time          TEXT NOT NULL DEFAULT '',        -- HH:MM · 빈 값이면 '시각 미정' (F5 8절)
    end_time      TEXT NOT NULL DEFAULT '',
    place         TEXT NOT NULL DEFAULT '',
    scope_weeks   TEXT NOT NULL DEFAULT '[]',      -- JSON int[]  — 주차로 지정한 범위 (F5-R06)
    scope_ids     TEXT NOT NULL DEFAULT '[]',      -- JSON str[]  — 자료 id 로 지정한 범위
    scope_note    TEXT NOT NULL DEFAULT '',        -- 공지 원문의 범위 문구 ('10월 15일까지 강의한 내용 전반')
    source        TEXT NOT NULL,                   -- notice | manual | auto(평가 기간·수업 요일로 임의로 잡음)
    evidence      TEXT NOT NULL DEFAULT '[]',      -- JSON [{quote, url}] (F5-R02 · 9절 '신뢰')
    confidence    REAL NOT NULL DEFAULT 1,
    status        TEXT NOT NULL DEFAULT 'confirmed',   -- confirmed | review
    notice_key    TEXT NOT NULL DEFAULT '',        -- manifest 의 글 키 — 어느 글에서 왔나
    notice_url    TEXT NOT NULL DEFAULT '',
    posted_at     TEXT NOT NULL DEFAULT '',        -- 공지 작성일
    edited        INTEGER NOT NULL DEFAULT 0,      -- 사용자가 손댔다 → 재수집이 덮어쓰지 않는다 (F5-R03)
    changed       TEXT NOT NULL DEFAULT '',        -- JSON {field, from, to, at} — 공지 재추출로 바뀐 것 (F5 8절)
    removed_at    TEXT,                            -- 사용자가 지웠다 (다시 살아나지 않게 줄은 남긴다)
    note          TEXT NOT NULL DEFAULT '',        -- 임의 일정이면 어떻게 잡았는지 ('중간 수업평가 기간 안의 첫 수업 · 화 15:00')
    time_auto     INTEGER NOT NULL DEFAULT 0,      -- 공지에 시각이 없어 그 과목 수업 시간으로 채웠다
    added_at      TEXT NOT NULL,
    seen_at       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_exams_date ON exams(date);
CREATE TABLE IF NOT EXISTS course_settings (
    course_id   TEXT PRIMARY KEY,                  -- e클래스 과목 id
    midterm     INTEGER NOT NULL DEFAULT 1,        -- 중간고사를 보는가 (기본: 본다)
    final       INTEGER NOT NULL DEFAULT 1,        -- 기말고사를 보는가
    updated_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    exam_id       TEXT NOT NULL,
    unit          TEXT NOT NULL DEFAULT 'pages',   -- pages | minutes (자료가 없으면 사용자가 시간으로, F5-R11)
    total_pages   INTEGER,
    total_minutes INTEGER,                         -- unit='minutes' 일 때의 총 시간
    page_minutes  REAL NOT NULL DEFAULT 2.5,
    difficulty    TEXT NOT NULL DEFAULT 'normal',
    review_days   INTEGER NOT NULL DEFAULT 1,
    excluded      TEXT NOT NULL DEFAULT '[]',      -- JSON [YYYY-MM-DD] (F5-R22)
    cap_minutes   INTEGER NOT NULL DEFAULT 240,    -- 하루 학습 시간 상한 (F5-R14)
    include_quiz  INTEGER NOT NULL DEFAULT 0,      -- 예상 문제 풀이 포함 (F5-R13)
    quiz_count    INTEGER NOT NULL DEFAULT 0,
    scope_weeks   TEXT NOT NULL DEFAULT '[]',      -- 계획을 만들 때 쓴 범위 (시험 범위가 나중에 바뀌면 비교한다)
    scope_ids     TEXT NOT NULL DEFAULT '[]',
    source_pages  INTEGER,                         -- 만들 때 F4 자료에서 자동으로 채운 쪽수 (변화 감지용, F5 8절)
    state         TEXT NOT NULL DEFAULT 'active',  -- active | done | canceled
    created_at    TEXT NOT NULL,
    rebalanced_at TEXT,
    closed_at     TEXT,
    FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_plans_exam ON plans(exam_id, state);
CREATE TABLE IF NOT EXISTS plan_days (
    plan_id  INTEGER NOT NULL,
    date     TEXT NOT NULL,
    pages    INTEGER NOT NULL DEFAULT 0,
    minutes  INTEGER NOT NULL DEFAULT 0,
    kind     TEXT NOT NULL DEFAULT 'study',        -- study | review (마무리 복습일)
    quiz     INTEGER NOT NULL DEFAULT 0,           -- 그 날 풀 예상 문제 수
    done     INTEGER NOT NULL DEFAULT 0,
    done_at  TEXT,
    moved    INTEGER NOT NULL DEFAULT 0,           -- 사용자가 옮긴 날 — 재조정이 날짜를 건드리지 않는다
    PRIMARY KEY (plan_id, date),
    FOREIGN KEY (plan_id) REFERENCES plans(id) ON DELETE CASCADE
);
-- 서비스 밖에서 공부한 강의자료 (2026-10-06) — F4 자료 id 단위, 과목에 한 번. 체크하면 계획의 남은 분량에서 빠진다
CREATE TABLE IF NOT EXISTS material_done (
    material_id TEXT PRIMARY KEY,                  -- F4 materials.id
    course_id   TEXT NOT NULL,
    done_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

# 컬럼을 더할 때는 여기에 (표, name, 정의)를 적는다 — 이미 있는 DB 는 열릴 때 조용히 따라온다.
_ADDED_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("exams", "note", "TEXT NOT NULL DEFAULT ''"),          # 2026-10-01 — 임의 일정(source='auto')
    ("exams", "time_auto", "INTEGER NOT NULL DEFAULT 0"),   # 2026-10-01 — 시각 미정 → 수업 시간
    ("plans", "day_minutes", "TEXT NOT NULL DEFAULT '{}'"), # 2026-10-06 — 학습일마다 직접 정한 공부 시간 {날짜: 분}
    ("exams", "ready_at", "TEXT"),                          # 2026-10-06 — 발표 '준비 완료'를 누른 시각 (없으면 아직)
)

_initialized: set[str] = set()


def _migrate(con: sqlite3.Connection) -> None:
    for table, name, ddl in _ADDED_COLUMNS:
        have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
        if name not in have:
            con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


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


# ---------------------------------------------------------------- meta

def get_meta(con: sqlite3.Connection, key: str, default: Optional[str] = None) -> Optional[str]:
    row = con.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(con: sqlite3.Connection, **kw: Any) -> None:
    for k, v in kw.items():
        con.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (k, None if v is None else str(v)))


def touch(con: sqlite3.Connection) -> str:
    """시험·계획이 바뀌었다 — 화면은 updated_at 이 달라졌을 때만 다시 부른다."""
    stamp = now()
    set_meta(con, updated_at=stamp)
    return stamp


def updated_at(con: sqlite3.Connection) -> Optional[str]:
    return get_meta(con, "updated_at")


def jdump(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False)


def jload(raw: Any, default: Any) -> Any:
    try:
        v = json.loads(raw or "")
    except (TypeError, ValueError):
        return default
    return v if isinstance(v, type(default)) else default


# ---------------------------------------------------------------- 시험

def exam_rows(con: sqlite3.Connection, include_removed: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM exams"
    if not include_removed:
        sql += " WHERE removed_at IS NULL"
    return list(con.execute(sql + " ORDER BY date, time, course_id"))


def exam(con: sqlite3.Connection, exam_id: str, include_removed: bool = False) -> Optional[sqlite3.Row]:
    row = con.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
    if row is not None and row["removed_at"] and not include_removed:
        return None
    return row


def upsert_exam(con: sqlite3.Connection, e: dict) -> bool:
    """시험 한 줄을 넣거나 갱신한다. 새로 생겼으면 True."""
    cur = con.execute("SELECT id FROM exams WHERE id = ?", (e["id"],)).fetchone()
    cols = [k for k in e if k != "id"]
    if cur is None:
        con.execute(f"INSERT INTO exams (id, {', '.join(cols)}) "
                    f"VALUES (:id, {', '.join(':' + c for c in cols)})", e)
        return True
    con.execute(f"UPDATE exams SET {', '.join(f'{c} = :{c}' for c in cols)} WHERE id = :id", e)
    return False


def update_exam(con: sqlite3.Connection, exam_id: str, fields: dict) -> None:
    if not fields:
        return
    fields = {**fields, "id": exam_id}
    cols = [k for k in fields if k != "id"]
    con.execute(f"UPDATE exams SET {', '.join(f'{c} = :{c}' for c in cols)} WHERE id = :id", fields)


def delete_exam(con: sqlite3.Connection, exam_id: str, hard: bool) -> None:
    """수기 시험은 줄째 지우고, 공지 추출분은 removed_at 만 적는다 (다시 살아나지 않게)."""
    if hard:
        con.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
    else:
        con.execute("UPDATE exams SET removed_at = ?, seen_at = ? WHERE id = ?", (now(), now(), exam_id))


def hard_delete_exam(con: sqlite3.Connection, exam_id: str) -> None:
    """임의 일정은 사용자 데이터가 아니다 — 줄째 지운다(계획은 CASCADE 로 함께)."""
    con.execute("DELETE FROM exams WHERE id = ?", (exam_id,))


# ---------------------------------------------------------------- 과목별 시험 유무

def course_setting(con: sqlite3.Connection, course_id: str) -> dict:
    row = con.execute("SELECT * FROM course_settings WHERE course_id = ?", (course_id,)).fetchone()
    if row is None:
        return {"midterm": True, "final": True, "updatedAt": None}
    return {"midterm": bool(row["midterm"]), "final": bool(row["final"]), "updatedAt": row["updated_at"]}


def course_settings(con: sqlite3.Connection) -> dict[str, dict]:
    return {r["course_id"]: {"midterm": bool(r["midterm"]), "final": bool(r["final"]), "updatedAt": r["updated_at"]}
            for r in con.execute("SELECT * FROM course_settings")}


def set_course_setting(con: sqlite3.Connection, course_id: str, **kw: bool) -> dict:
    cur = course_setting(con, course_id)
    nxt = {"midterm": kw.get("midterm", cur["midterm"]), "final": kw.get("final", cur["final"])}
    con.execute("INSERT INTO course_settings (course_id, midterm, final, updated_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(course_id) DO UPDATE SET midterm = excluded.midterm, final = excluded.final, "
                "updated_at = excluded.updated_at",
                (course_id, int(nxt["midterm"]), int(nxt["final"]), now()))
    return course_setting(con, course_id)


# ---------------------------------------------------------------- 계획

def plan_rows(con: sqlite3.Connection, exam_id: Optional[str] = None,
              state: Optional[str] = None) -> list[sqlite3.Row]:
    sql, args = "SELECT * FROM plans", []
    where = []
    if exam_id:
        where.append("exam_id = ?")
        args.append(exam_id)
    if state:
        where.append("state = ?")
        args.append(state)
    if where:
        sql += " WHERE " + " AND ".join(where)
    return list(con.execute(sql + " ORDER BY id DESC", args))


def plan(con: sqlite3.Connection, plan_id: int) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()


def active_plan(con: sqlite3.Connection, exam_id: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM plans WHERE exam_id = ? AND state = 'active' ORDER BY id DESC",
                       (exam_id,)).fetchone()


def insert_plan(con: sqlite3.Connection, p: dict) -> int:
    cols = list(p)
    cur = con.execute(f"INSERT INTO plans ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})", p)
    return int(cur.lastrowid)


def update_plan(con: sqlite3.Connection, plan_id: int, fields: dict) -> None:
    if not fields:
        return
    fields = {**fields, "id": plan_id}
    cols = [k for k in fields if k != "id"]
    con.execute(f"UPDATE plans SET {', '.join(f'{c} = :{c}' for c in cols)} WHERE id = :id", fields)


def days(con: sqlite3.Connection, plan_id: int) -> list[sqlite3.Row]:
    return list(con.execute("SELECT * FROM plan_days WHERE plan_id = ? ORDER BY date", (plan_id,)))


def day(con: sqlite3.Connection, plan_id: int, date: str) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM plan_days WHERE plan_id = ? AND date = ?", (plan_id, date)).fetchone()


def put_days(con: sqlite3.Connection, plan_id: int, rows: list[dict]) -> None:
    for d in rows:
        con.execute(
            "INSERT INTO plan_days (plan_id, date, pages, minutes, kind, quiz, done, done_at, moved) "
            "VALUES (:plan_id, :date, :pages, :minutes, :kind, :quiz, :done, :done_at, :moved) "
            "ON CONFLICT(plan_id, date) DO UPDATE SET pages = excluded.pages, minutes = excluded.minutes, "
            "kind = excluded.kind, quiz = excluded.quiz",
            {"plan_id": plan_id, "done": 0, "done_at": None, "moved": 0, "quiz": 0, **d})


def update_day(con: sqlite3.Connection, plan_id: int, date: str, fields: dict) -> None:
    if not fields:
        return
    fields = {**fields, "plan_id": plan_id, "date": date}
    cols = [k for k in fields if k not in ("plan_id", "date")]
    con.execute(f"UPDATE plan_days SET {', '.join(f'{c} = :{c}' for c in cols)} "
                "WHERE plan_id = :plan_id AND date = :date", fields)


def move_day(con: sqlite3.Connection, plan_id: int, old: str, new: str) -> None:
    con.execute("UPDATE plan_days SET date = ?, moved = 1 WHERE plan_id = ? AND date = ?", (new, plan_id, old))


def delete_days(con: sqlite3.Connection, plan_id: int, undone_only: bool = False) -> int:
    sql = "DELETE FROM plan_days WHERE plan_id = ?" + (" AND done = 0" if undone_only else "")
    return con.execute(sql, (plan_id,)).rowcount


def delete_day(con: sqlite3.Connection, plan_id: int, date: str) -> int:
    return con.execute("DELETE FROM plan_days WHERE plan_id = ? AND date = ?", (plan_id, date)).rowcount


def all_active_days(con: sqlite3.Connection) -> list[sqlite3.Row]:
    """등록된 모든 계획의 날짜별 분량 — 여러 시험의 하루 합산 검사 (F5-R23)."""
    return list(con.execute(
        "SELECT d.*, p.exam_id, e.course_id, e.course, e.type FROM plan_days d "
        "JOIN plans p ON p.id = d.plan_id JOIN exams e ON e.id = p.exam_id "
        "WHERE p.state = 'active' AND e.removed_at IS NULL ORDER BY d.date"))


# ---------------------------------------------------------------- 공부 완료한 강의자료 (2026-10-06)

def material_done(con: sqlite3.Connection, course_id: str) -> dict[str, str]:
    """{자료 id: 체크한 시각} — 서비스 밖에서 공부했다고 체크한 자료."""
    return {r["material_id"]: r["done_at"] for r in con.execute(
        "SELECT material_id, done_at FROM material_done WHERE course_id = ?", (course_id,))}


def set_material_done(con: sqlite3.Connection, course_id: str, ids: list[str], done: bool) -> int:
    """체크·해제. 바뀐 줄 수를 돌려준다."""
    n = 0
    for mid in ids:
        if done:
            cur = con.execute("INSERT OR IGNORE INTO material_done (material_id, course_id, done_at) VALUES (?, ?, ?)",
                              (mid, course_id, now()))
        else:
            cur = con.execute("DELETE FROM material_done WHERE material_id = ? AND course_id = ?", (mid, course_id))
        n += cur.rowcount
    return n
