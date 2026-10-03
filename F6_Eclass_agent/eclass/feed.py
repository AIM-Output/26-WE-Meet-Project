"""E클래스 새 글·자료 — 수집기가 이미 받아 둔 게시판 글·강의자료(manifest.json)를 '새로 올라왔다'는 소식으로 만든다. 표준 라이브러리만.

과제·마감(원장 items, reconcile.py)과는 따로 돈다 — 그쪽 흐름은 건드리지 않는다.

종류
    notice    공지 게시판 글 (이름에 '공지')                  → 한 건씩 알림 '공지 · 운영체제 · 중간고사 안내'
    board     자료실 등 그 밖에 모으는 게시판 글                → 하루치를 묶어 '새 글·자료 N건'
    material  강의자료 파일 (ubfile·resource·folder 활동)     → 위와 같이 묶음
    (게시판 글·과제에 붙은 첨부 파일은 그 글·과제의 일부라 따로 세지 않는다)

처음 들여올 때(표가 비어 있을 때)는 기준선 — 이미 있던 글·자료를 '새 글'로 알리지 않고 읽은 것으로 둔다.
manifest 가 바뀔 때만(수정 시각·크기) 다시 읽는다. 수집기는 학생 글이 올라오는 게시판(Q&A·팀빌딩)을 모으지 않으므로 여기도 없다.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import config as C
from . import store

KINDS = ("notice", "board", "material")
KIND_LABEL = {"notice": "공지", "board": "자료실 글", "material": "강의자료"}
POSTED_RE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2}):(\d{2}))?")
EXCERPT = 160
DEFAULT_SETTINGS = {"notices": True, "materials": True}


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _abs(rel: str) -> Path:
    return C.DATA_DIR.parent / str(rel or "").replace("\\", "/")


def _posted(raw: str) -> Optional[str]:
    """manifest 의 작성일(':\\r\\n\\t\\t2026-09-29 15:48' 처럼 지저분하다) → 'YYYY-MM-DDTHH:MM:00'."""
    m = POSTED_RE.search(raw or "")
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    h, mi = int(m.group(4) or 0), int(m.group(5) or 0)
    return f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{mi:02d}:00"


def _stamp() -> Optional[str]:
    try:
        st = C.MANIFEST_FILE.stat()
    except OSError:
        return None
    return f"{st.st_mtime_ns}:{st.st_size}"


def incoming() -> dict[str, dict]:
    """manifest.json + courses.json → {id: 행}."""
    m = _read(C.MANIFEST_FILE, {}) or {}
    courses = _read(C.COURSES_FILE, []) or []
    mods = {str(a.get("cmid")): a.get("mod") for c in courses if isinstance(c, dict) for a in c.get("activities", []) or []}
    out: dict[str, dict] = {}
    for key, p in (m.get("posts") or {}).items():
        if not isinstance(p, dict):
            continue
        board = p.get("activity") or ""
        out[f"post:{key}"] = {
            "kind": "notice" if "공지" in board else "board", "course": p.get("course", ""), "course_id": str(p.get("course_id", "")),
            "board": board, "title": p.get("title") or p.get("post") or "(제목 없음)", "url": p.get("url", ""),
            "path": p.get("path", ""), "posted_at": _posted(p.get("date", "")) or _posted(Path(str(p.get("path", ""))).name),
            "fetched_at": p.get("fetched_at"), "size": None,
            "attachments": json.dumps([Path(str(a).replace("\\", "/")).name for a in p.get("attachments") or []], ensure_ascii=False),
        }
    for key, f in (m.get("files") or {}).items():
        if not isinstance(f, dict) or f.get("post"):
            continue
        cmid = str(f.get("cmid", ""))
        mod = mods.get(cmid)
        path = str(f.get("path", ""))
        if mod not in C.RESOURCE_MODULES and (mod is not None or "\\게시판\\" in path or "\\과제\\" in path):
            continue                                    # 게시판 글·과제의 첨부 — 그 글·과제의 일부
        out["file:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]] = {
            "kind": "material", "course": f.get("course", ""), "course_id": str(f.get("course_id", "")),
            "board": f.get("activity", ""), "title": Path(path.replace("\\", "/")).name or key.rsplit("/", 1)[-1],
            "url": f"{C.BASE_URL}/mod/{mod}/view.php?id={cmid}" if mod and cmid else "", "path": path,
            # 올린 시각 = 파일 응답의 Last-Modified (collect.uploaded_at). 예전에 받은 파일은 다음 수집 때 채워진다
            "posted_at": f.get("uploaded_at") or None, "fetched_at": f.get("downloaded_at"),
            "size": int(f["size"]) if str(f.get("size", "")).isdigit() else None,
            "attachments": "[]",
        }
    return out


FIELDS = ("kind", "course", "course_id", "board", "title", "url", "path", "posted_at", "fetched_at", "size", "attachments")


def sync(con: sqlite3.Connection, now: Optional[datetime] = None, force: bool = False) -> dict:
    """manifest → feed 표. 새로 본 것은 first_seen=지금. 처음이면 기준선(읽음·알림 안 함). 결과 건수."""
    stamp = _stamp()
    if stamp is None:
        return {"new": 0, "skipped": True}
    if not force and store.get_meta(con, "feed_stamp") == stamp:
        return {"new": 0, "skipped": True}
    ts = (now or datetime.now()).isoformat(timespec="seconds")
    rows = incoming()
    existing = {r["id"]: r for r in con.execute("SELECT id, removed_at FROM feed")}
    baseline = not existing and not store.get_meta(con, "feed_baselined")
    new = 0
    for iid, r in rows.items():
        vals = [r[k] for k in FIELDS]
        if iid in existing:
            con.execute(f"UPDATE feed SET {', '.join(f'{k} = ?' for k in FIELDS)}, removed_at = NULL WHERE id = ?", (*vals, iid))
            continue
        con.execute(f"INSERT INTO feed (id, {', '.join(FIELDS)}, first_seen, read_at, notified, baseline) "
                    f"VALUES (?, {', '.join('?' for _ in FIELDS)}, ?, ?, ?, ?)",
                    (iid, *vals, ts, ts if baseline else None, int(baseline), int(baseline)))
        new += 1
    gone = [iid for iid, r in existing.items() if iid not in rows and not r["removed_at"]]
    con.executemany("UPDATE feed SET removed_at = ? WHERE id = ?", [(ts, i) for i in gone])
    store.set_meta(con, "feed_stamp", stamp)
    store.set_meta(con, "feed_baselined", store.get_meta(con, "feed_baselined") or ts)
    if new or gone:
        store.set_meta(con, "feed_updated_at", datetime.now().isoformat(timespec="milliseconds"))
    return {"new": 0 if baseline else new, "baseline": new if baseline else 0, "removed": len(gone), "skipped": False}


# ---------------------------------------------------------------- 보기

def _short(course: str) -> str:
    return re.sub(r"\s*\[\d+\]\s*\([A-Za-z0-9]+\)\s*$", "", course or "").strip()


def _body(path: str) -> str:
    """수집기가 쓴 글 .md → 본문 (머리 목록·첨부 목록 빼고)."""
    try:
        lines = _abs(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    try:
        i = lines.index("## 본문")
        return "\n".join(lines[i + 1:]).strip()
    except ValueError:
        return "\n".join(l for l in lines[1:] if not l.startswith("- ") and not l.startswith("#")).strip()


def view(r: sqlite3.Row, full: bool = False) -> dict:
    body = _body(r["path"]) if r["kind"] != "material" else ""
    flat = " ".join(body.split())
    out = {
        "id": r["id"], "kind": r["kind"], "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]), "course": r["course"],
        "courseId": r["course_id"], "courseShort": _short(r["course"]), "board": r["board"], "title": r["title"], "url": r["url"],
        "postedAt": r["posted_at"], "fetchedAt": r["fetched_at"], "firstSeen": r["first_seen"], "size": r["size"],
        "attachments": json.loads(r["attachments"] or "[]"), "read": bool(r["read_at"]), "isNew": not r["baseline"] and not r["read_at"],
        "removed": bool(r["removed_at"]), "excerpt": flat[:EXCERPT] + ("…" if len(flat) > EXCERPT else ""),
        "localPath": r["path"],
    }
    if full:
        out["body"] = body
    return out


def _order_key(r: sqlite3.Row) -> str:
    """올라온 순 — e클래스에 올라온 시각(글은 작성일, 파일은 Last-Modified). 모르면 받은 시각."""
    return r["posted_at"] or r["fetched_at"] or r["first_seen"] or ""


def list_items(con: sqlite3.Connection, kind: Optional[str] = None, course: Optional[str] = None,
               unread: bool = False, limit: int = 300) -> dict:
    rows = [r for r in con.execute("SELECT * FROM feed WHERE removed_at IS NULL")]
    counts = {"all": len(rows), "unread": sum(1 for r in rows if not r["read_at"]), **{k: 0 for k in KINDS}}
    for r in rows:
        counts[r["kind"]] = counts.get(r["kind"], 0) + 1
    if kind in KINDS:
        rows = [r for r in rows if r["kind"] == kind]
    if course:
        rows = [r for r in rows if course in (r["course_id"], r["course"], _short(r["course"]))]
    if unread:
        rows = [r for r in rows if not r["read_at"]]
    rows.sort(key=_order_key, reverse=True)
    return {"items": [view(r) for r in rows[:limit]], "counts": counts,
            "updatedAt": store.get_meta(con, "feed_updated_at"), "settings": settings(con)}


def detail(con: sqlite3.Connection, iid: str) -> Optional[dict]:
    r = con.execute("SELECT * FROM feed WHERE id = ?", (iid,)).fetchone()
    return view(r, full=True) if r else None


def mark_read(con: sqlite3.Connection, ids: Optional[list[str]] = None, read: bool = True) -> int:
    ts = datetime.now().isoformat(timespec="seconds")
    if ids is None:
        n = con.execute("UPDATE feed SET read_at = ? WHERE read_at IS NULL", (ts,)).rowcount
    else:
        n = 0
        for i in ids:
            n += con.execute("UPDATE feed SET read_at = ? WHERE id = ?", (ts if read else None, i)).rowcount
    if n:
        store.set_meta(con, "feed_updated_at", datetime.now().isoformat(timespec="milliseconds"))
    return n


def summary(con: sqlite3.Connection) -> dict:
    r = con.execute("SELECT COUNT(*) AS total, SUM(read_at IS NULL) AS unread, "
                    "SUM(read_at IS NULL AND kind = 'notice') AS notices FROM feed WHERE removed_at IS NULL").fetchone()
    return {"total": r["total"] or 0, "unread": r["unread"] or 0, "unreadNotices": r["notices"] or 0,
            "updatedAt": store.get_meta(con, "feed_updated_at")}


def settings(con: sqlite3.Connection) -> dict:
    s = store.get_json(con, "feed_settings", {}) or {}
    return {k: bool(s.get(k, v)) for k, v in DEFAULT_SETTINGS.items()}


def save_settings(con: sqlite3.Connection, **kw) -> dict:
    cur = settings(con)
    cur.update({k: bool(v) for k, v in kw.items() if k in DEFAULT_SETTINGS and v is not None})
    store.set_json(con, "feed_settings", cur)
    return cur


# ---------------------------------------------------------------- 알림

def deliver(con: sqlite3.Connection, push, now: Optional[datetime] = None) -> int:
    """새 글·자료 → 알림 센터 (kind=eclass). 공지는 한 건씩, 자료실 글·강의자료는 하루치 묶음. 보낸 것은 notified=1.
    push(nid, kind, ref_id, title, body, href, fire_at, missed, upsert) — notify.Push 와 같은 모양."""
    if push is None:
        return 0
    now = now or datetime.now()
    st = settings(con)
    pending = con.execute("SELECT * FROM feed WHERE notified = 0 AND baseline = 0 AND removed_at IS NULL ORDER BY first_seen").fetchall()
    if not pending:
        return 0
    added = 0
    days: dict[str, list[sqlite3.Row]] = {}
    for r in pending:
        if r["kind"] == "notice":
            if st["notices"] and not r["read_at"]:
                excerpt = " ".join(_body(r["path"]).split())[:80]
                if push(f"ec-post:{r['id']}", "eclass", r["id"], f"공지 · {_short(r['course'])} · {r['title']}",
                        excerpt or r["board"], f"/eclass/posts?post={r['id']}", datetime.fromisoformat(r["first_seen"]), False, False):
                    added += 1
        elif st["materials"] and not r["read_at"]:
            days.setdefault(r["first_seen"][:10], []).append(r)
    for day, rows in sorted(days.items()):
        all_rows = con.execute("SELECT * FROM feed WHERE kind != 'notice' AND baseline = 0 AND substr(first_seen, 1, 10) = ? "
                               "ORDER BY first_seen", (day,)).fetchall()
        names = [f"[{_short(x['course'])}] {x['title']}" for x in all_rows]
        body = ", ".join(names[:3]) + (f" 외 {len(names) - 3}건" if len(names) > 3 else "")
        if push(f"ec-new:{day}", "eclass", None, f"새 글·자료 {len(names)}건", body, "/eclass/posts?filter=unread",
                now if day == now.date().isoformat() else datetime.fromisoformat(f"{day}T23:59:00"), False, True):
            added += 1
    con.executemany("UPDATE feed SET notified = 1 WHERE id = ?", [(r["id"],) for r in pending])
    return added
