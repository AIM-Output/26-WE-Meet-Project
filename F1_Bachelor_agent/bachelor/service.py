"""읽기 모델 — 저장소(items + events)를 화면이 받는 학사 일정(`AcademicEvent`, 요구사항 F1 6절)으로 바꾼다.

표준 라이브러리만 쓴다 (대시보드 백엔드가 import 한다).

한 events 행 = 화면의 일정 하나. 값은 이렇게 정한다.
    제목·날짜·유형·대상 : 대표 항목 = 원천 우선순위가 가장 높은(숫자가 작은) 살아 있는 항목, 같으면 신뢰도 높은 것
    날짜                : 사용자가 '확인 필요' 카드에서 고쳐 승인했으면 그 값(user_dates)
    신뢰도              : 항목 중 최댓값, 원천 2곳 이상이 같은 날짜를 말하면 +0.03
    상태                : 숨김(사용자) > 승인(사용자) > 신뢰도 ≥ 0.80 이면 auto, 아니면 review (F1 7절)
    appliesToMe         : 읽을 때마다 프로필로 계산 (audience.py)
    onCalendar          : 캘린더(/)에 그리는가 — auto 이면서 내 해당, 또는 사용자가 승인·담기(pinned) 한 것
"""
from __future__ import annotations

import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from . import config as C
from .audience import applies_to_me
from .classify import semester_of
from .models import Audience
from .store import dumps, enabled_map, get_meta, loads, now_iso, set_meta, source_names, priority_map, touch
from .textutil import parse_iso_date

TYPE_META = {
    "registration": ("학적", "#334155"),
    "tuition": ("등록·납부", "#B45309"),
    "course_reg": ("수강신청·정정", "#4338CA"),
    "grade": ("성적", "#0F766E"),
    "exam": ("시험", "#9A3412"),
    "vacation": ("개강·방학", "#64748B"),
    "holiday": ("휴업일", "#9F1239"),
    "event": ("행사", "#7E22CE"),
    "etc": ("기타", "#475569"),
}
REMINDER_LABEL = {"d7": "D-7", "d3": "D-3", "d1": "D-1", "end1": "종료 전날", "m30": "시작 30분 전"}
CHANGED_CHIP_DAYS = 30          # '변경됨' 칩을 보여 주는 기간


# ── 날짜 표현 ───────────────────────────────────────────────

def _effective_dates(ev: sqlite3.Row, rep: sqlite3.Row, alive: list[sqlite3.Row]) -> dict:
    user = loads(ev["user_dates"]) if ev is not None else None
    if user and user.get("start_date"):
        return user
    d = {k: rep[k] for k in ("start_date", "start_time", "end_date", "end_time")}
    # 대표값(학사일정 표)에는 시각이 없고, 같은 날짜를 말한 공지에 시각이 있으면 그 시각을 쓴다 (F1-R15 '시각까지 보존')
    if not d["start_time"]:
        for i in alive:
            if i["start_date"] == d["start_date"] and i["start_time"]:
                d["start_time"] = i["start_time"]
                if i["end_time"] and (i["end_date"] or i["start_date"]) == (d["end_date"] or d["start_date"]):
                    d["end_date"], d["end_time"] = i["end_date"], i["end_time"]
                break
    return d


def to_fc(d: dict) -> tuple[Optional[str], Optional[str], bool, Optional[str]]:
    """저장 형식(마지막 날 포함) → 화면 형식 (start, end, allDay, endTime). 종일 일정의 end 는 exclusive (C1-R14).

    - 종일 하루짜리           : end = None
    - 종일 기간               : end = 마지막 날 + 1
    - 종일 기간 + 끝 시각     : 위와 같고 endTime = '16:00' (시각을 지어내지 않는다 — '10/2 16:00 마감')
    - 시각 있음               : start = 'YYYY-MM-DDTHH:MM', end = 끝 시각이 있으면 그 시각, 없으면 마지막 날 + 1 00:00
    """
    sd = parse_iso_date(d.get("start_date"))
    if sd is None:
        return None, None, True, None
    ed = parse_iso_date(d.get("end_date"))
    st, et = d.get("start_time"), d.get("end_time")
    if not st:
        end = (ed + timedelta(days=1)).isoformat() if ed and ed > sd else None
        return sd.isoformat(), end, True, et if (ed or et) else None
    start = f"{sd.isoformat()}T{st}"
    if ed or et:
        last = ed or sd
        end = f"{last.isoformat()}T{et}" if et else f"{(last + timedelta(days=1)).isoformat()}T00:00"
    else:
        end = None
    return start, end, False, None


