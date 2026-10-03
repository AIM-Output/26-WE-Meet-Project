"""과제 원장 읽기·쓰기 — 캘린더 이벤트(C1 deadline) · 과제 목록(탭) · 상세 · 내가 체크함 · 소요시간. 표준 라이브러리만.

화면 규칙 (F6 4절 라·마, 7절)
  - 캘린더에는 마감이 있고 사라지지 않은 것만 (마감 없는 과제는 목록에만, 8절)
  - 제출 완료 = e클래스 값. 내가 체크함 = 사용자 값. 둘 다면 제출 완료만 보인다(승격, F6-R32)
  - 탭: 진행 중(미완료 · 마감 전 또는 마감 없음) / 완료(제출 완료 · 내가 체크함) / 지난 마감(미완료 · 마감 지남)
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import config as C
from . import reconcile, store

COURSE_RE = re.compile(r"^(?P<short>.*?)\s*\[(?P<section>\d+)\]\s*\((?P<code>[A-Za-z0-9]+)\)\s*$")
NEW_HOURS = 24                  # 처음 본 지 이 시간 안이면 '새 과제'


class NotFound(Exception):
    pass


class Invalid(Exception):
    pass


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def split_course(name: str) -> dict:
    m = COURSE_RE.match(name or "")
    if not m:
        return {"short": name or "", "section": "", "code": ""}
    return {"short": m.group("short").strip(), "section": m.group("section"), "code": m.group("code")}


def iso(s: Optional[str]) -> Optional[str]:
    """'2026-09-16 16:00' → '2026-09-16T16:00:00' (로컬 시각, tz 없음)."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def parse_due(s: Optional[str]) -> Optional[datetime]:
    v = iso(s)
    return datetime.fromisoformat(v) if v else None


# ---------------------------------------------------------------- 과목

def courses() -> list[dict]:
    """courses.json → 과목 목록 (색은 목록 순서대로 — 캘린더·출결(F3)이 같은 색을 쓴다)."""
    raw = _read(C.COURSES_FILE, []) or []
    out = []
    for i, c in enumerate(raw):
        if not isinstance(c, dict):
            continue
        parts = split_course(c.get("name", ""))
        out.append({
            "id": str(c.get("id", i)), "name": c.get("name", ""), "short": parts["short"], "code": parts["code"],
            "section": parts["section"], "url": c.get("url", ""), "color": C.COURSE_PALETTE[i % len(C.COURSE_PALETTE)],
            "activityCount": len(c.get("activities", []) or []),
        })
    return out


# ---------------------------------------------------------------- 보기

def _attachments(raw: str) -> list[dict]:
    try:
        paths = json.loads(raw or "[]")
    except ValueError:
        paths = []
    return [{"name": Path(str(p).replace("\\", "/")).name, "path": str(p)} for p in paths if p]


def view(r: sqlite3.Row, color_of: dict[str, str], now: datetime) -> dict:
    """원장 한 줄 → 화면용 과제 (목록·상세·캘린더 extendedProps 공용)."""
    parts = split_course(r["course"])
    due = parse_due(r["due"])
    submitted = bool(r["submitted"])
    user_done = bool(r["user_done"]) and not submitted
    done = submitted or user_done
    first = datetime.fromisoformat(r["first_seen"]) if r["first_seen"] else None
    att = _attachments(r["attachments"])
    return {
        "id": r["id"], "cmid": r["cmid"] or "", "title": r["name"], "type": r["type"], "source": r["source"],
        "course": r["course"], "courseId": r["course_id"], "courseShort": parts["short"], "courseCode": parts["code"],
        "courseColor": color_of.get(r["course"]) or color_of.get(r["course_id"]) or "#64748b",
        "due": iso(r["due"]), "start": iso(r["start"]), "url": r["url"],
        "status": r["status"], "submitted": submitted, "graded": r["graded"], "description": r["description"],
        "attachments": att, "attachmentCount": len(att),
        "userDone": user_done, "userDoneAt": r["user_done_at"] if user_done else None,
        "promoted": bool(r["promoted_at"]) and submitted, "promotedAt": r["promoted_at"],
        "changed": {"at": r["changed_at"], "before": iso(r["prev_due"])} if r["changed_at"] and r["prev_due"] else None,
        "estimateHours": r["estimate_hours"],
        "firstSeen": r["first_seen"],
        "isNew": bool(first and not r["baseline"] and now - first < timedelta(hours=NEW_HOURS)),
        "removed": bool(r["removed_at"]), "removedAt": r["removed_at"],
        "done": done, "overdue": bool(due and due < now and not done),
        "legacyId": reconcile.legacy_id(r["url"], r["course"], r["name"], r["due"]) if r["due"] else None,
    }


