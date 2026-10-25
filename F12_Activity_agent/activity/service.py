"""화면이 받는 모양 — 목록·상세·진행 상태·이력·원천·초안 재료·캘린더·할 일·타일. 표준 라이브러리만 (백엔드가 import 한다).

등급(내 관심사 / 관련 있음 / 관심 밖)은 부를 때마다 지금 관심사로 계산한다(공지 500건 수십 ms) — 관심사를 바꾸면 다음 호출부터
바로 새 등급 (F12-R15). 모집 상태(모집 중 · 마감 · 결과 발표 · 지난 공지 · 대상 아님)는 등급과 따로 본다 — 끝난 공지는 등급과 상관없이 접는다.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any, Callable, Optional

from . import config as C
from . import draft as drafting
from . import interests as I
from . import registry, store
from scholarship import attachments, basicinfo
from scholarship.textutil import days_until, semester_of, to_date

PROGRESS = ("saved", "draft", "approved", "applied", "selected", "not_selected", "skipped")
PROGRESS_LABEL = {"saved": "담음", "draft": "초안 대기", "approved": "제출 예정", "applied": "지원함", "selected": "선정",
                  "not_selected": "탈락", "skipped": "관심 없음"}
ACTIVE = ("saved", "draft", "approved", "applied", "selected", "not_selected")     # '담은 것' — 관심 없음이 아닌 진행 상태
GRADE_LABEL = {"match": "내 관심사", "related": "관련 있음", "other": "관심 밖"}
STATUS_LABEL = {"open": "모집 중", "expired": "마감", "result": "결과 발표", "stale": "지난 공지", "not_for_me": "대상 아님"}
GRADE_RANK = {"match": 0, "related": 1, None: 1, "other": 2}

AddEvent = Callable[[dict], Optional[dict]]
RemoveEvent = Callable[[str], None]


class NotFound(LookupError):
    pass


class Invalid(ValueError):
    pass


def _info(con: sqlite3.Connection, row: sqlite3.Row) -> dict:
    """저장된 정보 — 규칙 판이 바뀌었으면 저장된 본문으로 다시 뽑는다(다시 내려받지 않는다)."""
    info = store.loads(row["info"], None)
    if info is None or row["extract_ver"] < C.EXTRACT_VERSION:
        from .collect import build_info          # collect 는 수집기를 함수 안에서만 import 한다 — requests 없이 된다
        unit = registry.get(row["unit_key"]) if row["unit_key"] else None
        body_short = len((row["body"] or "").strip()) < C.ATTACH_BODY_SHORT     # 본문이 길면 첨부를 읽지 않으므로 '못 읽음'도 아니다
        unread = attachments.unread_count(store.loads(row["attachments"], [])) if body_short else 0
        info = build_info(dict(row), unit, unread)
        store.set_info(con, row["id"], info, C.EXTRACT_VERSION)
    return info


def _visible_sources(con: sqlite3.Connection, profile: Optional[dict]) -> tuple[set[str], dict[str, str]]:
    """켜진 원천 + 내 소속 게시판이 지금 가리키는 이름(학과를 바꾸면 예전 학과 공지는 목록에서 빠진다) — F11 과 같은 규칙."""
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


def _status(info: dict, row: sqlite3.Row, today: date) -> tuple[str, Optional[str], Optional[int]]:
    period = info.get("period") or {}
    deadline = period.get("end")
    left = days_until(deadline, today) if deadline else None
    posted = to_date(row["posted_at"] or row["first_seen"])
    if info.get("result"):
        return "result", deadline, left
    if info.get("gradOnly") or info.get("foreignOnly"):
        return "not_for_me", deadline, left
    if (deadline and left is not None and left < 0) or info.get("closedMark"):
        return "expired", deadline, left
    if not deadline and posted and (today - posted).days > C.STALE_DAYS:
        return "stale", deadline, left
    return "open", deadline, left


def _affiliated(src: Optional[dict], unit: Optional[dict], profile: Optional[dict]) -> bool:
    """내 학과와 관련된 원천의 글인가 — 관련 사업단 · 내 단과대학·학과 게시판 · 내 캠퍼스 원천 (LLM 이 없을 때 '관련 있음' 근거)."""
    if not profile:
        return False
    for s in (src, unit):
        if s and (s.get("audience") or {}).get("scope") in ("related", "campus", "mine"):
            if registry.relevance(s, profile)["level"] in ("related", "campus", "mine"):
                return True
    return False


def _audience_note(info: dict, profile: Optional[dict]) -> Optional[str]:
    g = (profile or {}).get("grade")
    if info.get("grades") and g and g not in info["grades"]:
        return f"{'·'.join(map(str, info['grades']))}학년 대상 — 내 {g}학년"
    return None


def _evaluate_row(row: sqlite3.Row, info: dict, interests: dict, llm: Optional[dict], profile: Optional[dict],
                  st: Optional[sqlite3.Row], dr: Optional[sqlite3.Row], today: date, baseline: Optional[str]) -> dict:
    src = registry.get(row["source"])
    unit = registry.get(row["unit_key"]) if row["unit_key"] else None
    text = I.Text(f"{info.get('boardCategory') or ''} {row['title']}", f"{(row['body'] or '')[:6000]}\n{(row['attach_text'] or '')[:3000]}")
    g = I.grade(text, interests, llm=llm, affiliated=_affiliated(src, unit, profile), participation=bool(info.get("participation")),
                informational=info.get("category") == "other" and not info.get("participation"))
    system = g["grade"]
    grade = system
    flipped = False
    if st and st["override"] in ("match", "other"):
        grade = st["override"]
        flipped = grade != system
    status, deadline, left = _status(info, row, today)
    progress = st["progress"] if st else None
    ask = bool(progress == "approved" and deadline and (left or 0) < 0 and not (st and st["asked_applied"]))
    groups = {(src or {}).get("group"), (unit or {}).get("group")}
    return {
        "id": row["id"], "title": info.get("title") or row["title"], "rawTitle": row["title"], "url": row["url"],
        "postedAt": row["posted_at"], "firstSeen": row["first_seen"], "source": row["source"], "sourceName": row["source_name"],
        "sourceGroup": (src or {}).get("group"), "isProgram": "project" in groups, "writer": row["writer"],
        # 주관 — 제목의 [기관] · 사업단 · 작성 부서. coursemos(교육혁신본부·성장마루)의 작성자 칸은 사람 이름이라 원천 기관으로 대신한다
        "org": info.get("host") or (unit or {}).get("org")
               or (row["writer"] if (src or {}).get("kind") != "coursemos" else None) or (src or {}).get("org"),
        "unit": {"key": unit["key"], "org": unit["org"]} if unit else None,
        "category": info.get("category"), "categoryLabel": info.get("categoryLabel"), "boardCategory": info.get("boardCategory"),
        "grade": grade, "systemGrade": system, "gradeLabel": GRADE_LABEL.get(grade or "", None), "flipped": flipped,
        "hits": g["hits"], "chips": I.chips(g["hits"]), "by": g["by"],
        "status": status, "statusLabel": STATUS_LABEL[status], "deadline": deadline, "daysLeft": left, "period": info.get("period"),
        "target": info.get("target"), "place": info.get("place"), "benefit": info.get("benefit"),
        "audienceNote": _audience_note(info, profile),
        "progress": progress, "progressLabel": PROGRESS_LABEL.get(progress or ""), "saved": progress in ACTIVE,
        "hasDraft": dr is not None, "draftStale": bool(dr is not None and dr["source_hash"] and dr["source_hash"] != row["content_hash"]),
        "onCalendar": bool(st and st["calendar_id"]), "askApplied": ask,
        # 첫 수집(기준선)에 한꺼번에 들어온 글은 '새 글'이 아니다 — 그 뒤 이틀 안에 처음 본 글만
        "isNew": bool(baseline and row["first_seen"] and row["first_seen"] > baseline
                      and row["first_seen"][:10] >= (today - timedelta(days=2)).isoformat()),
        "needsOcr": bool(info.get("needsOcr")), "ocr": bool(info.get("ocr")),
    }


def _sort_key(it: dict) -> tuple:
    rank = GRADE_RANK[it["grade"]] if it["status"] == "open" else 3
    dl = it["daysLeft"]
    soon = 0 if dl is not None and dl >= 0 else 1
    return (rank, soon, dl if soon == 0 else 9999, -(int((it["postedAt"] or it["firstSeen"] or "0")[:10].replace("-", "") or 0)))


def evaluate(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None,
             include_hidden: bool = False) -> list[dict]:
    """보이는 공지 전부에 등급·모집 상태를 매겨 정렬 — 목록·알림·타일·LLM 판단이 같이 쓴다."""
    today = today or date.today()
    interests = I.from_profile(profile)
    llm = store.llm_grades(con, I.ihash(interests)) if I.is_set(interests) else {}
    on, mine = _visible_sources(con, profile)
    states = store.states(con)
    drs = {r["notice_id"]: r for r in store.drafts(con)}
    baseline = store.get_meta(con, "baseline_at")
    out = []
    dropped = I.dropped_categories()
    for row in store.notice_rows(con):
        if row["dup_of"] or row["source"] not in on:
            continue
        if row["source"] in mine and mine[row["source"]] and mine[row["source"]] not in row["source_name"]:
            continue
        st = states.get(row["id"])
        if st and st["progress"] == "skipped" and not include_hidden:
            continue
        info = _info(con, row)
        if info.get("category") in dropped:           # 학사·행정 안내 — 대외활동이 아니다 (예전에 모은 것도 숨긴다)
            continue
        out.append(_evaluate_row(row, info, interests, llm.get(row["id"]), profile, st, drs.get(row["id"]), today, baseline))
    return sorted(out, key=_sort_key)


def wide_keywords(items: list[dict], interests: dict) -> list[dict]:
    """열린 공지의 30% 넘게(15건 이상) 걸리는 자유 키워드 — '키워드 "학생" 에 32건이 걸렸습니다' (F12 8절)."""
    open_ = [i for i in items if i["status"] == "open"]
    out = []
    for kw in interests.get("keywords") or []:
        n = sum(1 for i in open_ if any(h["type"] == "keyword" and h["label"] == kw for h in i["hits"]))
        if n >= C.WIDE_KEYWORD_MIN and n >= len(open_) * C.WIDE_KEYWORD_SHARE:
            out.append({"keyword": kw, "count": n})
    return out


def overview(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None) -> dict:
    items = evaluate(con, profile, today)
    interests = I.from_profile(profile)
    open_ = [i for i in items if i["status"] == "open"]
    by = lambda v: sum(1 for i in open_ if i["grade"] == v)   # noqa: E731
    cats: dict[str, int] = {}
    for i in open_:
        cats[i["category"] or "other"] = cats.get(i["category"] or "other", 0) + 1
    return {
        "items": items,
        "counts": {"match": by("match"), "related": by("related"), "other": by("other"), "open": len(open_),
                   "closed": len(items) - len(open_), "total": len(items), "program": sum(1 for i in open_ if i["isProgram"]),
                   "programMatch": sum(1 for i in open_ if i["isProgram"] and i["grade"] == "match"),
                   "saved": sum(1 for i in items if i["saved"]),
                   "inProgress": sum(1 for i in items if i["progress"] in ("draft", "approved")), "categories": cats},
        "interests": {**interests, "set": I.is_set(interests)},
        "tags": [{"key": t["key"], "words": t["words"][:6]} for t in I.catalog()["tags"]],
        "categories": I.category_labels(),
        "wide": wide_keywords(items, interests),
        "profile": {"exists": bool(profile), "missing": [k for k in ("grade", "college", "department") if not (profile or {}).get(k)]},
        "updatedAt": store.get_meta(con, "updated_at"), "lastOkAt": store.get_meta(con, "last_ok_at"),
        "baselineAt": store.get_meta(con, "baseline_at"), "llm": C.llm_configured(),
    }


def _reasons(it: dict, interests: dict) -> list[str]:
    """상세의 '왜 이 등급인가' — 걸린 관심사·키워드를 말로 (F12-R23 · US-4)."""
    if not I.is_set(interests):
        return ["관심사를 아직 고르지 않아 등급을 매기지 않았습니다 — 관심사를 고르면 맞는 것만 위로 올립니다"]
    out = []
    for h in it["hits"]:
        where = "제목" if h.get("where") == "title" else "본문"
        if h["type"] == "tag":
            out.append(f"관심사 태그 '{h['label']}' — {where}에 '{h.get('word')}'")
        elif h["type"] == "keyword":
            out.append(f"내 키워드 '{h['label']}' — {where}에 있음")
        elif h["type"] == "exclude":
            out.append(f"제외 키워드 '{h['label']}' 가 {where}에 있어 관심 밖으로 뺐습니다")
        elif h["type"] == "llm":
            out.append(f"키워드는 없지만 LLM 이 관련도를 판단했습니다{(' — ' + h['reason']) if h.get('reason') else ''}")
        elif h["type"] == "affiliation":
            out.append("관심사 키워드는 없지만 내 학과와 관련된 원천(사업단·학과 게시판)의 모집 글입니다")
    if not out:
        out.append("내 관심사·키워드가 제목과 본문에 없습니다")
    if it["flipped"]:
        out.insert(0, f"내가 '{GRADE_LABEL.get(it['grade'] or '', '')}'(으)로 바꿨습니다 — 시스템 판단은 '{GRADE_LABEL.get(it['systemGrade'] or '', '없음')}'")
    return out


def detail(con: sqlite3.Connection, nid: str, profile: Optional[dict], today: Optional[date] = None) -> Optional[dict]:
    today = today or date.today()
    row = store.notice(con, nid)
    if row is None:
        return None
    st = store.state(con, nid)
    dr = store.draft(con, nid)
    info = _info(con, row)
    interests = I.from_profile(profile)
    llm = store.llm_grades(con, I.ihash(interests)).get(nid) if I.is_set(interests) else None
    it = _evaluate_row(row, info, interests, llm, profile, st, dr, today, store.get_meta(con, "baseline_at"))
    dups = [dict(r) for r in con.execute("SELECT id, source_name, url FROM notices WHERE dup_of = ?", (nid,))]
    others = [{"id": d["notice_id"], "title": _title(con, d["notice_id"]), "updatedAt": d["updated_at"]}
              for d in store.drafts(con) if d["notice_id"] != nid]
    body = (row["body"] or "").strip()
    return {
        **it, "reasons": _reasons(it, interests), "info": info, "grades": info.get("grades"),
        "eventPeriod": info.get("eventPeriod"), "fee": info.get("fee"), "capacity": info.get("capacity"),
        "documents": info.get("documents") or [], "applyMethod": info.get("applyMethod"), "applyUrl": info.get("applyUrl"),
        "contact": info.get("contact"), "notes": info.get("notes") or [], "evidence": info.get("evidence") or {},
        "body": body[:6000], "bodyTruncated": len(body) > 6000, "attachments": store.loads(row["attachments"], []),
        "ocrText": attachments.ocr_part(row["attach_text"])[:6000] or None,
        "alsoPostedAt": dups, "changedAt": row["changed_at"],
        "state": {"override": st["override"] if st else None, "overrideAt": st["override_at"] if st else None,
                  "progress": it["progress"], "progressAt": st["progress_at"] if st else None,
                  "savedAt": st["saved_at"] if st else None, "appliedAt": st["applied_at"] if st else None,
                  "resultAt": st["result_at"] if st else None, "note": st["note"] if st else None,
                  "calendarId": st["calendar_id"] if st else None, "todos": store.loads(st["todos"], {}) if st else {}},
        "draft": ({"body": dr["body"], "generatedBy": dr["generated_by"], "borrowed": store.loads(dr["borrowed"], []),
                   "updatedAt": dr["updated_at"], "createdAt": dr["created_at"], "stale": it["draftStale"]} if dr else None),
        "otherDrafts": others,
    }


def _title(con: sqlite3.Connection, nid: str) -> str:
    r = store.notice(con, nid)
    if r is None:
        return nid
    info = store.loads(r["info"], {}) or {}
    return info.get("title") or r["title"]


# ── 사용자가 바꾸는 것 ───────────────────────────────────────

def _calendar(con: sqlite3.Connection, nid: str, d: dict, add_event: Optional[AddEvent]) -> Optional[dict]:
    """신청 마감 → C1 내 일정(출처 act:<id>). 마감을 못 읽었거나 이미 넣었으면 넣지 않는다 (F12 8절 '마감 없는 공지')."""
    if add_event is None or not d.get("deadline") or (d.get("state") or {}).get("calendarId"):
        return None
    dl = d["deadline"]
    timed = "T" in dl
    label = "대여 신청 마감" if d.get("category") == "rental" else "신청 마감"
    ev = add_event({"title": f"[{label}] {d['title'][:60]}", "start": dl + (":00" if timed and len(dl) == 16 else ""),
                    "end": None, "all_day": not timed, "category": "etc",
                    "memo": f"{d['org'] or ''}\n{d['url']}\n신청은 본인이 직접 합니다 (유니버스는 제출하지 않습니다)".strip(),
                    "is_todo": False, "origin": f"act:{nid}"})
    if ev:
        store.put_state(con, nid, calendar_id=str(ev.get("id")))
    return ev


def patch(con: sqlite3.Connection, nid: str, body: dict, profile: Optional[dict] = None, *,
          add_event: Optional[AddEvent] = None, remove_event: Optional[RemoveEvent] = None) -> None:
    """{grade: match|other|null(되돌리기)} 등급 뒤집기 · {saved: true|false} 담기 · {progress: …|null} · {note} · {askedApplied}.
    담으면(또는 초안·제출 예정으로 처음 들어오면) 신청 마감을 캘린더에 넣는다 (F12-R41). 담기를 풀면 그때 넣은 일정을 지운다."""
    if store.notice(con, nid) is None:
        raise NotFound(nid)
    now = store.now_iso()
    st = store.state(con, nid)
    before = st["progress"] if st else None
    fields: dict[str, Any] = {}
    if "grade" in body:
        g = body["grade"]
        if g not in (None, "match", "other"):
            raise Invalid("등급은 match · other · null(되돌리기) 중 하나입니다")
        fields.update(override=g, override_at=now if g else None)
    new_progress = before
    if "saved" in body:
        if body["saved"] and before in (None, "skipped"):
            new_progress = "saved"
        elif not body["saved"] and before == "saved":
            new_progress = None
    if "progress" in body:
        p = body["progress"]
        if p is not None and p not in PROGRESS:
            raise Invalid(f"진행 상태는 {', '.join(PROGRESS)} 중 하나입니다")
        new_progress = p
    if new_progress != before:
        fields.update(progress=new_progress, progress_at=now)
        if new_progress == "saved":
            fields["saved_at"] = now
        if new_progress == "applied":
            fields["applied_at"] = now
        if new_progress in ("selected", "not_selected"):
            fields["result_at"] = now
    if "note" in body:
        fields["note"] = (body.get("note") or "")[:2000] or None
    if body.get("askedApplied"):
        fields["asked_applied"] = 1
    store.put_state(con, nid, **fields)
    if new_progress != before:
        if before in (None, "skipped") and new_progress in ("saved", "draft", "approved"):
            d = detail(con, nid, profile)
            if d:
                _calendar(con, nid, d, add_event)
        elif before == "saved" and new_progress is None and st and st["calendar_id"]:
            if remove_event is not None:
                try:
                    remove_event(st["calendar_id"])
                except Exception:                 # noqa: BLE001 — 이미 지운 일정이면 그만
                    pass
            store.put_state(con, nid, calendar_id=None)
    store.touch(con)


def history(con: sqlite3.Connection) -> dict:
    """이력 탭 — 학기별 담음 N · 지원 M · 선정 K + 상태별 목록 (F12-R43). 관심 없음도 여기서 되돌린다."""
    out: dict[str, dict] = {}
    rows = con.execute("SELECT * FROM user_state WHERE progress IS NOT NULL ORDER BY progress_at DESC").fetchall()
    for st in rows:
        at = to_date(st["applied_at"] or st["saved_at"] or st["progress_at"]) or date.today()
        sem = semester_of(at)
        g = out.setdefault(sem, {"semester": sem, "saved": 0, "applied": 0, "selected": 0, "items": []})
        if st["progress"] in ACTIVE:
            g["saved"] += 1
        if st["progress"] in ("applied", "selected", "not_selected"):
            g["applied"] += 1
        if st["progress"] == "selected":
            g["selected"] += 1
        row = store.notice(con, st["notice_id"])
        info = store.loads(row["info"], {}) if row else {}
        g["items"].append({"id": st["notice_id"], "title": _title(con, st["notice_id"]), "progress": st["progress"],
                           "progressLabel": PROGRESS_LABEL[st["progress"]], "at": st["progress_at"], "note": st["note"],
                           "categoryLabel": (info or {}).get("categoryLabel"), "url": row["url"] if row else None})
    return {"semesters": sorted(out.values(), key=lambda g: g["semester"], reverse=True)}


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
                      "boardLabel": disc.get("boardLabel") if disc else None, "categoryLabel": None}
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


# ── 초안 재료 (프로필과 따로 — 별도 삭제 가능. 비어 있으면 장학 초안 재료·프로필 초안 재료를 불러온다) ──

MATERIAL_KEYS = ("careerGoal", "activities", "skills", "highlights")
Fallback = Callable[[], Optional[dict]]


def saved_basic(con: sqlite3.Connection) -> dict:
    """저장한 기본 정보(이름·학번·소속·학년·연락처·이메일) — 장학(F11)이 비어 있을 때 빌려 간다."""
    return basicinfo.clean((store.loads(store.get_meta(con, "materials"), None) or {}).get("basic"))


def materials(con: sqlite3.Connection, profile: Optional[dict] = None, fallback: Optional[Fallback] = None,
              other_basic: Optional[Fallback] = None) -> dict:
    """초안 재료 — 기본 정보(basic) + 진로·활동·보유 역량·강조점. 비어 있으면 장학 초안 재료(fallback)·프로필 초안 재료를 불러온다.
    기본 정보의 빈 칸은 장학 재료의 기본 정보(other_basic) → 프로필 소속·학년으로 (F11 basicinfo.resolve)."""
    m = store.loads(store.get_meta(con, "materials"), None)
    own = basicinfo.clean((m or {}).get("basic"))
    other = None
    if other_basic and not all(own.values()):
        try:
            other = other_basic()
        except Exception:                        # noqa: BLE001 — 장학 쪽을 못 읽어도 재료 카드는 뜬다
            other = None
    basic, basic_from = basicinfo.resolve(own, profile, other, "scholarship")
    extra = {"basic": basic, "basicFrom": basic_from}
    if m is not None:
        return {"exists": True, **{k: m.get(k, "") for k in MATERIAL_KEYS}, **extra, "updatedAt": m.get("updatedAt"), "from": None}
    shared = None
    try:
        shared = fallback() if fallback else None
    except Exception:                            # noqa: BLE001 — 장학 쪽을 못 읽어도 재료 카드는 뜬다
        shared = None
    if shared and any((shared.get(k) or "").strip() for k in ("careerGoal", "activities", "highlights")):
        return {"exists": False, **{k: shared.get(k, "") or "" for k in MATERIAL_KEYS}, **extra, "updatedAt": None,
                "from": "scholarship"}
    dc = (profile or {}).get("draftContext") or {}
    return {"exists": False, **{k: dc.get(k, "") or "" for k in MATERIAL_KEYS}, **extra, "updatedAt": None,
            "from": "profile" if dc else None}


def put_materials(con: sqlite3.Connection, body: dict, profile: Optional[dict] = None,
                  other_basic: Optional[Fallback] = None) -> dict:
    """basic 을 보내지 않으면(예전 화면) 저장해 둔 기본 정보를 그대로 둔다."""
    data: dict = {k: str(body.get(k) or "").strip()[:2000] for k in MATERIAL_KEYS}
    data["basic"] = basicinfo.clean(body["basic"]) if body.get("basic") is not None else saved_basic(con)
    data["updatedAt"] = store.now_iso()
    store.set_meta(con, "materials", json.dumps(data, ensure_ascii=False))
    return materials(con, profile, other_basic=other_basic)


def delete_materials(con: sqlite3.Connection) -> None:
    store.set_meta(con, "materials", None)


# ── 초안 ────────────────────────────────────────────────────

def make_draft(con: sqlite3.Connection, nid: str, profile: Optional[dict], borrow_from: Optional[str] = None,
               llm: Optional[Callable] = None, add_event: Optional[AddEvent] = None,
               other_basic: Optional[Fallback] = None) -> dict:
    """초안 만들기 — 재료가 아직 없으면 화면이 먼저 재료 카드를 띄운다(api 가 409). 담지 않은 공지면 초안 대기로 담는다."""
    d = detail(con, nid, profile)
    if d is None:
        raise NotFound(nid)
    mats = materials(con, profile, other_basic=other_basic)
    borrowed = None
    if borrow_from:
        src = store.draft(con, borrow_from)
        if src is None:
            raise Invalid("가져올 초안이 없습니다")
        borrowed = {"from": borrow_from, "title": _title(con, borrow_from), "body": src["body"]}
    body, by = drafting.build(d, profile or {}, mats, borrowed=borrowed, llm=llm)
    store.save_draft(con, nid, body, generated_by=by, source_hash=store.notice(con, nid)["content_hash"],
                     borrowed=[{"from": borrowed["from"], "title": borrowed["title"]}] if borrowed else [])
    if d["progress"] in (None, "saved", "skipped"):
        patch(con, nid, {"progress": "draft"}, profile, add_event=add_event)
    store.touch(con)
    return detail(con, nid, profile)        # type: ignore[return-value]


def save_draft_body(con: sqlite3.Connection, nid: str, body: str) -> None:
    if store.draft(con, nid) is None:
        raise NotFound(nid)
    store.save_draft(con, nid, body[:30000])


# ── 캘린더·할 일 (C1 — 백엔드가 add_event 로 넘겨준다) ─────────────

def add_calendar(con: sqlite3.Connection, nid: str, profile: Optional[dict], add_event: AddEvent) -> dict:
    d = detail(con, nid, profile)
    if d is None:
        raise NotFound(nid)
    if not d["deadline"]:
        raise Invalid("신청 마감을 읽지 못해 캘린더에 넣을 수 없습니다 — 원문에서 확인하세요")
    ev = _calendar(con, nid, {**d, "state": {**d["state"], "calendarId": None}}, add_event)
    store.touch(con)
    return {"event": ev}


def add_todo(con: sqlite3.Connection, nid: str, index: int, profile: Optional[dict], add_event: AddEvent) -> dict:
    """준비물·제출 서류 하나 → 할 일 (마감 하루 전 기한, F12-R42 = F11-R54 와 같은 방식)."""
    d = detail(con, nid, profile)
    if d is None:
        raise NotFound(nid)
    docs = d["documents"]
    if not 0 <= index < len(docs):
        raise Invalid("서류 번호가 맞지 않습니다")
    due = to_date(d["deadline"]) if d["deadline"] else None
    day = (due - timedelta(days=1)) if due else date.today() + timedelta(days=1)
    if day < date.today():
        day = date.today()
    ev = add_event({"title": f"{docs[index][:60]} 준비 — {d['title'][:30]}", "start": day.isoformat(), "end": None,
                    "all_day": True, "category": "etc", "memo": f"대외활동 신청 서류 · 마감 {d['deadline'] or '미정'}\n{d['url']}",
                    "is_todo": True, "origin": f"act:{nid}:doc{index}"})
    st = store.state(con, nid)
    todos = store.loads(st["todos"], {}) if st else {}
    if ev:
        todos[str(index)] = str(ev.get("id"))
        store.put_state(con, nid, todos=json.dumps(todos))
    store.touch(con)
    return {"event": ev}


# ── 타일·브리핑 ─────────────────────────────────────────────

def status_summary(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None) -> dict:
    items = evaluate(con, profile, today)
    open_ = [i for i in items if i["status"] == "open"]
    mine = [i for i in items if i["progress"] in ("saved", "draft", "approved")]
    soon = [i for i in mine if i["daysLeft"] is not None and 0 <= i["daysLeft"] <= 3]
    interests = I.from_profile(profile)
    nxt = sorted((i for i in open_ if i["grade"] == "match" and i["daysLeft"] is not None and i["daysLeft"] >= 0),
                 key=lambda x: x["daysLeft"])
    return {
        "available": True, "updatedAt": store.get_meta(con, "updated_at"), "lastOkAt": store.get_meta(con, "last_ok_at"),
        "interestsSet": I.is_set(interests), "open": len(open_),
        "match": sum(1 for i in open_ if i["grade"] == "match"), "related": sum(1 for i in open_ if i["grade"] == "related"),
        "newMatch": sum(1 for i in open_ if i["grade"] == "match" and i["isNew"]),
        "saved": sum(1 for i in items if i["saved"]), "soon": len(soon), "profileExists": bool(profile),
        "next": {"id": nxt[0]["id"], "title": nxt[0]["title"], "daysLeft": nxt[0]["daysLeft"]} if nxt else None,
    }


def brief(con: sqlite3.Connection, profile: Optional[dict], days: int = 3, today: Optional[date] = None) -> list[dict]:
    """F10 브리핑 — 담아 둔 것의 마감만 (F12-R34)."""
    return [{"id": i["id"], "title": i["title"], "daysLeft": i["daysLeft"], "progress": i["progressLabel"]}
            for i in evaluate(con, profile, today)
            if i["progress"] in ("saved", "draft", "approved") and i["daysLeft"] is not None and 0 <= i["daysLeft"] <= days]