def _before_fc(prev: Optional[dict]) -> Optional[dict]:
    if not prev:
        return None
    s, e, all_day, et = to_fc(prev)
    return {"start": s, "end": e, "allDay": all_day, "endTime": et}


# ── 알림 시점 ───────────────────────────────────────────────

def reminder_options(type_: str, d: dict, overrides: Optional[dict]) -> list[dict]:
    """이 일정에 걸 수 있는 알림 시점과 켜짐 여부. 기간형이 아니면 end1, 시각이 없으면 m30 은 없다."""
    if not d.get("start_date"):
        return []
    period = bool(d.get("end_date") and d["end_date"] > d["start_date"])
    defaults = set(C.DEFAULT_REMINDERS.get(type_, ("d7", "d3", "d1")))
    ov = {k: v for k, v in (overrides or {}).items() if not k.startswith("_")}
    set_at = (overrides or {}).get("_at")
    out = []
    for code in C.REMINDER_CODES:
        if code == "end1" and not period:
            continue
        if code == "m30" and not d.get("start_time"):
            continue
        opt = {"code": code, "label": REMINDER_LABEL[code], "enabled": bool(ov.get(code, code in defaults))}
        if code in ov and set_at:
            opt["setAt"] = set_at
        if code in ("d7", "d3", "d1"):
            opt.update(offsetDays=int(code[1:]), anchor="start")
        elif code == "end1":
            opt.update(offsetDays=1, anchor="end")
        else:
            opt.update(offsetMinutes=30, anchor="start")
        out.append(opt)
    return out


# ── 조립 ────────────────────────────────────────────────────

def _load(con: sqlite3.Connection, event_ids: Optional[list[str]] = None):
    if event_ids:
        q = ",".join("?" * len(event_ids))
        evs = con.execute(f"SELECT * FROM events WHERE id IN ({q})", event_ids).fetchall()
        items = con.execute(f"SELECT * FROM items WHERE event_id IN ({q})", event_ids).fetchall()
    else:
        evs = con.execute("SELECT * FROM events").fetchall()
        items = con.execute("SELECT * FROM items").fetchall()
    by_ev: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for it in items:
        by_ev[it["event_id"]].append(it)
    return evs, by_ev


