"""수업 회차 만들기 — 순수 함수 (F3-R10~R17). 회차는 **저장하지 않고 매번 계산**한다.

    회차 = 과목이 수업하는 **날 하나** (2026-09-29 수정 ① — 전남대는 출석을 하루 단위로 부른다.
           월 5·6교시든 수 5교시든 그날 한 번이고, 같은 날 두 번 나뉜 수업도 1회다)
         = 시간표(요일·교시, 판마다 적용 시작일) × 학기 범위(개강~종강)
         + 학교 지정 보강일(휴업일에 걸린 회차를 그날 다시 한다) + 내가 추가한 보강
    자동 휴강 (2026-09-29 수정 ③) — 학사일정 휴업·휴강일(모든 과목) · e클래스 과목 공지의 휴강(그 과목)
         → 회차를 '휴강'으로 두고 이유(cancel)를 단다. 사용자가 되돌리면(수업함) 그 기록이 이긴다.
    위에 '내 기록'(출결·휴강·메모)을 회차 id 로 덧씌운다.

원천(시간표·학사일정·공지)과 사용자 값(기록)을 나누는 F1 의 items/events 와 같은 생각이다 — 시간표를 다시 가져와도
기록은 회차 id(`cl:<과목>:<날짜>`, 보강은 `:mk`)로 따라간다. 교시가 바뀌어도 날짜가 같으면 같은 회차다.
맞는 회차가 사라진 기록은 '떠 있는 기록'(orphans)으로 따로 돌려준다(지우지 않는다).

회차 id 는 C1 캘린더의 `class` 일정 id 와 같다 (F3-R14 — 두 벌로 만들지 않는다).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Optional

from . import config as C

PeriodMap = dict[str, dict[int, tuple[str, str]]]


def default_period_map() -> PeriodMap:
    return {"mwf": dict(C.MODULE_MWF), "tt": dict(C.MODULE_TT)}


def period_span(wd: int, periods: list[int], pmap: PeriodMap) -> tuple[str, str]:
    """(시작 'HH:MM', 끝 'HH:MM') — 캘린더에 그릴 시각. 요일마다 학교 시간표 모듈(월수금 50분·화목 75분)."""
    table = pmap[C.WEEKDAY_MODULE[wd]]
    # 화·목 표에 없는 교시(11교시 이상)는 월수금 표로 — 시각을 지어내지 않고 가장 가까운 공식 표를 쓴다
    spans = [table.get(p) or pmap["mwf"][p] for p in periods]
    return min(s for s, _ in spans), max(e for _, e in spans)


def session_id(course_id: str, day: str, makeup: bool = False) -> str:
    return f"cl:{course_id}:{day}{':mk' if makeup else ''}"


def _version_for(versions: list[dict], day: str) -> Optional[dict]:
    """그날 적용되는 시간표 판 — validFrom 이 그날 이전(또는 '학기 처음부터' = '')인 것 중 가장 늦은 것."""
    cur = None
    for v in versions:                       # validFrom 오름차순
        if (v.get("validFrom") or "") <= day:
            cur = v
    return cur


def build(course_id: str, versions: list[dict], start: date, end: date, *, holidays: dict[str, str],
          school_makeups: list[dict], user_makeups: list[dict], marks: dict[str, dict],
          notice_cancels: Optional[dict[str, dict]] = None, pmap: Optional[PeriodMap] = None) -> tuple[list[dict], list[dict]]:
    """과목 하나의 회차 목록과 떠 있는 기록. versions = [{validFrom, meetings: [{weekday, periods, room}]}] (오름차순).
    holidays = {날짜: 이름} (학사일정), notice_cancels = {날짜: {reason, url, posted}} (그 과목 e클래스 공지)."""
    pmap = pmap or default_period_map()
    notice_cancels = notice_cancels or {}
    versions = sorted(versions, key=lambda v: v.get("validFrom") or "")
    out: list[dict] = []
    if versions and start <= end:
        d = start
        while d <= end:
            key = d.isoformat()
            v = _version_for(versions, key)
            todays = [m for m in (v or {}).get("meetings") or [] if m["weekday"] == d.weekday()]
            if todays:
                periods = sorted({p for m in todays for p in m["periods"]})
                s, e = period_span(d.weekday(), periods, pmap)
                rooms = ", ".join(dict.fromkeys(m.get("room") for m in todays if m.get("room")))
                auto = None
                if key in holidays:
                    auto = {"source": "academic", "reason": holidays[key], "url": None}
                elif key in notice_cancels:
                    n = notice_cancels[key]
                    auto = {"source": "eclass", "reason": n.get("reason"), "url": n.get("url"), "posted": n.get("posted")}
                out.append(_session(course_id, key, d.weekday(), periods, s, e, rooms, kind="regular",
                                    origin="timetable", auto=auto))
            d += timedelta(days=1)

    # 휴업일 회차를 기록(되돌리기)까지 반영한 뒤에 학교 보강일을 붙인다 — '휴업일이었지만 수업함'이면 보강 없음
    _apply(out, marks)
    by_date = {x["date"]: x for x in out}
    extra: list[dict] = []
    for mk in school_makeups:
        md = date.fromisoformat(mk["date"])
        x = by_date.get(mk["original"])
        if not start <= md <= end or x is None or x["state"] != "canceled" or (x["autoCancel"] or {}).get("source") != "academic":
            continue
        s, e = period_span(md.weekday(), x["periods"], pmap)
        extra.append(_session(course_id, mk["date"], md.weekday(), x["periods"], s, e, x["room"],
                              kind="makeup", origin="school", makeup_for=x["date"], makeup_name=mk["name"]))
    taken = {x["id"] for x in extra}
    for um in user_makeups:
        if um["id"] in taken:
            continue
        md = date.fromisoformat(um["date"])
        s, e = period_span(md.weekday(), um["periods"], pmap)
        sess = _session(course_id, um["date"], md.weekday(), um["periods"], s, e, "", kind="makeup", origin="user")
        sess["id"] = um["id"]
        sess["memo"] = um.get("memo") or ""
        extra.append(sess)
    _apply(extra, marks)
    out.extend(extra)
    out.sort(key=lambda x: (x["date"], x["kind"] == "makeup", x["start"]))

    ids = {x["id"] for x in out}
    orphans = [{"id": k, **{f: m.get(f) for f in ("date", "attendance", "state", "memo")}}
               for k, m in marks.items() if k not in ids and (m.get("attendance") or m.get("memo"))]
    return out, orphans


def _session(course_id: str, day: str, wd: int, periods: list[int], start: str, end: str, room: str, *,
             kind: str, origin: str, auto: Optional[dict] = None, makeup_for: Optional[str] = None,
             makeup_name: Optional[str] = None) -> dict[str, Any]:
    state = "canceled" if auto else "scheduled"
    return {
        "id": session_id(course_id, day, makeup=kind == "makeup"),
        "courseId": course_id, "date": day, "weekday": wd, "periods": list(periods),
        "start": start, "end": end, "room": room,
        "kind": kind,                 # regular 정규 / makeup 보강
        "origin": origin,             # timetable 시간표 / school 학교 지정 보강일 / user 내가 추가
        "state": state,               # scheduled 예정 / canceled 휴강
        "baseState": state,           # 원천이 말하는 상태 (자동 휴강이면 canceled)
        "autoCancel": auto,           # 자동 휴강 근거 {source: academic|eclass, reason, url} — 되돌려도 남는다
        "cancelSource": auto["source"] if auto else None,   # 휴강이면 누가: academic · eclass · user
        "makeupFor": makeup_for, "makeupName": makeup_name,
        "attendance": None,           # present · absent · late · excused · None(미입력)
        "memo": "",
    }


def _apply(sessions: list[dict], marks: dict[str, dict]) -> None:
    for x in sessions:
        m = marks.get(x["id"])
        if not m:
            continue
        if m.get("state") == "canceled":
            x["state"], x["cancelSource"] = "canceled", x["cancelSource"] or "user"
        elif m.get("state") == "scheduled":
            x["state"], x["cancelSource"] = "scheduled", None      # 자동 휴강이었지만 수업함 — 되돌리기
        x["attendance"] = m.get("attendance") if x["state"] == "scheduled" else None
        x["recorded"] = m.get("attendance")   # 휴강으로 바꿔도 기록은 남긴다 (되돌리면 다시 보인다)
        if m.get("memo"):
            x["memo"] = m["memo"]