def _colors() -> dict[str, str]:
    m: dict[str, str] = {}
    for c in courses():
        m[c["name"]] = c["color"]
        m[c["id"]] = c["color"]
    return m


def _rows(con: sqlite3.Connection, include_removed: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM items" + ("" if include_removed else " WHERE removed_at IS NULL") + " ORDER BY due = '', due, name"
    return con.execute(sql).fetchall()


def to_event(a: dict) -> dict:
    """과제 → FullCalendar 이벤트 (/api/events 의 kind='deadline'). 마감이 없으면 None 을 돌려주지 않게 호출 쪽에서 거른다.
    00:00 마감은 전날 밤(24:00)으로 본다 — '10월 4일 자정까지'(= 10/5 00:00)가 캘린더에서 10/5 칸에 들어가지 않게
    10/4 23:30 ~ 10/5 00:00 으로 그린다(끝은 배타적이라 10/5 칸에는 안 걸친다. 1분짜리면 주 보기에서 격자 밖으로 삐져나와
    30분 칸으로). 화면의 시각 표시는 '24:00'. 실제 마감은 extendedProps.due 그대로."""
    start, end = a["start"] or a["due"], a["due"] if a["start"] else None
    due = parse_due(a["due"])
    if not a["start"] and due and (due.hour, due.minute) == (0, 0):
        start = (due - timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%S")
        end = a["due"]
    return {
        "id": a["id"], "title": a["title"], "start": start, "end": end,
        "allDay": False, "editable": False,
        "extendedProps": {"kind": "deadline", **{k: v for k, v in a.items() if k not in ("id", "title", "start")}},
    }


def calendar_events(con: sqlite3.Connection, now: Optional[datetime] = None) -> list[dict]:
    now = now or datetime.now()
    colors = _colors()
    return [to_event(view(r, colors, now)) for r in _rows(con) if r["due"]]


def tab_of(a: dict) -> str:
    if a["done"]:
        return "done"
    return "past" if a["overdue"] else "open"


def list_assignments(con: sqlite3.Connection, tab: Optional[str] = None, course: Optional[str] = None,
                     include_removed: bool = False, now: Optional[datetime] = None) -> dict:
    """GET /api/assignments — 탭·과목으로 거른 목록과 탭별 건수. 순서: 진행 중·지난 마감은 마감 순, 완료는 최근 순."""
    now = now or datetime.now()
    colors = _colors()
    items = [view(r, colors, now) for r in _rows(con, include_removed)]
    if course:
        items = [a for a in items if course in (a["courseId"], a["courseShort"], a["course"])]
    counts = {"open": 0, "done": 0, "past": 0}
    for a in items:
        if not a["removed"]:
            counts[tab_of(a)] += 1
    if tab in ("open", "done", "past"):
        items = [a for a in items if tab_of(a) == tab and not a["removed"]]
        if tab != "open":
            items.sort(key=lambda a: a["due"] or "", reverse=True)
    return {"items": items, "counts": counts, "updatedAt": store.get_meta(con, "updated_at")}


def detail(con: sqlite3.Connection, iid: str, now: Optional[datetime] = None) -> dict:
    r = con.execute("SELECT * FROM items WHERE id = ?", (iid,)).fetchone()
    if not r:
        raise NotFound("과제가 없습니다")
    a = view(r, _colors(), now or datetime.now())
    hist = []
    for h in con.execute("SELECT * FROM changes WHERE item_id = ? ORDER BY seq DESC LIMIT 20", (iid,)):
        hist.append({"kind": h["kind"], "at": h["at"], "before": json.loads(h["before"]) if h["before"] else None,
                     "after": json.loads(h["after"]) if h["after"] else None})
    return {**a, "history": hist}


# ---------------------------------------------------------------- 쓰기 (사용자 값)

def patch(con: sqlite3.Connection, iid: str, user_done: Optional[bool] = None, estimate_hours: Any = ...,
          now: Optional[datetime] = None) -> dict:
    """PATCH /api/assignments/{id} — {userDone} 내가 체크함(F6-R30·R33) · {estimatedHours} 소요시간(F7, None 이면 기본값으로)."""
    now = now or datetime.now()
    r = con.execute("SELECT * FROM items WHERE id = ?", (iid,)).fetchone()
    if not r:
        raise NotFound("과제가 없습니다")
    sets: dict[str, Any] = {}
    if user_done is not None:
        sets["user_done"] = int(bool(user_done))
        sets["user_done_at"] = now.isoformat(timespec="seconds") if user_done else None
        store.add_change(con, iid, "user_done" if user_done else "user_undone", notified=True)
    if estimate_hours is not ...:
        if estimate_hours is not None:
            try:
                estimate_hours = float(estimate_hours)
            except (TypeError, ValueError):
                raise Invalid("소요시간은 숫자여야 합니다")
            if not 0.25 <= estimate_hours <= 200:
                raise Invalid("소요시간은 0.25 ~ 200 시간 사이여야 합니다")
        sets["estimate_hours"] = estimate_hours
    if sets:
        con.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), iid))
        store.touch(con)
    r = con.execute("SELECT * FROM items WHERE id = ?", (iid,)).fetchone()
    return view(r, _colors(), now)


