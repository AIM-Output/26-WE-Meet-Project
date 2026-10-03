"""수집 결과(JSON) → 과제 원장(eclass.db) 반영 — 신규 · 변경 · 삭제 판정 (F6 5절 '수집 성공 후'). 표준 라이브러리만.

    1. deadlines.json(캘린더 + 과제 + 퀴즈) + assignments.json(설명·첨부·채점, 마감 없는 과제 포함) 을 활동 id 로 합친다
    2. 원장과 비교 → 신규 / 마감 변경(prev_due·changed_at, '변경됨') / 제출 확인 / 사라짐(removed_at, 기록은 남긴다)
    3. '내가 체크함'·소요시간은 건드리지 않는다. 체크한 과제가 e클래스에서 제출로 확인되면 승격(promoted_at)만 적는다 (F6-R32·R34)
    4. updated_at 을 올린다 → 화면이 다시 불러온다. 알림(신규·변경)은 changes.notified=0 으로 남겨 백엔드가 보낸다

처음 반영할 때(원장이 비어 있을 때)는 '기준선' — 이미 있던 과제를 신규로 알리지 않는다.

id 는 'dl:<cmid>' (e클래스 활동 번호). 활동 링크가 없는 캘린더 일정(과목 일정·개인 일정)만 'dl:e<과목|이름 해시>'.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import config as C
from . import store

MOD_RE = re.compile(r"/mod/([a-z0-9_]+)/view\.php\?id=(\d+)")
DUE_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2}) (\d{1,2}):(\d{2})$")
VIDEO_MODS = {"vod", "ubcontent", "econtent", "xncommons", "hvp", "url"}
CAL_MAX_EVENTS = 10         # Moodle '다가오는 일정'은 기본 10건까지만 보여 준다 — 꽉 찼으면 빠진 것이 '삭제'인지 알 수 없다
CAL_LOOKAHEAD_DAYS = 14     # 이 안에 마감인데 캘린더에서 빠졌으면 삭제로 본다


def _read(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def mod_cmid(url: str) -> tuple[str, str]:
    m = MOD_RE.search(url or "")
    return (m.group(1), m.group(2)) if m else ("", "")


def item_id(it: dict) -> str:
    mod, cmid = mod_cmid(it.get("url", ""))
    cmid = str(it.get("cmid") or cmid)
    if cmid:
        return f"dl:{cmid}"
    key = f"{it.get('course', '')}|{it.get('name', '')}"
    return "dl:e" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def legacy_id(url: str, course: str, name: str, due: str) -> str:
    """예전 대시보드(eclass_data.py)가 쓰던 id — 브라우저에만 저장돼 있던 '내가 체크함'·소요시간을 옮길 때 짝을 찾는다."""
    key = f"{url}|{course}|{name}|{due}"
    return "dl:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def type_of(mod: str, raw: str, source: str) -> str:
    raw = raw or ""
    if source == "quiz" or mod == "quiz" or "퀴즈" in raw or "quiz" in raw.lower():
        return "퀴즈"
    if source == "assign" or mod == "assign" or "과제" in raw:
        return "과제"
    if mod in VIDEO_MODS or any(w in raw.lower() for w in ("동영상", "vod", "영상", "video", "콘텐츠")):
        return "동영상"
    return "일정"


def is_submitted(status: str) -> bool:
    """e클래스 '제출 여부' 문구 → 제출했는가. '제출 완료'·'제출됨'·'시청 완료'(동영상) 는 참, '제출 안 함'·'미제출'·'미시청'·'없음' 은 거짓."""
    s = (status or "").replace(" ", "")
    if not s or any(w in s for w in ("안함", "미제출", "미시청", "없음", "하지않", "않음")):
        return False
    return "완료" in s or "제출됨" in s


def norm_due(s: str) -> str:
    """'2026-10-5 0:00' 같이 0 을 안 붙인 값도 'YYYY-MM-DD HH:MM' 으로. 날짜가 아니면 ''."""
    m = DUE_RE.match((s or "").strip())
    if not m:
        return ""
    y, mo, d, h, mi = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"


def incoming(now: datetime) -> tuple[dict[str, dict], dict]:
    """JSON 파일들 → {id: 필드}, 정보 {stamp, courseIds, calendarCount}."""
    dl = _read(C.DEADLINES_FILE, {})
    items = dl.get("items", []) if isinstance(dl, dict) else (dl or [])
    stamp = dl.get("updated_at") if isinstance(dl, dict) else None
    assigns = _read(C.ASSIGNMENTS_FILE, []) or []
    courses = _read(C.COURSES_FILE, []) or []
    course_ids = {str(c.get("name")): str(c.get("id")) for c in courses if isinstance(c, dict)}
    course_names = {v: k for k, v in course_ids.items()}
    by_url = {a.get("url"): a for a in assigns if isinstance(a, dict)}

    out: dict[str, dict] = {}

    def put(src: dict, source: str, raw_type: str, start: str, due: str, status: str):
        url = src.get("url", "")
        mod, cmid = mod_cmid(url)
        a = by_url.get(url) or {}
        if a:
            source = "assign"                   # 과제 화면에서 읽은 활동 — 과목 화면에서 사라지면 삭제로 본다
        iid = item_id({**src, "cmid": src.get("cmid") or cmid})
        cid = str(src.get("course_id") or a.get("course_id") or course_ids.get(src.get("course", ""), ""))
        # 캘린더는 과목을 '소프트웨어공학론' 처럼 줄여 적는다 → 과목 목록의 정식 이름으로
        course = a.get("course") or course_names.get(cid) or src.get("course", "")
        row = {
            "id": iid, "cmid": str(src.get("cmid") or cmid or ""), "mod": mod or ("assign" if source == "assign" else ""),
            "type": type_of(mod, raw_type, source), "source": source, "course": course,
            "course_id": cid,
            "name": src.get("name", "") or a.get("name", ""), "url": url,
            "start": norm_due(start), "due": norm_due(due) or norm_due(a.get("due", "")),
            "status": status or a.get("submitted", "") or "", "graded": a.get("graded", "") or "",
            "description": a.get("description", "") or src.get("description", "") or "",
            "attachments": json.dumps(a.get("attachments", []) or [], ensure_ascii=False),
        }
        row["submitted"] = int(is_submitted(row["status"]))
        prev = out.get(iid)
        if prev is None or (prev["source"] == "calendar" and source != "calendar"):
            out[iid] = row
        elif not prev["due"] and row["due"]:
            prev["due"] = row["due"]

    for it in items:
        if isinstance(it, dict):
            put(it, it.get("source") or "calendar", it.get("type", ""), it.get("start", ""), it.get("due", ""),
                it.get("status", ""))
    for a in assigns:                       # 마감이 없는 과제도 목록에는 둔다 (8절 — 캘린더에는 안 올린다)
        if isinstance(a, dict) and item_id({"url": a.get("url"), "cmid": a.get("cmid")}) not in out:
            put(a, "assign", "과제", "", a.get("due", ""), a.get("submitted", ""))
    cal_count = sum(1 for it in items if isinstance(it, dict) and (it.get("source") or "calendar") == "calendar")
    return out, {"stamp": stamp, "courseIds": set(course_ids.values()), "calendarCount": cal_count}


FIELDS = ("cmid", "mod", "type", "source", "course", "course_id", "name", "url", "start", "due", "status", "submitted",
          "graded", "description", "attachments")


def apply(con: sqlite3.Connection, full: bool = True, now: Optional[datetime] = None, force: bool = False) -> dict:
    """JSON → 원장. full=False(과목·부분만 돌린 수집)면 '사라진 과제' 판정을 하지 않는다. 결과 건수."""
    now = now or datetime.now()
    ts = now.isoformat(timespec="seconds")
    rows, info = incoming(now)
    result = {"new": 0, "changed": 0, "removed": 0, "restored": 0, "submitted": 0, "promoted": 0, "total": len(rows),
              "skipped": False}
    if info["stamp"] is None and not rows:
        result["skipped"] = True
        return result
    if not force and info["stamp"] and store.get_meta(con, "reconciled") == info["stamp"]:
        result["skipped"] = True
        return result
    baseline = con.execute("SELECT COUNT(*) FROM items").fetchone()[0] == 0 and not store.get_meta(con, "baselined")
    existing = {r["id"]: r for r in con.execute("SELECT * FROM items")}

    for iid, new in rows.items():
        old = existing.get(iid)
        vals = {k: new[k] for k in FIELDS}
        if old is None:
            con.execute(
                f"INSERT INTO items (id, {', '.join(FIELDS)}, first_seen, last_seen, baseline, submitted_at) "
                f"VALUES (?, {', '.join('?' for _ in FIELDS)}, ?, ?, ?, ?)",
                (iid, *vals.values(), ts, ts, int(baseline), ts if new["submitted"] else None))
            store.add_change(con, iid, "new", None, {"due": new["due"], "name": new["name"]}, notified=baseline, at=ts)
            result["new"] += 1
            continue
        extra: dict[str, Any] = {"last_seen": ts}
        if old["removed_at"]:
            extra["removed_at"] = None
            store.add_change(con, iid, "restored", None, {"due": new["due"]}, notified=True, at=ts)
            result["restored"] += 1
        if old["due"] and new["due"] and old["due"] != new["due"]:
            extra.update(prev_due=old["due"], changed_at=ts)
            store.add_change(con, iid, "due", {"due": old["due"]}, {"due": new["due"]}, at=ts)
            result["changed"] += 1
        elif not new["due"] and old["due"] and new["source"] == "calendar":
            vals["due"] = old["due"]            # 캘린더가 날짜를 못 읽은 회차 — 이전 값을 지킨다
        if new["submitted"] and not old["submitted"]:
            extra["submitted_at"] = ts
            if old["user_done"]:
                extra["promoted_at"] = ts       # '내가 체크함' → 'e클래스 제출 완료' 로 조용히 승격 (F6-R32)
                store.add_change(con, iid, "promoted", None, None, notified=True, at=ts)
                result["promoted"] += 1
            else:
                store.add_change(con, iid, "submitted", None, None, notified=True, at=ts)
            result["submitted"] += 1
        if not new["description"] and old["description"] and new["source"] != "assign":
            vals["description"] = old["description"]       # 캘린더에서만 보인 회차는 설명이 없다 — 과제 화면에서 읽은 것을 지킨다
            vals["attachments"] = old["attachments"]
            vals["graded"] = old["graded"]
        sets = {**vals, **extra}
        con.execute(f"UPDATE items SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), iid))

    if full:
        horizon = now + timedelta(days=CAL_LOOKAHEAD_DAYS)
        for iid, old in existing.items():
            if iid in rows or old["removed_at"]:
                continue
            gone = False
            if old["course_id"] and info["courseIds"] and old["course_id"] not in info["courseIds"]:
                gone = True                     # 과목 중도 취소 — 목록에서 빠진다 (8절)
            elif old["source"] in ("assign", "quiz", "vod") or old["mod"] in ("assign", "quiz"):
                gone = True                     # 과목 화면의 활동 목록에서 사라졌다 (삭제·숨김) — 과제·퀴즈·동영상은 과목 화면에서 다 본다
            elif old["due"]:
                due = _dt(old["due"])
                # 캘린더 '다가오는 일정'은 지난 일정을 보여 주지 않고, 10건이 넘으면 잘린다 → 가까운 미래인데 빠졌을 때만 삭제로 본다
                gone = bool(due and now < due <= horizon and info["calendarCount"] < CAL_MAX_EVENTS)
            if gone:
                con.execute("UPDATE items SET removed_at = ? WHERE id = ?", (ts, iid))
                store.add_change(con, iid, "removed", {"due": old["due"]}, None, notified=True, at=ts)
                result["removed"] += 1

    if info["stamp"]:
        store.set_meta(con, "reconciled", info["stamp"])
    store.set_meta(con, "baselined", store.get_meta(con, "baselined") or ts)
    store.set_meta(con, "reconciled_at", ts)
    store.touch(con)
    return result


def _dt(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return None


def stale(con: sqlite3.Connection) -> bool:
    """deadlines.json 이 원장보다 새로운가 (runner 가 반영하지 못한 수집 — 예전 코드·강제 종료)."""
    dl = _read(C.DEADLINES_FILE, {})
    stamp = dl.get("updated_at") if isinstance(dl, dict) else None
    return bool(stamp) and store.get_meta(con, "reconciled") != stamp
