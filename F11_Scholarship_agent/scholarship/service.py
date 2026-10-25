"""화면이 받는 모양 — 목록·상세·진행 상태·이력·원천·초안 재료. 표준 라이브러리만 (백엔드가 import 한다).

판정은 부를 때마다 지금 프로필로 계산한다(공지 200건 기준 수십 ms) — 프로필·민감정보가 바뀌면 다음 호출부터 바로 새 판정 (F11-R24·R32).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from . import config as C
from . import draft as drafting
from . import match, registry, store
from .textutil import days_until, semester_of, to_date

PROGRESS = ("draft", "approved", "applied", "selected", "not_selected", "skipped")
PROGRESS_LABEL = {"draft": "초안 대기", "approved": "승인·제출 예정", "applied": "신청함", "selected": "선정",
                  "not_selected": "탈락", "skipped": "관심 없음"}
GROUP_ORDER = {"eligible": 0, "needs_review": 1, "ineligible": 2, "expired": 3, "not_applicable": 4}


class NotFound(LookupError):
    pass


class Invalid(ValueError):
    pass


def _req(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """저장된 요건 — 규칙 판이 바뀌었으면 저장된 본문으로 다시 뽑는다(다시 내려받지 않는다)."""
    req = store.loads(row["req"], None)
    if req is None or row["extract_ver"] < C.EXTRACT_VERSION:
        from .collect import build_req          # collect 는 수집기를 함수 안에서만 import 한다 — 여기서 불러도 requests 없이 된다
        unit = registry.get(row["unit_key"]) if row["unit_key"] else None
        unread = sum(1 for a in store.loads(row["attachments"], []) if not a.get("read") and a.get("ext") not in (".jpg", ".png", ".zip"))
        req = build_req(dict(row), unit, unread)
        store.set_req(con, row["id"], req, C.EXTRACT_VERSION)
    return req


def _visible_sources(con: sqlite3.Connection, profile: Optional[dict]) -> tuple[set[str], dict[str, str]]:
    """켜진 원천 + 내 소속 게시판이 지금 가리키는 이름(학과를 바꾸면 예전 학과 공지는 목록에서 빠진다)."""
    rows = registry.resolve(profile, store.overrides(con))
    on = {r["key"] for r in rows if r["enabled"]}
    srows = store.source_rows(con)
    mine = {}
    for k in ("my_college", "my_dept"):
        disc = store.loads(srows[k]["discovered"], None) if k in srows else None
        hp = registry.homepage("college" if k == "my_college" else "dept", profile)
        if disc and hp and disc.get("homepage") == hp["homepage"]:
            mine[k] = disc.get("listedAs") or ""
        elif hp is None:
            on.discard(k)
    return on, mine


def _unit(row: sqlite3.Row) -> Optional[dict]:
    return registry.get(row["unit_key"]) if row["unit_key"] else None


def _item(row: sqlite3.Row, req: dict, res: dict, st: Optional[sqlite3.Row], dr: Optional[sqlite3.Row], today: date,
          baseline: Optional[str] = None) -> dict:
    unit = _unit(row)
    progress = st["progress"] if st else None
    deadline = res["deadline"]
    ask = bool(progress == "approved" and deadline and (days_until(deadline, today) or 0) < 0 and not (st and st["asked_applied"]))
    return {
        "id": row["id"], "title": req.get("scholarshipName") or row["title"], "rawTitle": row["title"],
        "kind": row["kind"], "url": row["url"], "postedAt": row["posted_at"], "firstSeen": row["first_seen"],
        "source": row["source"], "sourceName": row["source_name"], "writer": row["writer"],
        "org": req.get("provider") or (unit or {}).get("org") or row["writer"],
        "unit": {"key": unit["key"], "org": unit["org"]} if unit else None,
        "scholarshipKind": req.get("kind"), "amount": req.get("amount"),
        "verdict": res["verdict"], "systemVerdict": res["systemVerdict"], "label": res["label"], "flipped": res["flipped"],
        "hint": res["hint"], "sensitive": res["sensitive"], "failCount": res["failCount"],
        "deadline": deadline, "daysLeft": res["daysLeft"], "period": req.get("period"),
        "progress": progress, "progressLabel": PROGRESS_LABEL.get(progress or ""),
        "hasDraft": dr is not None, "draftStale": bool(dr is not None and dr["source_hash"] and dr["source_hash"] != row["content_hash"]),
        "onCalendar": bool(st and st["calendar_id"]), "askApplied": ask,
        # 첫 수집(기준선)에 한꺼번에 들어온 글은 '새 글'이 아니다 — 그 뒤 이틀 안에 처음 본 글만
        "isNew": bool(baseline and row["first_seen"] and row["first_seen"] > baseline
                      and row["first_seen"][:10] >= (today - timedelta(days=2)).isoformat()),
        "needsOcr": bool(req.get("needsOcr")), "attachmentsUnread": req.get("attachmentsUnread", 0),
        "confidence": res["confidence"],
    }


def _sort_key(it: dict) -> tuple:
    dl = it["daysLeft"]
    return (GROUP_ORDER[it["verdict"]], 0 if dl is not None and dl >= 0 else 1, dl if dl is not None and dl >= 0 else 9999,
            -(int((it["postedAt"] or it["firstSeen"] or "0")[:10].replace("-", "") or 0)))


def evaluate(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None,
             include_hidden: bool = False) -> list[dict]:
    """보이는 공지 전부 판정해 정렬 — 목록·알림·브리핑이 같이 쓴다."""
    today = today or date.today()
    on, mine = _visible_sources(con, profile)
    states = store.states(con)
    drs = {r["notice_id"]: r for r in store.drafts(con)}
    baseline = store.get_meta(con, "baseline_at")
    out = []
    for row in store.notice_rows(con):
        if row["dup_of"] or row["source"] not in on:
            continue
        if row["source"] in mine and mine[row["source"]] and mine[row["source"]] not in row["source_name"]:
            continue
        st = states.get(row["id"])
        if st and st["progress"] == "skipped" and not include_hidden:
            continue
        req = _req(con, row)
        override = {"verdict": st["override"]} if st and st["override"] else None
        res = match.decide(req, profile, {"isResult": bool(row["is_result"]), "postedAt": row["posted_at"] or row["first_seen"], "title": row["title"],
                                          "unit": _unit(row), "catalog": row["kind"] == "catalog"}, today, override)
        out.append(_item(row, req, res, st, drs.get(row["id"]), today, baseline))
    return sorted(out, key=_sort_key)


def overview(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None) -> dict:
    items = evaluate(con, profile, today)
    notices = [i for i in items if i["kind"] == "notice"]
    catalog = [i for i in items if i["kind"] == "catalog"]
    by = lambda xs, v: sum(1 for i in xs if i["verdict"] == v)   # noqa: E731
    return {
        "items": items,
        "counts": {"eligible": by(notices, "eligible"), "review": by(notices, "needs_review"),
                   "ineligible": by(notices, "ineligible"), "expired": by(notices, "expired"),
                   "notApplicable": by(notices, "not_applicable"), "notices": len(notices),
                   "catalogEligible": by(catalog, "eligible"), "catalogReview": by(catalog, "needs_review"),
                   "catalog": len(catalog), "inProgress": sum(1 for i in items if i["progress"] in ("draft", "approved"))},
        "profile": {"exists": bool(profile), "missing": [k for k in ("grade", "college", "department") if not (profile or {}).get(k)],
                    "campus": registry.campus_of(profile), "fields": registry.fields_of(profile)},
        "updatedAt": store.get_meta(con, "updated_at"), "lastOkAt": store.get_meta(con, "last_ok_at"),
        "catalogAt": store.get_meta(con, "catalog_at"), "baselineAt": store.get_meta(con, "baseline_at"),
        "llm": C.llm_configured(),
    }


def detail(con: sqlite3.Connection, nid: str, profile: Optional[dict], today: Optional[date] = None) -> Optional[dict]:
    today = today or date.today()
    row = store.notice(con, nid)
    if row is None:
        return None
    st = store.state(con, nid)
    dr = store.draft(con, nid)
    req = _req(con, row)
    override = {"verdict": st["override"]} if st and st["override"] else None
    res = match.decide(req, profile, {"isResult": bool(row["is_result"]), "postedAt": row["posted_at"] or row["first_seen"], "title": row["title"],
                                      "unit": _unit(row), "catalog": row["kind"] == "catalog"}, today, override)
    it = _item(row, req, res, st, dr, today, store.get_meta(con, "baseline_at"))
    dups = [dict(r) for r in con.execute("SELECT id, source_name, url FROM notices WHERE dup_of = ?", (nid,))]
    others = [{"id": d["notice_id"], "title": _title(con, d["notice_id"]), "updatedAt": d["updated_at"]}
              for d in store.drafts(con) if d["notice_id"] != nid]
    body = (row["body"] or "").strip()
    return {
        **it, "reasons": res["reasons"], "warning": res["warning"], "requirements": req,
        "documents": req.get("documents") or [], "applyMethod": req.get("applyMethod"), "applyUrl": req.get("applyUrl"),
        "contact": req.get("contact"), "selectionCount": req.get("selectionCount"), "notes": req.get("notes") or [],
        "otherConditions": req.get("otherConditions") or [],
        "body": body[:6000], "bodyTruncated": len(body) > 6000, "attachments": store.loads(row["attachments"], []),
        "alsoPostedAt": dups, "changedAt": row["changed_at"],
        "state": {"override": st["override"] if st else None, "overrideReason": st["override_reason"] if st else None,
                  "overrideAt": st["override_at"] if st else None, "progress": it["progress"],
                  "progressAt": st["progress_at"] if st else None, "appliedAt": st["applied_at"] if st else None,
                  "resultAt": st["result_at"] if st else None, "amount": st["amount"] if st else None,
                  "note": st["note"] if st else None, "calendarId": st["calendar_id"] if st else None,
                  "todos": store.loads(st["todos"], {}) if st else {}},
        "draft": ({"body": dr["body"], "generatedBy": dr["generated_by"], "borrowed": store.loads(dr["borrowed"], []),
                   "updatedAt": dr["updated_at"], "createdAt": dr["created_at"], "stale": it["draftStale"]} if dr else None),
        "otherDrafts": others,
    }


def _title(con: sqlite3.Connection, nid: str) -> str:
    r = store.notice(con, nid)
    if r is None:
        return nid
    req = store.loads(r["req"], {}) or {}
    return req.get("scholarshipName") or r["title"]


# ── 사용자가 바꾸는 것 ───────────────────────────────────────

def patch(con: sqlite3.Connection, nid: str, body: dict) -> None:
    """{verdict: eligible|ineligible|null(되돌리기), reason, progress: …|null, note, amount, askedApplied}"""
    if store.notice(con, nid) is None:
        raise NotFound(nid)
    now = store.now_iso()
    fields: dict[str, Any] = {}
    if "verdict" in body:
        v = body["verdict"]
        if v not in (None, "eligible", "ineligible"):
            raise Invalid("판정은 eligible · ineligible · null(되돌리기) 중 하나입니다")
        fields.update(override=v, override_reason=(body.get("reason") or None) if v else None, override_at=now if v else None)
    if "progress" in body:
        p = body["progress"]
        if p is not None and p not in PROGRESS:
            raise Invalid(f"진행 상태는 {', '.join(PROGRESS)} 중 하나입니다")
        fields.update(progress=p, progress_at=now)
        if p == "applied":
            fields["applied_at"] = now
        if p in ("selected", "not_selected"):
            fields["result_at"] = now
    if "note" in body:
        fields["note"] = (body.get("note") or "")[:2000] or None
    if "amount" in body:
        fields["amount"] = (body.get("amount") or "")[:100] or None
    if body.get("askedApplied"):
        fields["asked_applied"] = 1
    store.put_state(con, nid, **fields)
    store.touch(con)


def history(con: sqlite3.Connection) -> dict:
    """이력 탭 — 학기별 신청 N · 선정 M · 금액 합계 + 상태별 목록 (F11-S13). 관심 없음도 여기서 되돌린다."""
    out: dict[str, dict] = {}
    rows = con.execute("SELECT * FROM user_state WHERE progress IS NOT NULL ORDER BY progress_at DESC").fetchall()
    for st in rows:
        at = to_date(st["applied_at"] or st["progress_at"]) or date.today()
        sem = semester_of(at)
        g = out.setdefault(sem, {"semester": sem, "applied": 0, "selected": 0, "amountTotal": 0, "items": []})
        if st["progress"] in ("applied", "selected", "not_selected"):
            g["applied"] += 1
        if st["progress"] == "selected":
            g["selected"] += 1
            g["amountTotal"] += _won(st["amount"])
        row = store.notice(con, st["notice_id"])
        g["items"].append({"id": st["notice_id"], "title": _title(con, st["notice_id"]), "progress": st["progress"],
                           "progressLabel": PROGRESS_LABEL[st["progress"]], "at": st["progress_at"], "amount": st["amount"],
                           "note": st["note"], "url": row["url"] if row else None})
    return {"semesters": sorted(out.values(), key=lambda g: g["semester"], reverse=True)}


def _won(s: Optional[str]) -> int:
    """'200만원' · '1,500,000원' · '150' (만원으로 봄) → 원. 못 읽으면 0."""
    if not s:
        return 0
    t = s.replace(",", "").replace(" ", "")
    m = re.search(r"(\d+(?:\.\d+)?)만", t)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"(\d+)원?", t)
    if not m:
        return 0
    v = int(m.group(1))
    return v * 10000 if v < 10000 else v


# ── 원천 ────────────────────────────────────────────────────

def source_rows(con: sqlite3.Connection, profile: Optional[dict]) -> list[dict]:
    srows = store.source_rows(con)
    out = []
    counts = {r["source"]: r["n"] for r in con.execute("SELECT source, COUNT(*) AS n FROM notices WHERE dup_of IS NULL GROUP BY source")}
    for r in registry.resolve(profile, store.overrides(con)):
        s = srows.get(r["key"])
        disc = store.loads(s["discovered"], None) if s is not None else None
        target = None
        if r["kind"] == "profile_board":
            hp = registry.homepage(r.get("level", "dept"), profile)
            target = {"name": (hp or {}).get("name"), "homepage": (hp or {}).get("homepage"), "listedAs": (hp or {}).get("listedAs"),
                      "board": disc.get("boardUrl") if disc and hp and disc.get("homepage") == hp["homepage"] else None,
                      "boardLabel": disc.get("boardLabel") if disc else None, "categoryLabel": disc.get("categoryLabel") if disc else None}
        out.append({
            "key": r["key"], "name": r["name"], "org": r.get("org"), "group": r["group"], "kind": r["kind"], "url": r.get("url"),
            "why": r.get("why"), "relevance": r["relevance"], "enabled": r["enabled"], "userSet": r["userSet"],
            "lastRunAt": s["last_run_at"] if s is not None else None, "lastOkAt": s["last_ok_at"] if s is not None else None,
            "lastCount": s["last_count"] if s is not None else None, "lastNew": s["last_new"] if s is not None else None,
            "error": s["last_error"] if s is not None else None, "stored": counts.get(r["key"], 0), "target": target,
            "relay": r["kind"] == "relay",
        })
    return out


def set_source(con: sqlite3.Connection, key: str, enabled: Optional[bool]) -> None:
    if registry.get(key) is None:
        raise NotFound(key)
    store.put_source(con, key, enabled=None if enabled is None else int(bool(enabled)))
    store.touch(con)


# ── 초안 재료 (프로필과 따로 — 별도 삭제 가능, F11 6절) ───────────

MATERIAL_KEYS = ("careerGoal", "activities", "hardship", "highlights")


def materials(con: sqlite3.Connection, profile: Optional[dict] = None) -> dict:
    m = store.loads(store.get_meta(con, "materials"), None)
    if m is None:
        dc = (profile or {}).get("draftContext") or {}
        return {"exists": False, **{k: dc.get(k, "") for k in MATERIAL_KEYS}, "updatedAt": None,
                "fromProfile": bool(dc)}
    return {"exists": True, **{k: m.get(k, "") for k in MATERIAL_KEYS}, "updatedAt": m.get("updatedAt"), "fromProfile": False}


def put_materials(con: sqlite3.Connection, body: dict) -> dict:
    data = {k: str(body.get(k) or "").strip()[:2000] for k in MATERIAL_KEYS}
    data["updatedAt"] = store.now_iso()
    store.set_meta(con, "materials", json.dumps(data, ensure_ascii=False))
    return materials(con)


def delete_materials(con: sqlite3.Connection) -> None:
    store.set_meta(con, "materials", None)


# ── 초안 ────────────────────────────────────────────────────

def make_draft(con: sqlite3.Connection, nid: str, profile: Optional[dict], borrow_from: Optional[str] = None,
               llm: Optional[Callable] = None) -> dict:
    """초안 만들기 — 재료가 아직 없으면 화면이 먼저 재료 카드를 띄운다(needsMaterials)."""
    d = detail(con, nid, profile)
    if d is None:
        raise NotFound(nid)
    mats = materials(con, profile)
    borrowed = None
    if borrow_from:
        src = store.draft(con, borrow_from)
        if src is None:
            raise Invalid("가져올 초안이 없습니다")
        borrowed = {"from": borrow_from, "title": _title(con, borrow_from), "body": src["body"]}
    body, by = drafting.build(d, profile or {}, mats, borrowed=borrowed, llm=llm)
    store.save_draft(con, nid, body, generated_by=by, source_hash=store.notice(con, nid)["content_hash"],
                     borrowed=[{"from": borrowed["from"], "title": borrowed["title"]}] if borrowed else [])
    st = store.state(con, nid)
    if not st or not st["progress"]:
        store.put_state(con, nid, progress="draft", progress_at=store.now_iso())
    store.touch(con)
    return detail(con, nid, profile)        # type: ignore[return-value]


def save_draft_body(con: sqlite3.Connection, nid: str, body: str) -> None:
    if store.draft(con, nid) is None:
        raise NotFound(nid)
    store.save_draft(con, nid, body[:30000])


# ── 캘린더·할 일 (C1 — 백엔드가 add_event 로 넘겨준다) ─────────────

AddEvent = Callable[[dict], Optional[dict]]


def add_calendar(con: sqlite3.Connection, nid: str, profile: Optional[dict], add_event: AddEvent) -> dict:
    """신청 마감 → 내 캘린더(C1 '내 일정', 출처 sch:<id>) (F11-R55). 마감을 못 읽었으면 넣지 않는다."""
    d = detail(con, nid, profile)
    if d is None:
        raise NotFound(nid)
    if not d["deadline"]:
        raise Invalid("신청 마감을 읽지 못해 캘린더에 넣을 수 없습니다 — 원문에서 확인하세요")
    dl = d["deadline"]
    timed = "T" in dl
    ev = add_event({"title": f"[장학 마감] {d['title'][:60]}", "start": dl + (":00" if timed and len(dl) == 16 else ""),
                    "end": None, "all_day": not timed, "category": "etc",
                    "memo": f"{d['org'] or ''}\n{d['url']}\n신청은 본인이 직접 합니다 (유니버스는 제출하지 않습니다)".strip(),
                    "is_todo": False, "origin": f"sch:{nid}"})
    if ev:
        store.put_state(con, nid, calendar_id=str(ev.get("id")))
    store.touch(con)
    return {"event": ev}


def add_todo(con: sqlite3.Connection, nid: str, index: int, profile: Optional[dict], add_event: AddEvent,
             today: Optional[date] = None) -> dict:
    """제출 서류 하나 → 할 일 (마감 하루 전 기한, F11-R54)."""
    d = detail(con, nid, profile)
    if d is None:
        raise NotFound(nid)
    docs = d["documents"]
    if not 0 <= index < len(docs):
        raise Invalid("서류 번호가 맞지 않습니다")
    due = to_date(d["deadline"]) if d["deadline"] else None
    today = today or date.today()
    day = (due - timedelta(days=1)) if due else today + timedelta(days=1)
    if day < today:
        day = today
    ev = add_event({"title": f"{docs[index][:60]} 준비 — {d['title'][:30]}", "start": day.isoformat(), "end": None,
                    "all_day": True, "category": "etc", "memo": f"장학 제출 서류 · 마감 {d['deadline'] or '미정'}\n{d['url']}",
                    "is_todo": True, "origin": f"sch:{nid}:doc{index}"})
    st = store.state(con, nid)
    todos = store.loads(st["todos"], {}) if st else {}
    if ev:
        todos[str(index)] = str(ev.get("id"))
        store.put_state(con, nid, todos=json.dumps(todos))
    store.touch(con)
    return {"event": ev}


# ── 타일·브리핑 ─────────────────────────────────────────────

def status_summary(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None) -> dict:
    items = [i for i in evaluate(con, profile, today) if i["kind"] == "notice"]
    open_ = [i for i in items if i["verdict"] in ("eligible", "needs_review")]
    soon = [i for i in open_ + [i for i in items if i["progress"] in ("draft", "approved")]
            if i["daysLeft"] is not None and 0 <= i["daysLeft"] <= 3]
    return {
        "available": True, "updatedAt": store.get_meta(con, "updated_at"), "lastOkAt": store.get_meta(con, "last_ok_at"),
        "eligible": sum(1 for i in items if i["verdict"] == "eligible"),
        "review": sum(1 for i in items if i["verdict"] == "needs_review"),
        "soon": len({i["id"] for i in soon}), "inProgress": sum(1 for i in items if i["progress"] in ("draft", "approved")),
        "profileExists": bool(profile),
        "next": next(({"id": i["id"], "title": i["title"], "daysLeft": i["daysLeft"], "label": i["label"]}
                      for i in sorted(open_, key=lambda x: (x["daysLeft"] is None or x["daysLeft"] < 0, x["daysLeft"] or 0))
                      if i["daysLeft"] is not None and i["daysLeft"] >= 0), None),
    }


def brief(con: sqlite3.Connection, profile: Optional[dict], days: int = 3, today: Optional[date] = None) -> list[dict]:
    """F10 브리핑 — 마감 임박 장학만 (F11-R74)."""
    return [{"id": i["id"], "title": i["title"], "daysLeft": i["daysLeft"], "label": i["label"], "progress": i["progressLabel"]}
            for i in evaluate(con, profile, today)
            if i["kind"] == "notice" and i["daysLeft"] is not None and 0 <= i["daysLeft"] <= days
            and (i["verdict"] in ("eligible", "needs_review") or i["progress"] in ("draft", "approved"))]