def migrate_legacy(con: sqlite3.Connection, user_done: dict[str, bool], estimates: dict[str, float],
                   now: Optional[datetime] = None) -> dict:
    """브라우저에만 있던 '내가 체크함'·소요시간(예전 id 또는 새 id 기준)을 원장으로 옮긴다. 이미 서버에 값이 있으면 서버가 이긴다."""
    now = now or datetime.now()
    by_key: dict[str, sqlite3.Row] = {}
    for r in _rows(con, include_removed=True):
        by_key[r["id"]] = r
        if r["due"]:
            by_key[reconcile.legacy_id(r["url"], r["course"], r["name"], r["due"])] = r
    moved = {"userDone": 0, "estimates": 0, "unmatched": 0}
    for key, v in (user_done or {}).items():
        r = by_key.get(key)
        if r is None:
            moved["unmatched"] += 1
        elif v and not r["user_done"]:
            con.execute("UPDATE items SET user_done = 1, user_done_at = ? WHERE id = ?", (now.isoformat(timespec="seconds"), r["id"]))
            moved["userDone"] += 1
    for key, h in (estimates or {}).items():
        r = by_key.get(key)
        if r is None:
            moved["unmatched"] += 1
            continue
        try:
            h = float(h)
        except (TypeError, ValueError):
            continue
        if r["estimate_hours"] is None and 0.25 <= h <= 200:
            con.execute("UPDATE items SET estimate_hours = ? WHERE id = ?", (h, r["id"]))
            moved["estimates"] += 1
    if moved["userDone"] or moved["estimates"]:
        store.touch(con)
    return moved


# ---------------------------------------------------------------- 요약

def summary(con: sqlite3.Connection, now: Optional[datetime] = None) -> dict:
    """/api/status 의 F6 칸 — 기능 타일 숫자와 updatedAt."""
    now = now or datetime.now()
    soon_until = now + timedelta(days=3)
    colors = _colors()
    open_n = soon = overdue = new = 0
    for r in _rows(con):
        a = view(r, colors, now)
        if a["done"]:
            continue
        due = parse_due(r["due"])
        if a["overdue"]:
            overdue += 1
            continue
        open_n += 1
        if due and due <= soon_until:
            soon += 1
        if a["isNew"]:
            new += 1
    total = con.execute("SELECT COUNT(*) FROM items WHERE removed_at IS NULL").fetchone()[0]
    return {"updatedAt": store.get_meta(con, "updated_at"), "reconciledAt": store.get_meta(con, "reconciled_at"),
            "counts": {"total": total, "open": open_n, "soon": soon, "overdue": overdue, "new": new}}


def ensure_reconciled(con: sqlite3.Connection) -> Optional[dict]:
    """수집 JSON 이 원장보다 새로우면 반영한다 (runner 가 반영하지 못한 경우의 안전망). 반영했으면 결과."""
    if reconcile.stale(con):
        return reconcile.apply(con, full=False)
    return None
