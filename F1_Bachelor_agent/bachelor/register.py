"""등록 — 후보(Candidate)를 저장소에 반영한다: 같은 일정 알아보기 · 여러 원천 합치기 · 날짜 변경 감지 (F1-R20~R24).

같은 일정 알아보기 (재수집해도 같은 항목으로)
    학사일정 표: (원천, 학기, 정규화 제목, 같은 제목 안에서의 순번) — 날짜가 바뀌어도 같은 항목으로 본다 → '변경됨'
    공지:        (원천, 글 번호, 정규화 제목, 순번)
여러 원천 합치기 (F1 7절 '중복 판정')
    새 항목이 들어오면 다른 글·원천의 항목 중 **정규화 제목 + 시작일**이 같은 것(또는 시작일·유형이 같고 한 제목이 다른
    제목을 품는 것)을 찾아 같은 events 행에 붙인다. 대표값은 원천 우선순위(학사일정 표 > 학사 공지 > 학과)로 화면에서 고른다.
날짜 변경 (F1-R23)
    같은 항목의 날짜·시각이 바뀌면 이전 값을 prev 에 남기고, 그 항목이 대표값이면 events.changed_* 와 알림 1건.
원문 삭제
    학사일정 표에서 사라진 행·수정된 글에서 사라진 일정은 지우지 않고 removed_at 만 적는다 ('원문 삭제됨').
사용자 값(숨김·승인·메모·알림)은 events 에만 있으므로 여기서 덮어쓰지 않는다 (F1-R24).
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

from . import config as C
from .models import Candidate
from .store import dumps, now_iso, priority_map
from .textutil import iso_date, normalize_title, short_hash


def _dates(c: Candidate) -> dict:
    return {"start_date": iso_date(c.start), "start_time": c.start_time,
            "end_date": iso_date(c.end), "end_time": c.end_time}


def _row_dates(r: sqlite3.Row) -> dict:
    return {k: r[k] for k in ("start_date", "start_time", "end_date", "end_time")}


def fmt_dates(d: dict) -> str:
    """{'start_date': '2026-09-05', …} → '9/5 10:00 ~ 9/8' (알림 문구용)."""
    def one(ds: Optional[str], ts: Optional[str]) -> str:
        if not ds:
            return "?"
        s = f"{int(ds[5:7])}/{int(ds[8:10])}"
        return f"{s} {ts}" if ts else s
    s = one(d.get("start_date"), d.get("start_time"))
    if d.get("end_date") and (d["end_date"] != d.get("start_date") or d.get("end_time")):
        s += " ~ " + one(d["end_date"], d.get("end_time"))
    return s


def _idents(source_key: str, cands: list[Candidate], post_id: Optional[str]) -> list[tuple[str, Candidate]]:
    groups: dict[tuple, list[Candidate]] = defaultdict(list)
    for c in cands:
        scope = post_id if post_id is not None else c.semester
        groups[(scope, normalize_title(c.title))].append(c)
    out = []
    for (scope, norm), cs in groups.items():
        cs.sort(key=lambda c: (c.start or date.max, c.end or date.max))
        for i, c in enumerate(cs):
            out.append((f"{source_key}:{short_hash(scope or '', norm, str(i), n=12)}", c))
    return out


def _merge_target(con: sqlite3.Connection, c: Candidate, norm: str, post_id: Optional[str], source_key: str) -> Optional[str]:
    """다른 원천·글에서 이미 들어온 같은 일정의 event_id. 같은 글 안의 항목끼리는 합치지 않는다."""
    if c.start is None:
        return None
    rows = con.execute(
        "SELECT event_id, norm, type, source_key, post_id FROM items WHERE start_date = ? AND removed_at IS NULL",
        (c.start.isoformat(),)).fetchall()
    loose = None
    for r in rows:
        if r["source_key"] == source_key and (post_id is None or r["post_id"] == post_id):
            continue
        if r["norm"] == norm:
            return r["event_id"]
        short, long_ = sorted((r["norm"], norm), key=len)
        if loose is None and r["type"] == c.type and len(short) >= 4 and short in long_:
            loose = r["event_id"]
    return loose


def _is_representative(con: sqlite3.Connection, event_id: str, ident: str, prio: dict[str, int]) -> bool:
    rows = con.execute("SELECT ident, source_key, confidence FROM items WHERE event_id = ? AND removed_at IS NULL",
                       (event_id,)).fetchall()
    if not rows:
        return True
    best = min(rows, key=lambda r: (prio.get(r["source_key"], 9), -r["confidence"]))
    return best["ident"] == ident


def add_notification(con: sqlite3.Connection, nid: str, kind: str, ref_id: Optional[str], title: str, body: str,
                     href: Optional[str], fire_at: Optional[str] = None) -> None:
    now = now_iso()
    con.execute(
        "INSERT OR IGNORE INTO notifications(id, kind, ref_id, title, body, fire_at, delivered_at, missed, href) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)", (nid, kind, ref_id, title, body, fire_at or now, now, href))


def register(con: sqlite3.Connection, source_key: str, cands: list[Candidate], *,
             post_id: Optional[str] = None, snapshot_since: Optional[date] = None) -> dict:
    """원천 하나(학사일정 표 전체) 또는 공지 글 하나의 후보 전체를 반영한다.

    snapshot_since: 학사일정 표처럼 매번 전체를 받는 원천이면 그 기간 안에서 이번에 안 보인 항목을 '원문 삭제'로 표시.
    반환: {"new": n, "changed": n, "same": n, "removed": n}
    """
    now = now_iso()
    prio = priority_map(con)
    stats = {"new": 0, "changed": 0, "same": 0, "removed": 0}
    seen: set[str] = set()
    for ident, c in _idents(source_key, cands, post_id):
        seen.add(ident)
        norm = normalize_title(c.title)
        fields = {
            "source_key": source_key, "post_id": c.post_id if c.post_id is not None else post_id, "title": c.title,
            "norm": norm, **_dates(c), "type": c.type, "audience": dumps(c.audience.to_dict()),
            "evidence": dumps(c.evidence), "confidence": c.confidence, "semester": c.semester, "url": c.url,
            "posted_at": c.posted_at, "action_url": c.action_url, "action_label": c.action_label,
            "flags": dumps(c.flags), "last_seen": now,
        }
        row = con.execute("SELECT * FROM items WHERE ident = ?", (ident,)).fetchone()
        if row is None:
            event_id = _merge_target(con, c, norm, post_id, source_key)
            if event_id is None:
                event_id = f"ac:{source_key}:{short_hash(ident, n=8)}"
                con.execute("INSERT OR IGNORE INTO events(id, first_seen, updated_at) VALUES (?, ?, ?)",
                            (event_id, now, now))
            cols = ["ident", "event_id", *fields.keys(), "first_seen"]
            con.execute(f"INSERT INTO items({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})",
                        (ident, event_id, *fields.values(), now))
            stats["new"] += 1
            continue

        before, after = _row_dates(row), _dates(c)
        sets = dict(fields, removed_at=None)
        if before != after and before["start_date"] and after["start_date"]:
            sets.update(prev=dumps(before), changed_at=now)
            stats["changed"] += 1
            if _is_representative(con, row["event_id"], ident, prio):
                con.execute("UPDATE events SET changed_at = ?, changed_before = ?, updated_at = ? WHERE id = ?",
                            (now, dumps(before), now, row["event_id"]))
                add_notification(
                    con, f"chg:{row['event_id']}:{now}", "change", row["event_id"],
                    f"{c.title} 날짜가 바뀌었습니다", f"{fmt_dates(before)} → {fmt_dates(after)}",
                    f"/academic?event={row['event_id']}")
        else:
            stats["same"] += 1
        con.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE ident = ?", (*sets.values(), ident))

    # 이번에 안 보인 항목 → 원문 삭제됨 (지우지 않는다)
    if post_id is not None:
        stale = con.execute("SELECT ident FROM items WHERE source_key = ? AND post_id = ? AND removed_at IS NULL",
                            (source_key, post_id)).fetchall()
    elif snapshot_since is not None:
        stale = con.execute(
            "SELECT ident FROM items WHERE source_key = ? AND removed_at IS NULL AND COALESCE(end_date, start_date) >= ?",
            (source_key, snapshot_since.isoformat())).fetchall()
    else:
        stale = []
    for r in stale:
        if r["ident"] not in seen:
            _drop_or_mark(con, r["ident"], now, keep=post_id is None)
            stats["removed"] += 1
    return stats


def retire_source_items(con: sqlite3.Connection, source_key: str) -> int:
    """원천이 읽는 게시판이 바뀌었을 때(소속 변경·직접 지정) 이전 게시판에서 온 항목 정리.
    사용자가 손대지 않은 것은 지우고, 손댄 것(숨김·메모·승인)은 '원문 삭제됨'으로 남긴다. 처리한 글 기록도 비운다."""
    now = now_iso()
    rows = con.execute("SELECT ident FROM items WHERE source_key = ? AND removed_at IS NULL", (source_key,)).fetchall()
    for r in rows:
        _drop_or_mark(con, r["ident"], now, keep=False)
    con.execute("DELETE FROM posts WHERE source_key = ?", (source_key,))
    return len(rows)


def _drop_or_mark(con: sqlite3.Connection, ident: str, now: str, keep: bool) -> None:
    """이번에 안 나온 항목. 학사일정 표에서 행이 사라졌거나(keep) 사용자가 손댄 일정이면 '원문 삭제됨'으로 남기고,
    공지 글을 다시 읽어(수정·추출 규칙 개선) 사라진 항목은 조용히 지운다 — 옛 추출 결과가 쌓이지 않게."""
    row = con.execute("SELECT event_id FROM items WHERE ident = ?", (ident,)).fetchone()
    ev = con.execute("SELECT * FROM events WHERE id = ?", (row["event_id"],)).fetchone() if row else None
    touched = ev is not None and (ev["user_status"] or ev["memo"] or ev["pinned"] or ev["reminders"])
    others = con.execute("SELECT COUNT(*) FROM items WHERE event_id = ? AND ident != ?",
                         (row["event_id"], ident)).fetchone()[0] if row else 0
    if keep or touched:
        con.execute("UPDATE items SET removed_at = ? WHERE ident = ?", (now, ident))
        return
    con.execute("DELETE FROM items WHERE ident = ?", (ident,))
    if row and not others:
        con.execute("DELETE FROM events WHERE id = ?", (row["event_id"],))
        con.execute("DELETE FROM notifications WHERE ref_id = ? AND read_at IS NULL AND kind = 'academic'",
                    (row["event_id"],))


def snapshot_window(today: Optional[date] = None) -> date:
    """학사일정 표에서 '이번에 안 보이면 삭제로 본다' 의 기준일 = 가져오는 범위의 시작."""
    today = today or date.today()
    return today - timedelta(days=int(C.TABLE_KEEP_MONTHS * 30.5))


def item_dates(r: sqlite3.Row) -> dict:
    return _row_dates(r)