def build_event(ev: sqlite3.Row, items: list[sqlite3.Row], prio: dict[str, int], names: dict[str, str],
                profile: Optional[dict], today: date, enabled: Optional[dict[str, bool]] = None,
                new_since: Optional[str] = None) -> Optional[dict]:
    # 꺼진 원천(사용자가 끔)에서 온 항목은 빼고 본다 — 다른 켜진 원천이 같은 일정을 말하면 그 원천으로 보인다
    if enabled is not None:
        items = [i for i in items if enabled.get(i["source_key"], False)]
    if not items:
        return None
    alive = [i for i in items if not i["removed_at"]]
    pool = alive or items
    rep = min(pool, key=lambda r: (prio.get(r["source_key"], 9), -r["confidence"], r["first_seen"]))
    d = _effective_dates(ev, rep, alive)
    start, end, all_day, end_time = to_fc(d)

    conf = max(i["confidence"] for i in pool)
    if len({i["source_key"] for i in alive if i["start_date"] == rep["start_date"]}) >= 2:
        conf = min(0.97, conf + 0.03)
    flags = set()
    for i in pool:
        flags.update(loads(i["flags"], []))
    needs_ocr = d.get("start_date") is None

    if ev["user_status"] == "hidden":
        status = "hidden"
    elif ev["user_status"] == "approved":
        status = "approved"
    elif conf >= C.AUTO_THRESHOLD and not needs_ocr:
        status = "auto"
    else:
        status = "review"

    aud = Audience.from_dict(loads(rep["audience"], {}))
    applies = applies_to_me(aud, profile)
    pinned = bool(ev["pinned"])
    on_calendar = start is not None and status != "hidden" and (
        status == "approved" or pinned or (status == "auto" and applies is True))

    changed = None
    if ev["changed_at"]:
        try:
            recent = datetime.fromisoformat(ev["changed_at"]) >= datetime.now() - timedelta(days=CHANGED_CHIP_DAYS)
        except ValueError:
            recent = False
        if recent:
            changed = {"at": ev["changed_at"], "before": _before_fc(loads(ev["changed_before"]))}

    sources, evidence = [], []
    for i in sorted(pool, key=lambda r: (prio.get(r["source_key"], 9), r["first_seen"])):
        sources.append({"key": i["source_key"], "name": names.get(i["source_key"], i["source_key"]), "url": i["url"],
                        "postedAt": i["posted_at"], "fetchedAt": i["last_seen"], "removed": bool(i["removed_at"])})
        for e in loads(i["evidence"], []):
            if e.get("quote") and all(x["quote"] != e["quote"] for x in evidence):
                evidence.append({"field": e.get("field", "start"), "quote": e["quote"],
                                 "source": names.get(i["source_key"], i["source_key"])})

    label, color = TYPE_META.get(rep["type"], TYPE_META["etc"])
    return {
        "id": ev["id"],
        "title": rep["title"],
        "start": start, "end": end, "allDay": all_day, "endTime": end_time,
        "type": rep["type"], "typeLabel": label, "color": color,
        "sources": sources,
        "evidence": evidence,
        "confidence": round(conf, 2),
        "weak": conf < C.WEAK_THRESHOLD,
        "needsOcr": needs_ocr,
        "audience": aud.to_dict(),
        "appliesToMe": applies,
        "status": status,
        "onCalendar": on_calendar,
        "pinned": pinned,
        "changed": changed,
        "removed": not alive,
        "userEdited": bool(loads(ev["user_dates"])),
        "reminders": reminder_options(rep["type"], d, loads(ev["reminders"])),
        "memo": ev["memo"] or "",
        "actionUrl": rep["action_url"], "actionLabel": rep["action_label"],
        "semester": rep["semester"] or semester_of(rep["title"], parse_iso_date(d.get("start_date"))),
        "flags": sorted(flags),
        "firstSeen": ev["first_seen"],
        # 마지막 수집에서 처음 찾은 일정 (대시보드 '신규 일정 N건', 목록의 '신규' 칩)
        "isNew": bool(new_since) and ev["first_seen"] >= new_since,
        "notifySince": max(ev["first_seen"], ev["notify_since"] or ""),
    }


def last_day(e: dict) -> Optional[date]:
    """마지막 날(포함) — 화면의 lastDay(lib/academic.ts)와 같은 규칙. 종일 끝은 exclusive, '다음 날 00:00' 끝은 그 전날."""
    if not e["start"]:
        return None
    s = date.fromisoformat(e["start"][:10])
    if not e["end"]:
        return s
    end = date.fromisoformat(e["end"][:10])
    if e["allDay"] or (e["end"][11:16] == "00:00" and end > s):
        return end - timedelta(days=1)
    return end


def review_count(items: list[dict], today: date) -> int:
    """대시보드 '확인 필요 N건' = /academic 확인 필요 탭 — 학기와 상관없이 아직 끝나지 않은 것(날짜 미확인 포함)."""
    return sum(1 for e in items if e["status"] == "review" and (last_day(e) is None or last_day(e) >= today))


def _after(ts: Optional[str]) -> Optional[str]:
    """ts 1초 뒤 — '이 시각까지 본 것'을 신규에서 빼는 경계."""
    try:
        return (datetime.fromisoformat(ts) + timedelta(seconds=1)).isoformat(timespec="seconds") if ts else None
    except ValueError:
        return None


