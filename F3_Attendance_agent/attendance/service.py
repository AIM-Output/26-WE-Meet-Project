"""화면이 받는 모양과 사용자 조작 — 학기 · 과목 · 회차 · 출결 · 시간표 · 경고 알림. 표준 라이브러리만.

흐름 (Frontend-Route 8-1)
    과목 목록(e클래스) → 시간표(자동 수집·직접 입력) → 회차(학사일정 기준으로 매번 계산) → 출결 기록 → 집계·상태 → 경고
    회차·집계는 저장하지 않고 부를 때마다 만든다(7과목 × 30회차 = 수 ms). 저장하는 것은 store.py 머리 주석.

경고 (F3-R33) — 과목마다 '마지막으로 알린 단계'(alert_level)를 두고, 상태가 그보다 올라간 순간에만 한 번 알린다.
    내려가면(잘못 찍은 결석을 고침) 기준도 같이 내린다. 눌렀다 되돌리기를 반복해도 10분 안의 같은 단계는 다시 알리지 않는다.
    알림은 notify 콜백으로 대시보드 알림 센터(F1 notifications 표)에 넣고, 응답의 alerts 로 토스트도 띄운다(F3-S09).
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from . import academic_calendar as AC
from . import calc, notices, store
from . import config as C
from . import sessions as S
from . import timetable as T
from .store import dumps, loads, now_iso

Notify = Callable[[dict], None]

# 사용자가 적는 칸 = 출석 · 결석 · 지각 · 공결 + 휴강(state) (2026-09-29 수정 ② — 조퇴는 없다)
ATTENDANCE = ("present", "absent", "late", "excused")
ATTENDANCE_LABEL = {"present": "출석", "absent": "결석", "late": "지각", "excused": "공결", None: "미입력"}
_SID = re.compile(r"^cl:(?P<cid>.+):(?P<date>\d{4}-\d{2}-\d{2})(?::mk)?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class Invalid(ValueError):
    pass


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


def _date(v: Any, label: str) -> str:
    if not isinstance(v, str) or not _DATE.match(v):
        raise Invalid(f"{label} 날짜 형식이 잘못됐습니다: {v!r} (YYYY-MM-DD)")
    try:
        date.fromisoformat(v)
    except ValueError as e:
        raise Invalid(f"{label} 날짜가 없는 날입니다: {v}") from e
    return v


# ── 학기 ────────────────────────────────────────────────────

def resolve_semester(con: sqlite3.Connection, cal: dict, sid: str) -> dict:
    """학기 범위·휴업일·학교 보강일. 내가 고친 값 > 학사일정(F1) > 없음(직접 입력 요청)."""
    row = con.execute("SELECT * FROM semesters WHERE id = ?", (sid,)).fetchone()
    auto = cal["semesters"].get(sid, {})
    start = (row["user_start"] if row else None) or auto.get("start")
    end = (row["user_end"] if row else None) or auto.get("end")
    holidays: list[dict] = []
    makeup_days: list[dict] = []
    warnings: list[str] = []
    if not start or not end:
        warnings.append("학사일정에서 개강·종강을 찾지 못했습니다 — 직접 입력해 주세요")
    else:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
        merged: dict[str, dict] = {d: {"date": d, "name": n, "source": "fixed"} for d, n in AC.fixed_holidays(s, e).items()}
        for d, n in cal["holidays"].items():
            if start <= d <= end:
                merged[d] = {"date": d, "name": n, "source": "academic"}
        for h in loads(row["holidays"], []) if row else []:
            if start <= h["date"] <= end:
                merged[h["date"]] = {"date": h["date"], "name": h.get("name") or "휴업일", "source": "user"}
        holidays = sorted(merged.values(), key=lambda x: x["date"])
        makeup_days = [m for m in cal["makeups"] if start <= m["date"] <= end]
        if not cal["available"]:
            warnings.append("학사일정(F1)을 읽지 못해 휴업일이 반영되지 않았을 수 있습니다 — 양력 고정 공휴일만 뺐습니다")
    return {
        "id": sid, "label": AC.semester_label(sid), "start": start, "end": end,
        "startSource": ("user" if row and row["user_start"] else "academic") if start else None,
        "endSource": ("user" if row and row["user_end"] else "academic") if end else None,
        "auto": {"start": auto.get("start"), "end": auto.get("end")},
        "holidays": holidays, "makeupDays": makeup_days,
        "userHolidays": loads(row["holidays"], []) if row else [],
        "academicAvailable": cal["available"], "warnings": warnings,
    }


def semester_ids(con: sqlite3.Connection, cal: dict) -> list[str]:
    ids = {k for k, v in cal["semesters"].items() if v.get("start")}
    ids |= {r["id"] for r in con.execute("SELECT id FROM semesters")}
    ids |= {r["semester"] for r in con.execute("SELECT DISTINCT semester FROM courses")}
    return sorted(ids, reverse=True)


def current_semester(con: sqlite3.Connection, cal: dict, today: date) -> str:
    """오늘이 속한 학기(개강 2주 전 ~ 종강 3주 뒤). 방학이면 가장 최근에 시작한 학기. 학사일정이 없으면 달로 추정."""
    best: Optional[tuple[str, str]] = None
    t = today.isoformat()
    for sid in semester_ids(con, cal):
        sem = resolve_semester(con, cal, sid)
        if not sem["start"] or not sem["end"]:
            continue
        lo = (date.fromisoformat(sem["start"]) - timedelta(days=14)).isoformat()
        hi = (date.fromisoformat(sem["end"]) + timedelta(days=21)).isoformat()
        if lo <= t <= hi:
            return sid
        if sem["start"] <= t and (best is None or sem["start"] > best[1]):
            best = (sid, sem["start"])
    return best[0] if best else AC.semester_of(today)


def set_semester(con: sqlite3.Connection, sid: str, body: dict) -> None:
    """개강·종강·휴업일 직접 입력 (F3-R11, 9절). null 이면 학사일정 값으로 돌아간다."""
    if not re.match(r"^\d{4}-(1|2|S|W)$", sid or ""):
        raise Invalid(f"학기 형식이 잘못됐습니다: {sid!r} (예: 2026-2)")
    row = con.execute("SELECT * FROM semesters WHERE id = ?", (sid,)).fetchone()
    start = row["user_start"] if row else None
    end = row["user_end"] if row else None
    hol = loads(row["holidays"], []) if row else []
    if "start" in body:
        start = _date(body["start"], "개강") if body["start"] else None
    if "end" in body:
        end = _date(body["end"], "종강") if body["end"] else None
    if start and end and end <= start:
        raise Invalid("종강이 개강보다 빠릅니다")
    if "holidays" in body:
        hol = []
        for h in body["holidays"] or []:
            if not isinstance(h, dict):
                raise Invalid("휴업일은 {date, name} 입니다")
            hol.append({"date": _date(h.get("date"), "휴업일"), "name": str(h.get("name") or "휴업일").strip()[:40]})
    con.execute("INSERT INTO semesters(id, user_start, user_end, holidays, updated_at) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET user_start = excluded.user_start, user_end = excluded.user_end, "
                "holidays = excluded.holidays, updated_at = excluded.updated_at",
                (sid, start, end, dumps(hol), now_iso()))
    store.touch(con)


# ── 교시 시각 ────────────────────────────────────────────────

def period_map(con: sqlite3.Connection) -> S.PeriodMap:
    pm = S.default_period_map()
    user = loads(store.get_meta(con, "period_map"), {}) or {}
    for mod in ("mwf", "tt"):
        for p, se in (user.get(mod) or {}).items():
            pm[mod][int(p)] = (se[0], se[1])
    return pm


def period_view(con: sqlite3.Connection) -> dict:
    pm = period_map(con)
    user = loads(store.get_meta(con, "period_map"), {}) or {}
    return {"mwf": {str(k): list(v) for k, v in sorted(pm["mwf"].items())},
            "tt": {str(k): list(v) for k, v in sorted(pm["tt"].items())},
            "edited": bool(user), "source": C.PERIOD_SOURCE, "sourceUrl": C.PERIOD_SOURCE_URL,
            "weekdayModule": {C.WEEKDAYS[k]: v for k, v in C.WEEKDAY_MODULE.items()}}


def set_period_map(con: sqlite3.Connection, body: Optional[dict]) -> dict:
    """교시 ↔ 시각 고치기 (C1-R05a — 학교가 교시 시각을 바꾸면 이 표만). None 이면 학교 기본값으로."""
    if not body:
        store.set_meta(con, "period_map", None)
        store.touch(con)
        return period_view(con)
    base = S.default_period_map()
    diff: dict[str, dict[str, list[str]]] = {}
    for mod in ("mwf", "tt"):
        for p, se in (body.get(mod) or {}).items():
            pi = int(p)
            if pi not in base[mod] or not isinstance(se, (list, tuple)) or len(se) != 2:
                raise Invalid(f"{mod} {p}교시 값이 이상합니다")
            s, e = str(se[0]), str(se[1])
            if not (_HHMM.match(s) and _HHMM.match(e)) or e <= s:
                raise Invalid(f"{p}교시 시각이 이상합니다: {s}~{e}")
            if (s, e) != base[mod][pi]:
                diff.setdefault(mod, {})[str(pi)] = [s, e]
    store.set_meta(con, "period_map", dumps(diff) if diff else None)
    store.touch(con)
    return period_view(con)


# ── 과목 ────────────────────────────────────────────────────

def sync_courses(con: sqlite3.Connection, sid: str, eclass: list[dict]) -> int:
    """e클래스 과목 목록을 이번 학기 과목으로 (F3-R01). 이름·분반이 바뀌면 id 로 찾아 이름만 고친다(9절). 설정은 건드리지 않는다."""
    added = 0
    for i, c in enumerate(eclass):
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        name, short = c.get("name") or "", c.get("short") or c.get("name") or ""
        code, section, color = (c.get("code") or "").upper(), str(c.get("section") or ""), c.get("color")
        row = con.execute("SELECT * FROM courses WHERE semester = ? AND id = ?", (sid, cid)).fetchone()
        if row is None:
            con.execute("INSERT INTO courses(semester, id, name, short, code, section, source, color, seq, created_at, "
                        "updated_at) VALUES (?, ?, ?, ?, ?, ?, 'eclass', ?, ?, ?, ?)",
                        (sid, cid, name, short, code, section, color, i, now_iso(), now_iso()))
            added += 1
        elif (row["name"], row["short"], row["code"], row["section"], row["color"], row["seq"]) != \
                (name, short, code, section, color, i):
            con.execute("UPDATE courses SET name = ?, short = ?, code = ?, section = ?, color = ?, seq = ?, "
                        "updated_at = ? WHERE semester = ? AND id = ?",
                        (name, short, code, section, color, i, now_iso(), sid, cid))
    if added:
        store.touch(con)
    return added


def _course_row(con: sqlite3.Connection, sid: str, cid: str) -> sqlite3.Row:
    row = con.execute("SELECT * FROM courses WHERE semester = ? AND id = ?", (sid, cid)).fetchone()
    if row is None:
        raise NotFound("과목이 없습니다")
    return row


def _settings(row: sqlite3.Row) -> dict:
    return {
        "limitRatio": row["limit_ratio"] if row["limit_ratio"] is not None else C.DEFAULT_LIMIT_RATIO,
        "lateToAbsence": row["late_to_absence"] if row["late_to_absence"] is not None else C.DEFAULT_LATE_TO_ABSENCE,
    }


def _versions(con: sqlite3.Connection, sid: str, cid: str) -> list[dict]:
    return [{"validFrom": r["valid_from"], "meetings": loads(r["data"], []), "filledBy": r["filled_by"],
             "updatedAt": r["updated_at"]}
            for r in con.execute("SELECT * FROM meetings WHERE semester = ? AND course_id = ? ORDER BY valid_from",
                                 (sid, cid))]


def _marks(con: sqlite3.Connection, sid: str, cid: str) -> dict[str, dict]:
    return {r["id"]: dict(r) for r in con.execute("SELECT * FROM marks WHERE semester = ? AND course_id = ?", (sid, cid))}


def _user_makeups(con: sqlite3.Connection, sid: str, cid: str) -> list[dict]:
    return [{"id": r["id"], "date": r["date"], "periods": loads(r["periods"], []), "memo": r["memo"]}
            for r in con.execute("SELECT * FROM makeups WHERE semester = ? AND course_id = ? ORDER BY date", (sid, cid))]


def build_course(con: sqlite3.Connection, row: sqlite3.Row, sem: dict, pmap: S.PeriodMap,
                 now: datetime) -> dict:
    """과목 하나의 화면 모양 — 설정 · 시간표 · 회차 · 집계."""
    sid, cid = row["semester"], row["id"]
    versions = _versions(con, sid, cid)
    sessions: list[dict] = []
    orphans: list[dict] = []
    note = notices.load()["byCourse"].get(cid) or {"cancels": {}, "hints": []}
    if sem["start"] and sem["end"] and versions:
        sessions, orphans = S.build(
            cid, versions, date.fromisoformat(sem["start"]), date.fromisoformat(sem["end"]),
            holidays={h["date"]: h["name"] for h in sem["holidays"]}, school_makeups=sem["makeupDays"],
            user_makeups=_user_makeups(con, sid, cid), marks=_marks(con, sid, cid),
            notice_cancels=note["cancels"], pmap=pmap)
    # 공지에서 휴강을 찾았지만 걸 회차가 없는 것(날짜 못 찾음 · 그날 수업 없음)은 화면에 '확인 필요'로 링크만
    days = {s["date"] for s in sessions if s["kind"] == "regular"}
    hints = list(note["hints"])
    if sem["start"] and sem["end"]:
        hints += [{**v, "date": d, "why": f"공지의 휴강 날짜({int(d[5:7])}/{int(d[8:])})가 이 과목 수업일이 아닙니다"}
                  for d, v in sorted(note["cancels"].items()) if sem["start"] <= d <= sem["end"] and d not in days
                  and not _whole_week(note["cancels"], v)]
    for s in sessions:
        s["started"] = calc.started(s, now)
        s["ended"] = calc.ended(s, now)
    settings = _settings(row)
    adjust = {"absent": row["adjust_absent"], "late": row["adjust_late"]}
    summary = calc.summarize(sessions, settings, adjust, now)
    cur = versions[-1] if versions else None
    auto = loads(row["tt_auto"], None)
    return {
        "id": cid, "semester": sid, "name": row["name"], "short": row["short"], "code": row["code"],
        "section": row["section"], "color": row["color"], "source": row["source"], "excluded": bool(row["excluded"]),
        "settings": settings, "adjust": adjust,
        "timetable": {
            "meetings": cur["meetings"] if cur else [],
            "text": T.meetings_text(cur["meetings"]) if cur else "",
            "filledBy": ("user" if len(versions) > 1 else cur["filledBy"]) if cur else None,
            "versions": [{**v, "text": T.meetings_text(v["meetings"])} for v in versions],
            "status": row["tt_status"], "message": row["tt_message"], "raw": loads(row["tt_raw"], None),
            "auto": auto, "autoText": T.meetings_text(auto) if auto else "", "checkedAt": row["tt_checked_at"],
        },
        "summary": summary, "sessions": sessions, "orphans": orphans, "alertLevel": row["alert_level"],
        "noticeHints": hints,
    }


def _whole_week(cancels: dict[str, dict], v: dict) -> bool:
    """'이번 주 휴강'처럼 한 공지가 여러 날을 덮으면 수업 없는 날은 알릴 필요가 없다."""
    return sum(1 for x in cancels.values() if x is v) > 1


def _context(con: sqlite3.Connection, sid: str, cal: Optional[dict] = None) -> tuple[dict, dict, S.PeriodMap]:
    cal = cal or AC.load()
    return cal, resolve_semester(con, cal, sid), period_map(con)


def build_semester(con: sqlite3.Connection, sid: str, now: datetime, cal: Optional[dict] = None) -> tuple[dict, list[dict]]:
    cal, sem, pmap = _context(con, sid, cal)
    rows = con.execute("SELECT * FROM courses WHERE semester = ? ORDER BY source = 'manual', seq, created_at",
                       (sid,)).fetchall()
    return sem, [build_course(con, r, sem, pmap, now) for r in rows]


def course_view(con: sqlite3.Connection, sid: str, cid: str, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    _, sem, pmap = _context(con, sid)
    return build_course(con, _course_row(con, sid, cid), sem, pmap, now)


def _totals(courses: list[dict]) -> dict:
    live = [c for c in courses if not c["excluded"]]
    risky = [c for c in live if c["summary"]["level"] in ("danger", "over")]
    caution = [c for c in live if c["summary"]["level"] == "caution"]
    worst = max((c["summary"]["level"] for c in live), key=lambda lv: calc.LEVEL_RANK[lv], default=None)
    return {
        "courses": len(live), "withTimetable": sum(1 for c in live if c["timetable"]["meetings"]),
        "needsTimetable": [c["short"] for c in live if not c["timetable"]["meetings"]],
        "unchecked": sum(c["summary"]["uncheckedSessions"] for c in live),
        "risky": [{"id": c["id"], "name": c["short"], "level": c["summary"]["level"],
                   "levelLabel": c["summary"]["levelLabel"], "remaining": c["summary"]["remaining"],
                   "spareSessions": c["summary"]["spareSessions"]}
                  for c in sorted(risky, key=lambda c: -calc.LEVEL_RANK[c["summary"]["level"]])],
        "caution": [c["short"] for c in caution],
        "worstLevel": worst, "worstLabel": calc.LEVEL_LABEL[worst],
        "sessions": sum(len(c["sessions"]) for c in live),
    }


def academic_warning(con: sqlite3.Connection, profile: Optional[dict]) -> dict:
    """직전 학기 평점과 학사경고 기준 (F3-R40). 평점은 C2 프로필의 '직전 학기 평점'을 그대로 쓴다."""
    raw = store.get_meta(con, "warning_gpa")
    threshold = float(raw) if raw else C.WARNING_GPA
    g = (profile or {}).get("lastSemesterGpa")
    out = {"threshold": threshold, "scale": C.WARNING_SCALE, "sourceUrl": C.WARNING_SOURCE_URL,
           "gpa": g, "below": None, "message": None}
    if not g or g.get("value") is None:
        out["message"] = "프로필에 직전 학기 평점을 넣으면 학사경고 기준과 비교해 드립니다"
    elif float(g.get("scale") or 4.5) != C.WARNING_SCALE:
        out["message"] = f"평점 만점이 {g.get('scale')} 이라 4.5 만점 기준({threshold})과 비교하지 않았습니다"
    else:
        out["below"] = float(g["value"]) < threshold
        out["message"] = (f"직전 학기 평점 {g['value']} — 학사경고 기준({threshold} 미만)에 해당합니다. 이번 학기 출결·성적을 특히 챙기세요"
                          if out["below"] else None)
    return out


def overview(con: sqlite3.Connection, sid: Optional[str] = None, *, profile: Optional[dict] = None,
             eclass: Optional[list[dict]] = None, now: Optional[datetime] = None,
             notify: Optional[Notify] = None) -> dict:
    """GET /api/attendance/summary — 학기 · 과목(설정·시간표·회차·집계) · 합계 · 교시 시각 · 학사경고."""
    now = now or datetime.now()
    cal = AC.load()
    cur = current_semester(con, cal, now.date())
    sid = sid or cur
    if eclass is not None and sid == cur:
        sync_courses(con, sid, eclass)
    sem, courses = build_semester(con, sid, now, cal)
    alerts = evaluate_alerts(con, courses, notify) if sid == cur else []
    options = []
    for s in semester_ids(con, cal) or [sid]:
        r = resolve_semester(con, cal, s)
        options.append({"id": s, "label": r["label"], "start": r["start"], "end": r["end"], "current": s == cur})
    if sid not in {o["id"] for o in options}:
        options.insert(0, {"id": sid, "label": sem["label"], "start": sem["start"], "end": sem["end"], "current": sid == cur})
    return {
        "semester": sem, "current": cur, "semesters": options, "courses": courses, "totals": _totals(courses),
        "periods": period_view(con), "academicWarning": academic_warning(con, profile),
        "eclassCourses": None if eclass is None else len(eclass),
        "labels": {"attendance": {k or "none": v for k, v in ATTENDANCE_LABEL.items()}, "level": {
            k or "none": v for k, v in calc.LEVEL_LABEL.items()}},
        "notices": {"available": notices.load()["available"]},
        "updatedAt": data_stamp(con), "alerts": alerts, "now": now.isoformat(timespec="minutes"),
    }


def data_stamp(con: sqlite3.Connection) -> Optional[str]:
    """화면이 다시 부를지 판단하는 도장 — 내 기록이 바뀐 시각과 e클래스 공지(자동 휴강 원천)가 바뀐 시각 중 늦은 것."""
    stamps = [x for x in (store.get_meta(con, "updated_at"), notices.load()["stamp"]) if x]
    return max(stamps) if stamps else None


# ── 경고 알림 ────────────────────────────────────────────────

def evaluate_alerts(con: sqlite3.Connection, courses: list[dict], notify: Optional[Notify],
                    now: Optional[datetime] = None) -> list[dict]:
    now = now or datetime.now()
    out = []
    for c in courses:
        level = c["summary"]["level"]
        if c["excluded"] or level is None:
            continue
        prev = c["alertLevel"]
        if calc.LEVEL_RANK[level] == calc.LEVEL_RANK[prev]:
            continue
        con.execute("UPDATE courses SET alert_level = ? WHERE semester = ? AND id = ?", (level, c["semester"], c["id"]))
        c["alertLevel"] = level
        if level == "safe" or calc.LEVEL_RANK[level] < calc.LEVEL_RANK[prev]:
            continue
        since = (now - timedelta(minutes=C.ALERT_DEDUP_MIN)).isoformat(timespec="seconds")
        dup = con.execute("SELECT 1 FROM alerts WHERE semester = ? AND course_id = ? AND level = ? AND created_at >= ?",
                          (c["semester"], c["id"], level, since)).fetchone()
        if dup:
            continue
        title, body = calc.alert_text(c["short"], level, c["summary"])
        con.execute("INSERT INTO alerts(semester, course_id, level, title, body, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                    (c["semester"], c["id"], level, title, body, now.isoformat(timespec="seconds")))
        a = {"courseId": c["id"], "name": c["short"], "level": level, "levelLabel": calc.LEVEL_LABEL[level],
             "title": title, "body": body, "href": f"/attendance?course={c['id']}",
             "refId": f"att:{c['semester']}:{c['id']}:{level}", "at": now.isoformat(timespec="seconds")}
        out.append(a)
        if notify:
            try:
                notify(a)
            except Exception:                        # noqa: BLE001 — 알림 센터가 없어도 출결 저장은 된다
                pass
    return out


def alert_history(con: sqlite3.Connection, sid: str, limit: int = 30) -> list[dict]:
    return [dict(r) for r in con.execute("SELECT * FROM alerts WHERE semester = ? ORDER BY id DESC LIMIT ?", (sid, limit))]


# ── 회차 조작 (출결 · 휴강 · 보강) ─────────────────────────────

def _locate(con: sqlite3.Connection, session_id: str, now: datetime) -> tuple[dict, dict]:
    """회차 id → (과목 화면 모양, 회차). 과목 id 에 ':' 가 있어도(mc:…) 날짜 자리로 가른다."""
    m = _SID.match(session_id or "")
    if not m:
        raise NotFound("수업 회차가 아닙니다")
    cid = m.group("cid")
    rows = con.execute("SELECT * FROM courses WHERE id = ? ORDER BY semester DESC", (cid,)).fetchall()
    cal = AC.load()
    pmap = period_map(con)
    for row in rows:
        view = build_course(con, row, resolve_semester(con, cal, row["semester"]), pmap, now)
        for s in view["sessions"]:
            if s["id"] == session_id:
                return view, s
    raise NotFound("수업 회차를 찾을 수 없습니다 — 시간표가 바뀌었을 수 있습니다")


def _put_mark(con: sqlite3.Connection, view: dict, s: dict, **fields: Any) -> None:
    cur = con.execute("SELECT * FROM marks WHERE id = ?", (s["id"],)).fetchone()
    rec = {"attendance": cur["attendance"] if cur else None, "state": cur["state"] if cur else None,
           "memo": cur["memo"] if cur else None}
    rec.update(fields)
    if not rec["attendance"] and not rec["state"] and not rec["memo"]:
        con.execute("DELETE FROM marks WHERE id = ?", (s["id"],))
        return
    con.execute("INSERT INTO marks(id, semester, course_id, date, attendance, state, memo, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET attendance = excluded.attendance, "
                "state = excluded.state, memo = excluded.memo, updated_at = excluded.updated_at",
                (s["id"], view["semester"], view["id"], s["date"], rec["attendance"], rec["state"], rec["memo"],
                 now_iso()))


def _check_attendance(s: dict, value: Optional[str], now: datetime) -> None:
    if value is None:
        return
    if value not in ATTENDANCE:
        raise Invalid(f"출결 값이 이상합니다: {value!r} (present·absent·late·excused)")
    if s["state"] != "scheduled":
        raise Invalid("휴강 회차에는 출결을 적을 수 없습니다 — 휴강을 먼저 풀어 주세요")
    if not calc.started(s, now) and value != "excused":
        raise Invalid("아직 시작하지 않은 수업입니다")


def patch_session(con: sqlite3.Connection, session_id: str, body: dict, *, now: Optional[datetime] = None,
                  notify: Optional[Notify] = None) -> dict:
    """출결 {attendance} · 휴강 처리/되돌리기 {state: canceled|scheduled} · 메모 {memo} (F3-R15·R20·R24·R25)."""
    now = now or datetime.now()
    view, s = _locate(con, session_id, now)
    fields: dict[str, Any] = {}
    if "state" in body:
        target = body["state"]
        if target not in ("canceled", "scheduled", None):
            raise Invalid("state 는 canceled(휴강) 또는 scheduled(되돌리기)입니다")
        target = target or s["baseState"]
        fields["state"] = None if target == s["baseState"] else target
        s = {**s, "state": target}
    if "attendance" in body:
        _check_attendance(s, body["attendance"], now)
        fields["attendance"] = body["attendance"]
    if "memo" in body:
        fields["memo"] = str(body["memo"] or "").strip()[:300] or None
    if not fields:
        raise Invalid("바꿀 것이 없습니다")
    _put_mark(con, view, s, **fields)
    store.touch(con)
    fresh = course_view(con, view["semester"], view["id"], now)
    alerts = evaluate_alerts(con, [fresh], notify, now)
    return {"session": next((x for x in fresh["sessions"] if x["id"] == session_id), None), "course": fresh,
            "alerts": alerts, "updatedAt": data_stamp(con)}


def bulk_attendance(con: sqlite3.Connection, items: list[dict], *, now: Optional[datetime] = None,
                    notify: Optional[Notify] = None) -> dict:
    """이번 주 몰아서 입력 · '모두 출석으로' (F3-R26). 적을 수 없는 회차(미래·휴강)는 건너뛰고 수를 알려 준다."""
    now = now or datetime.now()
    touched: dict[tuple[str, str], bool] = {}
    done, skipped = 0, []
    for it in items or []:
        try:
            view, s = _locate(con, str(it.get("id") or ""), now)
            _check_attendance(s, it.get("attendance"), now)
        except (NotFound, Invalid) as e:
            skipped.append({"id": it.get("id"), "reason": str(e)})
            continue
        _put_mark(con, view, s, attendance=it.get("attendance"))
        touched[(view["semester"], view["id"])] = True
        done += 1
    if done:
        store.touch(con)
    courses = [course_view(con, sid, cid, now) for sid, cid in touched]
    alerts = evaluate_alerts(con, courses, notify, now)
    return {"updated": done, "skipped": skipped, "courses": courses, "alerts": alerts,
            "updatedAt": data_stamp(con)}


def add_makeup(con: sqlite3.Connection, body: dict, *, semester: Optional[str] = None,
               now: Optional[datetime] = None, notify: Optional[Notify] = None) -> dict:
    """보강 회차 추가 {courseId, date, periods, memo?} (F3-R16). 총 횟수에 1회 더해지고 캘린더에도 나타난다."""
    now = now or datetime.now()
    cid = str(body.get("courseId") or "")
    day = _date(body.get("date"), "보강")
    sid = semester or _semester_for(con, cid, day, now)
    view = course_view(con, sid, cid, now)
    wd = date.fromisoformat(day).weekday()
    try:
        ms = T.normalize_meetings([{"weekday": wd, "periods": body.get("periods") or []}])
    except T.ParseError as e:
        raise Invalid(str(e)) from e
    if len(ms) != 1:
        raise Invalid("보강 교시는 이어진 교시 하나로 넣어 주세요 (떨어져 있으면 두 번 추가)")
    periods = ms[0]["periods"]
    sid_ = S.session_id(cid, day, makeup=True)
    if any(x["id"] == sid_ for x in view["sessions"]):
        raise Conflict("그 날에는 이미 보강 회차가 있습니다")
    con.execute("INSERT INTO makeups(id, semester, course_id, date, periods, memo, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (sid_, sid, cid, day, dumps(periods), str(body.get("memo") or "").strip()[:300], now_iso()))
    store.touch(con)
    fresh = course_view(con, sid, cid, now)
    return {"id": sid_, "course": fresh, "alerts": evaluate_alerts(con, [fresh], notify, now),
            "updatedAt": data_stamp(con)}


def delete_makeup(con: sqlite3.Connection, session_id: str, *, now: Optional[datetime] = None) -> dict:
    """내가 추가한 보강만 지운다. 학교 지정 보강은 '휴강'으로 바꾼다(원천이 만든 것)."""
    r = con.execute("SELECT * FROM makeups WHERE id = ?", (session_id,)).fetchone()
    if r is None:
        raise NotFound("내가 추가한 보강 회차가 아닙니다 — 학교 지정 보강은 휴강으로 표시하세요")
    con.execute("DELETE FROM makeups WHERE id = ?", (session_id,))
    con.execute("DELETE FROM marks WHERE id = ?", (session_id,))
    store.touch(con)
    return {"course": course_view(con, r["semester"], r["course_id"], now), "updatedAt": data_stamp(con)}


def _semester_for(con: sqlite3.Connection, cid: str, day: str, now: datetime) -> str:
    rows = con.execute("SELECT semester FROM courses WHERE id = ? ORDER BY semester DESC", (cid,)).fetchall()
    if not rows:
        raise NotFound("과목이 없습니다")
    if len(rows) == 1:
        return rows[0]["semester"]
    cal = AC.load()
    for r in rows:
        sem = resolve_semester(con, cal, r["semester"])
        if sem["start"] and sem["end"] and sem["start"] <= day <= sem["end"]:
            return r["semester"]
    return rows[0]["semester"]


# ── 과목 설정 · 수기 과목 ─────────────────────────────────────

def patch_course(con: sqlite3.Connection, cid: str, body: dict, *, semester: Optional[str] = None,
                 now: Optional[datetime] = None, notify: Optional[Notify] = None) -> dict:
    """한도 비율 {limitRatio} · 지각 환산 {lateToAbsence} ·
    누적 직접 조정 {adjust: {absent, late}} · 계산 제외 {excluded} · (수기 과목) {name, code, section}"""
    now = now or datetime.now()
    sid = semester or _semester_for(con, cid, now.date().isoformat(), now)
    row = _course_row(con, sid, cid)
    sets: dict[str, Any] = {}
    if "limitRatio" in body:
        v = body["limitRatio"]
        try:
            v = None if v is None else float(v)
        except (TypeError, ValueError) as e:
            raise Invalid("한도 비율은 숫자입니다") from e
        if v is not None and not 0 < v <= 0.5:
            raise Invalid("한도 비율은 0 보다 크고 1/2 이하입니다")
        sets["limit_ratio"] = v
    if "lateToAbsence" in body:
        v = body["lateToAbsence"]
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 <= v <= 10):
            raise Invalid("지각 환산은 0(환산 안 함)~10 사이 정수입니다")
        sets["late_to_absence"] = v
    if "adjust" in body:
        adj = body["adjust"] or {}
        for k, col in (("absent", "adjust_absent"), ("late", "adjust_late")):
            if k in adj:
                v = adj[k]
                if not isinstance(v, int) or isinstance(v, bool) or not -60 <= v <= 60:
                    raise Invalid("직접 조정은 -60~60 사이 정수(횟수)입니다")
                sets[col] = v
    if "excluded" in body:
        sets["excluded"] = int(bool(body["excluded"]))
    if row["source"] == "manual":
        if "name" in body:
            name = str(body["name"] or "").strip()[:80]
            if not name:
                raise Invalid("과목 이름이 비었습니다")
            sets["name"] = sets["short"] = name
        for k in ("code", "section"):
            if k in body:
                sets[k] = str(body[k] or "").strip().upper()[:20]
    elif {"name", "code", "section"} & body.keys():
        raise Invalid("e클래스 과목의 이름·학수번호·분반은 e클래스에서 온 값이라 고칠 수 없습니다")
    if not sets:
        raise Invalid("바꿀 것이 없습니다")
    cols = ", ".join(f"{k} = ?" for k in sets)
    con.execute(f"UPDATE courses SET {cols}, updated_at = ? WHERE semester = ? AND id = ?",
                (*sets.values(), now_iso(), sid, cid))
    store.touch(con)
    fresh = course_view(con, sid, cid, now)
    return {"course": fresh, "alerts": evaluate_alerts(con, [fresh], notify, now),
            "updatedAt": data_stamp(con)}


def add_manual_course(con: sqlite3.Connection, body: dict, *, semester: str, now: Optional[datetime] = None) -> dict:
    """e클래스에 없는 과목 (F3-R05) — id 는 'mc:' 접두사(요구사항 7절)."""
    name = str(body.get("name") or "").strip()[:80]
    if not name:
        raise Invalid("과목 이름을 넣어 주세요")
    code = str(body.get("code") or "").strip().upper()[:20]
    section = str(body.get("section") or "").strip()[:10]
    cid = "mc:" + hashlib.sha1(f"{semester}|{name}|{code}|{section}".encode("utf-8")).hexdigest()[:10]
    if con.execute("SELECT 1 FROM courses WHERE semester = ? AND id = ?", (semester, cid)).fetchone():
        raise Conflict("같은 과목이 이미 있습니다")
    seq = (con.execute("SELECT MAX(seq) AS m FROM courses WHERE semester = ?", (semester,)).fetchone()["m"] or 0) + 1
    con.execute("INSERT INTO courses(semester, id, name, short, code, section, source, color, seq, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 'manual', ?, ?, ?, ?)",
                (semester, cid, name, name, code, section, body.get("color") or "#64748b", seq, now_iso(), now_iso()))
    if body.get("meetings"):
        _save_version(con, semester, cid, _norm(body["meetings"]), "", "user")
    store.touch(con)
    return {"id": cid, "course": course_view(con, semester, cid, now)}


def delete_course(con: sqlite3.Connection, cid: str, *, semester: str) -> None:
    row = _course_row(con, semester, cid)
    if row["source"] != "manual":
        raise Conflict("e클래스 과목은 지울 수 없습니다 — 수강을 취소했으면 '계산에서 제외'를 쓰세요")
    for t in ("meetings", "marks", "makeups", "alerts"):
        con.execute(f"DELETE FROM {t} WHERE semester = ? AND course_id = ?", (semester, cid))
    con.execute("DELETE FROM courses WHERE semester = ? AND id = ?", (semester, cid))
    store.touch(con)


# ── 시간표 ───────────────────────────────────────────────────

def _norm(ms: Any) -> list[dict]:
    try:
        return T.normalize_meetings(ms)
    except T.ParseError as e:
        raise Invalid(str(e)) from e


def _save_version(con: sqlite3.Connection, sid: str, cid: str, meetings: list[dict], valid_from: str, by: str) -> None:
    con.execute("INSERT INTO meetings(semester, course_id, valid_from, data, filled_by, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(semester, course_id, valid_from) DO UPDATE SET data = excluded.data, "
                "filled_by = excluded.filled_by, updated_at = excluded.updated_at",
                (sid, cid, valid_from, dumps(meetings), by, now_iso()))


def _same(a: Optional[list[dict]], b: Optional[list[dict]]) -> bool:
    key = lambda ms: [(m["weekday"], tuple(m["periods"])) for m in ms or []]   # noqa: E731
    return key(a) == key(b)


def save_timetable(con: sqlite3.Connection, body: dict, *, semester: str, now: Optional[datetime] = None,
                   notify: Optional[Notify] = None) -> dict:
    """PUT /api/attendance/timetable {courses: [{courseId, meetings}], validFrom?} → 회차 재생성 결과 (Frontend-Route 8-5).

    validFrom 이 없거나 개강 이전이면 '학기 처음부터' 이 시간표(판 하나로 바꿈). 학기 중 날짜면 그날부터만 바뀐다 —
    지난 회차와 출결 기록은 그대로 둔다 (F3-R17). 회차 id 가 날짜라 교시만 바뀌면 기록이 그대로 따라가고,
    요일이 바뀌어 그날 수업이 없어지면 그 기록은 '떠 있는 기록'(orphans)으로 남는다."""
    now = now or datetime.now()
    _, sem, pmap = _context(con, semester)
    vf = body.get("validFrom") or ""
    if vf:
        vf = _date(vf, "적용 시작")
        if sem["start"] and vf <= sem["start"]:
            vf = ""
    entries = body.get("courses") or []
    if not isinstance(entries, list) or not entries:
        raise Invalid("저장할 과목이 없습니다")
    parsed = [(str(e.get("courseId") or ""), _norm(e.get("meetings") or [])) for e in entries]
    out = []
    for cid, ms in parsed:
        row = _course_row(con, semester, cid)
        versions = _versions(con, semester, cid)
        auto = loads(row["tt_auto"], None)
        if not ms:
            con.execute("DELETE FROM meetings WHERE semester = ? AND course_id = ?"
                        + (" AND valid_from >= ?" if vf else ""), (semester, cid, *([vf] if vf else [])))
        elif not vf or not versions:
            con.execute("DELETE FROM meetings WHERE semester = ? AND course_id = ?", (semester, cid))
            _save_version(con, semester, cid, ms, "", "auto" if auto and _same(ms, auto) else "user")
        else:
            con.execute("DELETE FROM meetings WHERE semester = ? AND course_id = ? AND valid_from >= ?", (semester, cid, vf))
            _save_version(con, semester, cid, ms, vf, "user")
        fresh = course_view(con, semester, cid, now)
        out.append({"courseId": cid, "name": fresh["short"], "sessions": len(fresh["sessions"]),
                    "total": fresh["summary"]["totalCount"], "orphans": len(fresh["orphans"]),
                    "text": fresh["timetable"]["text"]})
    store.touch(con)
    courses = [course_view(con, semester, cid, now) for cid, _ in parsed]
    return {"generated": out, "courses": courses, "alerts": evaluate_alerts(con, courses, notify, now),
            "updatedAt": data_stamp(con)}


def revert_timetable(con: sqlite3.Connection, cid: str, *, semester: str, now: Optional[datetime] = None) -> dict:
    """'자동값으로 되돌리기' — 시간표 조회에서 찾은 값으로 (학기 처음부터)."""
    row = _course_row(con, semester, cid)
    auto = loads(row["tt_auto"], None)
    if not auto:
        raise Invalid("자동으로 찾은 시간표가 없습니다 — 먼저 '시간표 자동으로 가져오기'를 하세요")
    return save_timetable(con, {"courses": [{"courseId": cid, "meetings": auto}]}, semester=semester, now=now)


def apply_import(con: sqlite3.Connection, sid: str, results: list[dict]) -> dict:
    """시간표 자동 수집 결과 반영 (F3-R02·R02a). 내가 고친 시간표는 덮지 않는다(kept)."""
    filled, kept, same, missing, errors = [], [], [], [], []
    for r in results:
        row = con.execute("SELECT * FROM courses WHERE semester = ? AND id = ?", (sid, r["courseId"])).fetchone()
        if row is None:
            continue
        ms = r.get("meetings") or []
        con.execute("UPDATE courses SET tt_status = ?, tt_message = ?, tt_raw = ?, tt_auto = ?, tt_checked_at = ? "
                    "WHERE semester = ? AND id = ?",
                    (r["status"], r.get("message"), dumps(r.get("raw")) if r.get("raw") else None,
                     dumps(ms) if r["status"] == "found" else row["tt_auto"], now_iso(), sid, r["courseId"]))
        name = row["short"]
        if r["status"] != "found":
            (errors if r["status"] == "error" else missing).append({"name": name, "message": r.get("message")})
            continue
        versions = _versions(con, sid, r["courseId"])
        if not versions or (len(versions) == 1 and versions[0]["filledBy"] == "auto"):
            if versions and _same(versions[0]["meetings"], ms):
                same.append(name)
                continue
            con.execute("DELETE FROM meetings WHERE semester = ? AND course_id = ?", (sid, r["courseId"]))
            _save_version(con, sid, r["courseId"], ms, "", "auto")
            filled.append({"name": name, "text": T.meetings_text(ms)})
        elif _same(versions[-1]["meetings"], ms):
            same.append(name)
        else:
            kept.append({"name": name, "text": T.meetings_text(ms)})
    store.touch(con)
    return {"filled": filled, "kept": kept, "same": same, "missing": missing, "errors": errors}


def import_targets(con: sqlite3.Connection, sid: str) -> list[dict]:
    return [dict(r) for r in con.execute(
        "SELECT id, name, short, code, section FROM courses WHERE semester = ? AND excluded = 0 ORDER BY seq", (sid,))]


# ── 캘린더 (C1 class) · 오늘 · 타일 ───────────────────────────

def calendar_events(con: sqlite3.Connection, start: Optional[str] = None, end: Optional[str] = None,
                    now: Optional[datetime] = None) -> list[dict]:
    """/api/events 에 섞는 수업 일정 (F3-R14, C1 3절 kind=class). 휴강 회차도 싣는다(화면이 취소선·'휴강'으로 그린다)."""
    now = now or datetime.now()
    cal = AC.load()
    out = []
    for sid in semester_ids(con, cal):
        sem = resolve_semester(con, cal, sid)
        if not sem["start"] or not sem["end"]:
            continue
        if (end and sem["start"] > end) or (start and sem["end"] < start):
            continue
        _, courses = build_semester(con, sid, now, cal)
        for c in courses:
            if c["excluded"]:
                continue
            for s in c["sessions"]:
                if (start and s["date"] < start) or (end and s["date"] > end):
                    continue
                out.append({
                    "id": s["id"], "title": c["short"],
                    "start": f"{s['date']}T{s['start']}:00", "end": f"{s['date']}T{s['end']}:00",
                    "allDay": False, "editable": False,
                    "extendedProps": {
                        "kind": "class", "courseId": c["id"], "semester": sid, "courseName": c["name"],
                        "courseCode": c["code"], "section": c["section"], "color": c["color"] or "#64748b",
                        "periods": s["periods"], "periodsText": T.meeting_text({"weekday": s["weekday"], "periods": s["periods"]}),
                        "room": s["room"], "state": s["state"], "attendance": s["attendance"],
                        "cancelSource": s["cancelSource"], "autoCancel": s["autoCancel"],
                        "sessionKind": s["kind"], "origin": s["origin"], "makeupName": s["makeupName"],
                        "makeupFor": s["makeupFor"], "memo": s["memo"], "started": s["started"],
                        "level": c["summary"]["level"], "levelLabel": c["summary"]["levelLabel"],
                        "remaining": c["summary"]["remaining"], "spareSessions": c["summary"]["spareSessions"],
                    },
                })
    return out


def today(con: sqlite3.Connection, now: Optional[datetime] = None) -> dict:
    """오늘 수업과 위험 과목 — F10 아침 브리핑(F3-R35)·F9 대화가 읽는다."""
    now = now or datetime.now()
    cal = AC.load()
    sid = current_semester(con, cal, now.date())
    _, courses = build_semester(con, sid, now, cal)
    t = now.date().isoformat()
    classes = [{"courseId": c["id"], "name": c["short"], "color": c["color"], **{k: s[k] for k in (
        "id", "start", "end", "periods", "room", "state", "cancelSource", "attendance", "kind")},
        "level": c["summary"]["level"], "levelLabel": c["summary"]["levelLabel"]}
        for c in courses if not c["excluded"] for s in c["sessions"] if s["date"] == t]
    classes.sort(key=lambda x: x["start"])
    return {"date": t, "semester": sid, "classes": classes, "totals": _totals(courses)}


def status_summary(con: sqlite3.Connection, profile: Optional[dict] = None, eclass: Optional[list[dict]] = None,
                   now: Optional[datetime] = None, notify: Optional[Notify] = None) -> dict:
    """/api/status 의 attendance 칸 — 대시보드 기능 타일(F3-S08)."""
    now = now or datetime.now()
    cal = AC.load()
    sid = current_semester(con, cal, now.date())
    if eclass is not None:
        sync_courses(con, sid, eclass)
    sem, courses = build_semester(con, sid, now, cal)
    evaluate_alerts(con, courses, notify, now)
    return {"semester": sid, "label": sem["label"], "semesterMissing": not (sem["start"] and sem["end"]),
            "updatedAt": data_stamp(con), **_totals(courses)}
