"""과목마다 중간·기말 — 일정이 안 나온 시험을 **임의로 잡아 두고**, 진짜 일정이 나오면 그 자리를 바꾼다 (2026-10-01 사용자 요청).

규칙
  1. 모든 과목은 중간고사·기말고사 2회를 본다고 둔다. 시험이 없는 과목은 사용자가 과목별로 끈다(course_settings).
     퀴즈·발표는 여기서 만들지 않는다 — 공지·직접 추가로만 생긴다.
  2. 중간고사 일정이 아직 없으면 학사일정 **'중간 수업평가' 기간** 안에서 **그 과목의 수업 회차**(F3)로 잡는다.
       - 공식 '중간고사' 주간이 그 안에 있으면 그 주의 **첫 수업**, 없으면 기간 마지막 7일의 첫 수업
       - 시험은 보통 수업 시간에 본다 → 시각도 그 회차의 수업 시각으로 넣는다
       - 시간표가 없는 과목은 그 주의 첫 평일로, 시각 없이(‘시각 미정’)
       - 이른 날짜를 고르는 이유: 계획을 이른 날짜에 맞춰 두면 실제 시험이 늦을 때 여유가 생기고,
         늦게 잡았다가 실제가 빠르면 준비가 안 된다
  3. 기말고사는 **그 과목의 중간고사 날짜가 지나면** 만든다(중간고사가 없는 과목은 중간 수업평가 기간이 끝나면).
     기간은 '최종 수업평가'(종강까지로 자른다), 고르는 방식은 2와 같다.
  4. 임의 일정(source='auto')은 진짜 일정이 아니다 —
       - 공지에서 같은 과목의 중간/기말이 나오면 **같은 id** 라 그 자리가 공지 값으로 바뀐다(service.sync_notices)
       - 사용자가 날짜를 고치면 직접 넣은 일정(manual)이 된다
       - 시간표가 나중에 들어오면 수업 요일로 다시 잡는다. 단 **계획을 이미 등록했으면 옮기지 않는다**(블록이 엇나간다)
  5. 이미 기간이 지난 시험은 새로 만들지 않는다(지난 날짜의 '임의 일정'은 쓸모가 없다).

날짜를 지어내지 않는다: 학사일정에 기간이 없으면 만들지 않고 이유(hints)만 남긴다.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from typing import Any, Callable, Optional

from . import academic, classes, store
from . import config as C

CoursesGetter = Callable[[], list[dict]]
WD = "월화수목금토일"

# 규칙 버전 — **규칙을 바꾸면 올린다.** 도장(_stamp)에 들어가서, 규칙이 바뀐 뒤 처음 부를 때 반드시 다시 계산하게 한다.
#   1: 과목마다 중간·기말 임의 일정 (2026-10-01)
#   2: 시각 미정 → 수업 시간 채우기 (2026-10-01)
#   이 값이 없던 때 실제로 생긴 일: 1 이 같은 날 저장한 도장과 2 의 도장이 똑같아 시각 채우기가 한 번도 돌지 않았다
#   (산학협력 발표 10/7 이 계속 '시각 미정'). 격리 테스트는 시간표 DB 경로가 달라 도장이 달라져서 이걸 놓쳤다.
RULES_VERSION = 2
LABEL = {"midterm": "중간", "final": "기말"}


def _iso(d: date) -> str:
    return d.isoformat()


def _prefer(part: dict) -> Optional[tuple[date, date]]:
    """고르는 주간 — 공식 시험 주간(평가 기간과 겹치는 부분), 없으면 평가 기간 마지막 7일."""
    window = part["window"]
    if not window:
        return None
    lo, hi = window
    exam = part["exam"]
    if exam and exam[0] <= hi and exam[1] >= lo:
        return max(lo, exam[0]), min(hi, exam[1])
    return max(lo, hi - timedelta(days=6)), hi


def place(kind: str, part: dict, sessions: Optional[list[dict]], today: date) -> Optional[dict]:
    """임의 일정 한 건 — {date, time, endTime, note}. 잡을 수 없으면 None (기간이 없거나 다 지났다)."""
    window = part["window"]
    prefer = _prefer(part)
    if not window or not prefer or window[1] < today:
        return None
    name = "중간고사" if kind == "midterm" else "기말고사"
    evname = "중간 수업평가" if kind == "midterm" else "최종 수업평가"
    where = (f"학사일정 '{evname}'({academic.label(part['evaluation'])})" if part["evaluation"]
             else f"학사일정 '{name}'({academic.label(part['exam'])})")
    week = f"{name} 주간({academic.label(prefer)})" if part["exam"] else f"기간 마지막 주({academic.label(prefer)})"

    def pick(lo: date, hi: date) -> Optional[dict]:
        for s in sessions or []:
            d = date.fromisoformat(s["date"])
            if lo <= d <= hi and d >= today:
                return s
        return None

    s = pick(*prefer) or pick(*window)
    if s:
        d = date.fromisoformat(s["date"])
        how = "첫 수업" if prefer[0] <= d <= prefer[1] else "남은 첫 수업"
        return {"date": s["date"], "time": s["start"], "endTime": s["end"],
                "note": f"{where} 안에서 {week}의 {how}({WD[d.weekday()]} {s['start']})으로 임의로 잡았습니다"}
    # 시간표가 없다 — 그 주의 첫 평일, 시각 없이
    d = max(prefer[0], today)
    while d <= window[1] and d.weekday() >= 5:
        d += timedelta(days=1)
    if d > window[1]:
        return None
    why = "남은 수업이 없어" if sessions else "수업 시간표가 없어"
    return {"date": _iso(d), "time": "", "endTime": "",
            "note": f"{why} {where} 안에서 {week}의 첫 평일로 임의로 잡았습니다 — 시각 미정"}


def class_time(sessions: list[dict], when: str) -> Optional[dict]:
    """시각이 없는 시험의 시각 — 그날 수업 시간 > 같은 요일의 수업 시간 > 그 과목의 첫 수업 시간."""
    if not sessions:
        return None
    for s in sessions:
        if s["date"] == when:
            return {"start": s["start"], "end": s["end"], "how": "그날 수업 시간"}
    wd = date.fromisoformat(when).weekday()
    same = [s for s in sessions if date.fromisoformat(s["date"]).weekday() == wd]
    if same:
        return {"start": same[0]["start"], "end": same[0]["end"], "how": f"{WD[wd]}요일 수업 시간"}
    first = sessions[0]
    return {"start": first["start"], "end": first["end"], "how": "그 과목 수업 시간"}


def _stamp(con: sqlite3.Connection, today: date, course_ids: list[str]) -> str:
    try:
        st = C.F1_DB.stat()
        f1 = f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        f1 = "-"
    settings = store.course_settings(con)
    return json.dumps([RULES_VERSION, _iso(today), sorted(course_ids),
                       sorted((k, v["midterm"], v["final"]) for k, v in settings.items()),
                       f1, classes.stamp(), store.updated_at(con)], ensure_ascii=False, default=str)


def ensure(con: sqlite3.Connection, today: Optional[date] = None,
           get_courses: Optional[CoursesGetter] = None, force: bool = False) -> dict:
    """모든 과목의 중간·기말을 규칙대로 맞춘다. 바뀐 것이 없으면 아무 것도 하지 않는다(도장으로 건너뛴다).

    돌려주는 것: {skipped, semester, created, moved, removed, hints, periods}
    """
    from . import service                                   # 순환 import 를 피해 여기서 (service 가 이 모듈을 부른다)

    today = today or date.today()
    courses = service.course_map(get_courses)
    sid = service.semester_of(today)
    stamp = _stamp(con, today, list(courses))
    if not force and store.get_meta(con, "defaults_stamp") == stamp:
        return {"skipped": True, "semester": sid, "created": [], "moved": [], "removed": [], "timed": [], "hints": []}

    per = academic.periods(sid)
    sess = classes.sessions(sid)
    out: dict[str, Any] = {"skipped": False, "semester": sid, "created": [], "moved": [], "removed": [], "hints": []}
    if not per["available"]:
        out["hints"].append("학사일정(F1)을 읽지 못해 시험 일정을 임의로 잡지 못했습니다")
    elif not per["midterm"]["window"]:
        out["hints"].append(f"{service.semester_label(sid)} 학사일정에 '중간 수업평가' 기간이 아직 없습니다")
    if sess is None:
        out["hints"].append("수업 시간표(F3)를 읽지 못해 시험 시각은 비워 둡니다")

    t = _iso(today)
    for cid, c in courses.items():
        setting = store.course_setting(con, cid)
        for kind in C.DEFAULT_EXAM_TYPES:
            eid = service.exam_id(cid, kind, "")
            cur = store.exam(con, eid, include_removed=True)
            label = f"{c['short']} {C.type_label(kind)}"

            if not setting[kind]:
                # 이 과목은 이 시험을 안 본다 — 임의 일정만 치운다(공지·직접 넣은 시험은 진짜 정보라 둔다)
                if cur is not None and cur["source"] == "auto":
                    store.hard_delete_exam(con, eid)
                    out["removed"].append({"examId": eid, "course": c["short"], "type": kind, "label": label})
                continue
            if not per["available"]:
                continue

            if kind == "final" and cur is None and not _midterm_over(con, cid, per, today):
                continue                                         # 기말은 중간고사가 끝난 뒤에 만든다

            if cur is None:
                spot = place(kind, per[kind], (sess or {}).get(cid) if sess is not None else None, today)
                if spot is None:
                    if kind == "final" and not per["final"]["window"]:
                        hint = f"{service.semester_label(sid)} 학사일정에 '최종 수업평가' 기간이 아직 없어 기말고사를 잡지 못했습니다"
                        if hint not in out["hints"]:
                            out["hints"].append(hint)
                    continue
                stamp_now = store.now()
                store.upsert_exam(con, {
                    "id": eid, "course_id": cid, "course": c["name"], "type": kind, "title": C.type_label(kind),
                    "date": spot["date"], "time": spot["time"], "end_time": spot["endTime"], "place": "",
                    "scope_weeks": "[]", "scope_ids": "[]", "scope_note": "", "source": "auto",
                    "evidence": "[]", "confidence": C.AUTO_EXAM_CONFIDENCE, "status": "confirmed",
                    "notice_key": "", "notice_url": "", "posted_at": "", "edited": 0, "changed": "",
                    "removed_at": None, "note": spot["note"], "added_at": stamp_now, "seen_at": stamp_now,
                })
                out["created"].append({"examId": eid, "course": c["short"], "type": kind, "label": label,
                                       "date": spot["date"], "time": spot["time"]})
                continue

            # 이미 있는 임의 일정 — 시간표가 바뀌었으면 다시 잡는다. 계획을 등록했거나 지난 일정이면 그대로 둔다
            if (cur["source"] != "auto" or cur["edited"] or cur["removed_at"] or cur["date"] < t
                    or store.active_plan(con, eid) is not None):
                continue
            spot = place(kind, per[kind], (sess or {}).get(cid) if sess is not None else None, today)
            if spot and (spot["date"], spot["time"], spot["endTime"]) != (cur["date"], cur["time"], cur["end_time"]):
                store.update_exam(con, eid, {"date": spot["date"], "time": spot["time"], "end_time": spot["endTime"],
                                             "note": spot["note"], "seen_at": store.now()})
                out["moved"].append({"examId": eid, "course": c["short"], "type": kind, "label": label,
                                     "from": cur["date"], "to": spot["date"]})

    # 시각 미정 → 그 과목의 수업 시간 (2026-10-01 사용자 요청: 발표·시험 모두)
    out["timed"] = []
    if sess:
        for r in store.exam_rows(con):
            if r["time"] or r["course_id"] not in sess:
                continue
            slot = class_time(sess[r["course_id"]], r["date"])
            if slot:
                store.update_exam(con, r["id"], {"time": slot["start"], "end_time": slot["end"], "time_auto": 1})
                out["timed"].append({"examId": r["id"], "course": courses.get(r["course_id"], {}).get("short", r["course_id"]),
                                     "date": r["date"], "time": slot["start"], "how": slot["how"]})

    if out["created"] or out["moved"] or out["removed"] or out["timed"]:
        store.touch(con)
    store.set_meta(con, defaults_stamp=_stamp(con, today, list(courses)))
    out["periods"] = period_view(per)
    return out


def _midterm_over(con: sqlite3.Connection, cid: str, per: dict, today: date) -> bool:
    """그 과목의 중간고사가 끝났나 — 중간고사가 있으면 그 날짜가 지났는지, 없으면 중간 수업평가 기간이 끝났는지."""
    from . import service

    mid = store.exam(con, service.exam_id(cid, "midterm", ""))
    if mid is not None:
        return mid["date"] < _iso(today)
    window = per["midterm"]["window"] or per["midterm"]["exam"]
    return bool(window) and window[1] < today


def period_view(per: dict) -> dict:
    """화면 안내용 — '중간 수업평가 10/12~10/23 · 중간고사 10/19~10/23'."""
    def one(p: dict) -> dict:
        return {k: ([_iso(p[k][0]), _iso(p[k][1])] if p[k] else None) for k in ("evaluation", "exam", "window")} | {
            "label": " · ".join(x for x in (
                f"수업평가 {academic.label(p['evaluation'])}" if p["evaluation"] else "",
                f"시험 주간 {academic.label(p['exam'])}" if p["exam"] else "") if x)}
    return {"available": per["available"], "semester": per["semester"],
            "start": _iso(per["start"]) if per["start"] else None, "end": _iso(per["end"]) if per["end"] else None,
            "midterm": one(per["midterm"]), "final": one(per["final"])}


__all__ = ["ensure", "place", "class_time", "period_view"]