def ack_new(con: sqlite3.Connection) -> None:
    """'전체 확인' — 지금까지의 신규를 본 것으로. 목록 위 신규 묶음에서 빠져 날짜순 목록으로 돌아가고 대시보드 '신규 일정'도 0."""
    set_meta(con, "new_ack_at", now_iso())
    touch(con)


def list_events(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None,
                event_ids: Optional[list[str]] = None) -> list[dict]:
    today = today or date.today()
    prio, names, enabled = priority_map(con), source_names(con), enabled_map(con)
    # 신규 = 마지막 수집 시작 뒤 처음 본 것. 사용자가 '전체 확인'을 누른 시각(new_ack_at)까지 본 것은 빼고 날짜순 목록으로
    new_since = max(filter(None, (get_meta(con, "last_run_started"), _after(get_meta(con, "new_ack_at")))), default=None)
    evs, by_ev = _load(con, event_ids)
    out = [x for ev in evs
           if (x := build_event(ev, by_ev.get(ev["id"], []), prio, names, profile, today, enabled, new_since))]
    out.sort(key=lambda e: (e["start"] is None, e["start"] or "", e["title"]))
    return out


def get_event(con: sqlite3.Connection, event_id: str, profile: Optional[dict]) -> Optional[dict]:
    got = list_events(con, profile, event_ids=[event_id])
    return got[0] if got else None


def current_semester(today: Optional[date] = None) -> str:
    return semester_of("", today or date.today())


def overview(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None) -> dict:
    """GET /api/academic/events — 학기 목록 + 전체 일정. 탭 전환은 화면에서 거른다(재요청 없음, Frontend-Route 6-9)."""
    today = today or date.today()
    items = list_events(con, profile, today)
    cur = current_semester(today)
    sems = sorted({e["semester"] for e in items if e["semester"]} | {cur}, reverse=True)
    return {"semesters": sems, "currentSemester": cur, "updatedAt": get_meta(con, "updated_at"),
            "profileMissing": not profile, "items": items}


LONG_PERIOD_DAYS = 14          # 이보다 긴 종일 기간은 캘린더에 시작·마감 두 점으로만 그린다


def calendar_events(con: sqlite3.Connection, profile: Optional[dict], start: Optional[str] = None,
                    end: Optional[str] = None) -> list[dict]:
    """캘린더(/api/events)에 섞어 보낼 학사 일정 — FullCalendar 형식, extendedProps.kind = 'academic' (C1 3절).

    기간형은 가로 막대로 그린다(F1-S01). 단, '휴학 신청 8/18~10/28' 처럼 두 주를 넘는 신청 기간은 막대가 모든 주를
    덮어 다른 일정을 '+N개'로 밀어내므로 **시작일·마감일 두 점**으로 나눠 보낸다. id 는 '<id>#start'·'<id>#end',
    extendedProps.refId 가 원래 일정 id (클릭하면 같은 상세가 열린다).
    """
    out = []
    for e in list_events(con, profile):
        if not e["onCalendar"]:
            continue
        s, last = e["start"][:10], (e["end"] or e["start"])[:10]
        if (end and s > end) or (start and last < start):
            continue
        props = {
            "kind": "academic", "refId": e["id"], "type": e["type"], "typeLabel": e["typeLabel"], "color": e["color"],
            "appliesToMe": e["appliesToMe"], "status": e["status"], "changed": bool(e["changed"]),
            "endTime": e["endTime"], "source": e["sources"][0]["name"] if e["sources"] else "",
            "reminders": [r for r in e["reminders"] if r["enabled"]], "marker": None,
        }
        base = {"title": e["title"], "allDay": e["allDay"], "editable": False}
        sd, ed = parse_iso_date(e["start"]), parse_iso_date(e["end"])
        if e["allDay"] and sd and ed and (ed - sd).days > LONG_PERIOD_DAYS:
            last_day = ed - timedelta(days=1)
            out.append({**base, "id": f"{e['id']}#start", "title": f"{e['title']} 시작", "start": e["start"], "end": None,
                        "extendedProps": {**props, "marker": "start"}})
            out.append({**base, "id": f"{e['id']}#end", "title": f"{e['title']} 마감", "start": last_day.isoformat(),
                        "end": None, "extendedProps": {**props, "marker": "end"}})
            continue
        out.append({**base, "id": e["id"], "start": e["start"], "end": e["end"], "extendedProps": props})
    return out


# ── 쓰기 (사용자 값만) ──────────────────────────────────────

class NotFound(LookupError):
    pass


class Invalid(ValueError):
    pass


def update_event(con: sqlite3.Connection, event_id: str, patch: dict) -> None:
    """PATCH /api/academic/events/{id}.

    status: 'approved'(확인 필요 → 캘린더에 등록, start/end 로 날짜를 고칠 수 있음) · 'hidden'(숨김/필요 없음) · 'restore'(숨김 해제)
    memo · pinned(해당 없음이어도 내 캘린더에 담기, F1-R25) · reminders({code: bool})
    원천 값(제목·날짜)은 바꾸지 않는다 (D6) — 확인 필요 항목을 승인할 때의 날짜 수정만 user_dates 로 따로 둔다.
    """
    ev = con.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
    if ev is None:
        raise NotFound(event_id)
    sets: dict[str, object] = {}
    now = now_iso()
    status = patch.get("status")
    if status in ("approved", "restore") or patch.get("pinned"):
        sets["notify_since"] = now      # 지금부터 보이기 시작한 일정 — 이미 지난 알림을 '놓친 알림'으로 쏟아내지 않는다
    if status == "approved":
        sets["user_status"] = "approved"
        dates = patch.get("dates")
        if dates:
            if not dates.get("start_date"):
                raise Invalid("시작 날짜가 필요합니다")
            if dates.get("end_date") and dates["end_date"] < dates["start_date"]:
                raise Invalid("종료가 시작보다 빠릅니다")
            sets["user_dates"] = dumps(dates)
        else:
            rep = con.execute("SELECT start_date FROM items WHERE event_id = ? ORDER BY start_date IS NULL LIMIT 1",
                              (event_id,)).fetchone()
            if (rep is None or rep["start_date"] is None) and not loads(ev["user_dates"]):
                raise Invalid("날짜를 읽지 못한 항목입니다 — 시작 날짜를 입력해 주세요")
    elif status == "hidden":
        sets["user_status"] = "hidden"
    elif status == "restore":
        sets["user_status"] = None
    elif status is not None:
        raise Invalid(f"알 수 없는 status: {status}")
    if "memo" in patch:
        sets["memo"] = (patch["memo"] or "")[:2000]
    if "pinned" in patch:
        sets["pinned"] = int(bool(patch["pinned"]))
    if patch.get("reminders") is not None:
        cur = loads(ev["reminders"], {}) or {}
        for code, on in patch["reminders"].items():
            if code not in C.REMINDER_CODES:
                raise Invalid(f"알 수 없는 알림 코드: {code}")
            cur[code] = bool(on)
        cur["_at"] = now                # 켠 시점 — 그보다 앞선 알림은 만들지 않는다
        sets["reminders"] = dumps(cur)
    if not sets:
        return
    sets["updated_at"] = now
    con.execute(f"UPDATE events SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), event_id))
    touch(con)


# ── 설정 ────────────────────────────────────────────────────

def get_settings(con: sqlite3.Connection) -> dict:
    return {"alertTime": get_meta(con, "alert_time", C.ALERT_TIME),
            "defaults": {k: list(v) for k, v in C.DEFAULT_REMINDERS.items()}}


def set_settings(con: sqlite3.Connection, alert_time: Optional[str]) -> dict:
    if alert_time is not None:
        try:
            datetime.strptime(alert_time, "%H:%M")
        except ValueError as e:
            raise Invalid("알림 시각은 HH:MM 형식입니다") from e
        set_meta(con, "alert_time", alert_time)
    return get_settings(con)
