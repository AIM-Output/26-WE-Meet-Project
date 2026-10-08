"""F8 화면·연동용 묶음 — 미리보기 · 등록 · 캘린더 일정 · 충돌 · 옮기기 · 지우기 · 오늘 블록 · 상태 타일.

입력은 전부 넘겨받는다(백엔드는 자기가 붙인 F3·C1·F1·F5·F7 에서, 명령줄은 sources.py 가 직접 읽어서):
  events    캘린더 일정 (/api/events 모양) — 수업(class) · 내 일정·할 일(user) · 시험(exam).
            학사 일정(academic) · 마감 · 학습 블록은 무시 — 학사 일정은 '내 일정에 넣기'로 만든 내 일정(user)만 본다
  exams     F5 공강 공부 대상 (exams.api.study_targets — 다가오는 시험 · 진도율 %)
  priority  F7 순위 목록 (/api/priority 의 items — 순서 그대로)
이 모듈이 여는 것은 자기 DB(store)뿐이다. fastapi 도 부르지 않는다(명령줄에서도 쓴다).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from . import config as C
from . import rules, slots, store
from . import settings as S
from .settings import hhmm, minutes as to_min

Invalid = S.Invalid


class NotFound(Exception):
    pass


class Stale(Exception):
    """미리보기 뒤에 데이터가 바뀌었다 — 다시 계산해야 한다 (F8 8절 '배치 중 데이터 변경')."""


# ---------------------------------------------------------------- 시각 다루기

def parse_dt(v: Any) -> Optional[datetime]:
    if not v:
        return None
    s = str(v).replace(" ", "T")
    if len(s) == 10:
        return None                                          # 날짜만 = 종일 — 시간을 차지하지 않는다
    try:
        return datetime.fromisoformat(s).replace(tzinfo=None)
    except ValueError:
        return None


def block_dt(d: str, hm: str) -> datetime:
    """('2026-10-06', '24:00') → 10/7 00:00."""
    m = to_min(hm, allow_24=True)
    return datetime.fromisoformat(d) + timedelta(minutes=m)


def _per_day(start: datetime, end: datetime) -> Iterable[tuple[str, int, int]]:
    """[start, end) 를 날짜별 (날짜, 시작 분, 끝 분)으로 자른다."""
    cur = start
    while cur < end:
        day0 = datetime(cur.year, cur.month, cur.day)
        nxt = day0 + timedelta(days=1)
        stop = min(end, nxt)
        yield day0.date().isoformat(), int((cur - day0).total_seconds() // 60), int((stop - day0).total_seconds() // 60)
        cur = stop


BUSY_KINDS = ("user", "exam")          # 시간을 차지하는 일정 — 학사(academic)는 빠진다 (2026-10-07)


def split_events(events: Iterable[dict]) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """캘린더 일정 → (날짜별 수업, 날짜별 차지된 구간).

    수업(class)은 휴강도 싣는다(canceled — 슬롯 계산이 수업으로 치지 않는다, R08). 차지하는 것은 시각이 있는
    내 일정·할 일 · 시험 (R03). 과제 마감은 한 시점이라 시간을 차지하지 않는다.
    **학사 일정(academic)은 보지 않는다** (2026-10-07 사용자 요청) — 학교 전체 일정이라 내 시간을 차지하지 않는다.
    학사 일정에서 '내 일정에 넣기'로 만든 항목은 내 일정(user, origin='ac:…')이라 그대로 차지된 시간이다.
    날짜만 있는 할 일은 여기서 보지 않는다 — todo_tasks 가 공강에 넣을 작업으로 만든다."""
    classes: dict[str, list[dict]] = {}
    busy: dict[str, list[dict]] = {}
    for ev in events:
        p = ev.get("extendedProps") or {}
        kind = p.get("kind")
        if ev.get("allDay") or kind in (None, "deadline", "study"):
            continue
        s = parse_dt(ev.get("start"))
        if s is None:
            continue
        e = parse_dt(ev.get("end")) or s + timedelta(hours=1)        # 끝이 없으면 한 시간 (F7 과 같다)
        if e <= s:
            continue
        for d, a, b in _per_day(s, e):
            if kind == "class":
                classes.setdefault(d, []).append({"start": a, "end": b, "title": ev.get("title") or "수업",
                                                  "canceled": p.get("state") == "canceled", "id": ev.get("id")})
            elif kind in BUSY_KINDS:
                busy.setdefault(d, []).append({"start": a, "end": b, "title": ev.get("title") or "", "kind": kind,
                                               "id": ev.get("id")})
    return classes, busy


# ---------------------------------------------------------------- 남겨 두는 블록 (F8-R30 · R33)

def is_kept(r: Any, now: datetime, first: str, last: str) -> bool:
    """다시 계산해도 그대로 두는 블록 — 완료 · 내가 옮긴(고정) · 이미 시작했거나 지난 것 · 기간 밖."""
    if r["done"] or r["placed_by"] == "user":
        return True
    if not first <= r["date"] <= last:
        return True
    return block_dt(r["date"], r["start"]) < now


def kept_per_day(rows: Iterable[Any], ref: str, now: datetime, first: str, last: str) -> dict[str, int]:
    """그 작업의 남겨 두는 블록이 날짜마다 몇 개인가 — 하루 2블록 제한(R16)에 같이 센다."""
    out: dict[str, int] = {}
    for r in rows:
        if r["ref_id"] == ref and is_kept(r, now, first, last):
            out[r["date"]] = out.get(r["date"], 0) + 1
    return out


def consumed(rows: Iterable[Any], ref: str, now: datetime) -> int:
    """이미 해 둔(또는 하기로 고정한) 분 — 작업 길이에서 뺀다. 완료 · 고정(아직 안 지남) · 진행 중인 블록.
    지나갔는데 체크하지 않은 자동 블록은 한 것으로 치지 않는다(다시 배치된다)."""
    total = 0
    for r in rows:
        if r["ref_id"] != ref:
            continue
        s, e = block_dt(r["date"], r["start"]), block_dt(r["date"], r["end"])
        if r["done"] or (s <= now < e) or (r["placed_by"] == "user" and e > now):
            total += int(r["minutes"])
    return total


# ---------------------------------------------------------------- 작업 목록 (F8 5절 ②)

TODO_COLOR = "#c2410c"            # 할 일 색 (대시보드와 같다)


def todo_tasks(events: Iterable[dict], rows: list[Any], now: datetime, settings: dict,
               first: str, last: str) -> list[dict]:
    """C1 할 일(날짜만 있는 미완료) → 작업. 길이 30분, 기한 = 그 날 낮 끝. 날짜가 지난 할 일(2주 안)은 '밀린 할 일'로
    기간 안 아무 때나(가장 이른 공강). 시각이 있는 할 일은 이미 그 시각에 있으므로 넣지 않는다(차지된 시간이다)."""
    out = []
    oldest = (now.date() - timedelta(days=C.TODO_LOOKBACK_DAYS)).isoformat()
    day_end = to_min(settings["dayEnd"])
    for ev in events:
        p = ev.get("extendedProps") or {}
        if p.get("kind") != "user" or not p.get("isTodo") or p.get("done") or not ev.get("allDay"):
            continue
        d = str(ev.get("start") or "")[:10]
        if not d or d > last or d < oldest:
            continue
        late = d < first
        due = datetime.fromisoformat(last if late else d) + timedelta(minutes=day_end)
        key = f"todo:{ev.get('id')}"
        total = C.TODO_MINUTES
        left = total - consumed(rows, key, now)
        if left <= 0:
            continue
        out.append({
            "key": key, "type": "todo", "title": ev.get("title") or "할 일", "detail": ev.get("title") or "할 일",
            "course": "", "color": TODO_COLOR, "date": d, "late": late, "due": due,
            "minutes": left, "totalMinutes": total, "keptPerDay": kept_per_day(rows, key, now, first, last),
            "slack": (due - now).total_seconds() / 3600 - left / 60, "href": f"/?event={ev.get('id')}",
        })
    return out


def study_targets(exams: Iterable[dict]) -> list[dict]:
    """F5 공강 공부 대상 → rules.fill_study 가 쓰는 모양. 제목은 '운영체제 중간고사 공부'."""
    out = []
    for x in exams:
        if not x.get("examId") or not x.get("date"):
            continue
        out.append({
            "examId": x["examId"], "title": f"{x.get('course') or ''} {x.get('typeLabel') or '시험'} 공부".strip(),
            "course": x.get("course") or "", "color": x.get("color") or C.STUDY_COLOR,
            "date": x["date"], "time": x.get("time") or "", "percent": x.get("percent") or 0,
            "isAuto": bool(x.get("isAuto")), "href": x.get("href") or "/exams",
            "typeLabel": x.get("typeLabel") or "",
        })
    return out


def kept_study(rows: Iterable[Any], now: datetime, first: str, last: str) -> dict[str, dict[str, int]]:
    """남겨 두는 공부 블록 수 {시험 id: {날짜: 수}} — 공부 블록의 하루 2블록 · 같은 과목 감점에 센다."""
    out: dict[str, dict[str, int]] = {}
    for r in rows:
        if r["task_type"] == "study" and is_kept(r, now, first, last):
            day = out.setdefault(r["ref_id"], {})
            day[r["date"]] = day.get(r["date"], 0) + 1
    return out


def assignment_tasks(priority: Iterable[dict], rows: list[Any], now: datetime,
                     first: str = "", last: str = "9999-12-31") -> list[dict]:
    """F7 순위 목록 → 작업 (순서 그대로, R12). 마감 없음 · 2주 넘게 지난 놓친 마감은 대상이 아니다."""
    out = []
    for it in priority:
        g = it.get("group")
        if g not in C.ASSIGNMENT_GROUPS and not (g == "overdue" and not it.get("stale")):
            continue
        due = parse_dt(it.get("due"))
        if due is None:
            continue
        total = int(round(float(it.get("neededHours") or it.get("estimatedHours") or 0) * 60))
        left = total - consumed(rows, it["id"], now)
        if total <= 0 or left <= 0:
            continue
        out.append({
            "key": it["id"], "type": "assignment", "title": it.get("title") or "과제",
            "detail": it.get("courseShort") or it.get("course") or "과제",
            "course": it.get("courseShort") or "", "color": it.get("courseColor") or C.STUDY_COLOR,
            "due": due, "minutes": left, "totalMinutes": total,
            "keptPerDay": kept_per_day(rows, it["id"], now, first, last),
            "slack": it.get("slackHours"), "href": f"/assignments?event={it['id']}",
        })
    return out


# ---------------------------------------------------------------- 미리보기 (F8-R20 · S02)

def _row_view(r: Any) -> dict:
    return {
        "id": f"{C.EVENT_PREFIX}{r['id']}", "blockId": r["id"], "taskType": r["task_type"], "refId": r["ref_id"],
        "title": r["title"], "course": r["course"], "color": r["color"] or C.STUDY_COLOR,
        "date": r["date"], "start": r["start"], "end": r["end"], "minutes": r["minutes"],
        "reason": r["reason"], "slot": r["slot"], "href": r["href"] or None,
        "placedBy": r["placed_by"], "auto": r["placed_by"] == "auto", "done": bool(r["done"]),
    }


def signature(blocks: list[dict]) -> str:
    raw = json.dumps([[b["key"], b["date"], b["start"], b["end"], b["minutes"]] for b in blocks], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def preview(con: sqlite3.Connection, events: list[dict], exams: list[dict], priority: list[dict],
            settings: Optional[dict] = None, now: Optional[datetime] = None, range_days: Optional[int] = None,
            exclude: Iterable[str] = ()) -> dict:
    """배치 계산만 한다 — 캘린더를 바꾸지 않는다. 자동 배치분(앞으로 · 미완료 · 고정 아님)만 다시 계산한다.

    ① 과제(F7 순서) · 할 일 → 공강  ② 남은 공강 → 공부 블록(남은 진도율 ÷ 시험까지 남은 날수, 설정 fillStudy)."""
    now = (now or datetime.now()).replace(microsecond=0)
    settings = settings or S.load()
    n = int(range_days or settings["rangeDays"])
    if n not in C.RANGE_DAYS_CHOICES:
        raise Invalid(f"배치 기간은 {' · '.join(map(str, C.RANGE_DAYS_CHOICES))}일 중 하나여야 합니다")
    days = slots.day_range(now.date(), n)
    first, last = days[0].isoformat(), days[-1].isoformat()

    all_rows = store.rows(con)
    kept_rows = [r for r in all_rows if is_kept(r, now, first, last)]
    replace = [r for r in all_rows if not is_kept(r, now, first, last)]

    classes, busy = split_events(events)
    busy_all = {d: list(v) for d, v in busy.items()}
    for r in kept_rows:
        if first <= r["date"] <= last:
            busy_all.setdefault(r["date"], []).append(
                {"start": to_min(r["start"]), "end": to_min(r["end"], allow_24=True), "title": r["title"], "kind": "block"})
    free = slots.build(days, classes, busy_all, settings, now)

    tasks = rules.order(todo_tasks(events, all_rows, now, settings, first, last),
                        assignment_tasks(priority, all_rows, now, first, last))
    res = rules.place(tasks, free, settings, now, last)
    targets = [t for t in study_targets(exams) if float(t["percent"]) < 100 and first <= t["date"]]
    study = rules.fill_study(res["free"], targets, settings, kept_study(all_rows, now, first, last)) \
        if settings["fillStudy"] else []
    planned = sorted(res["blocks"] + study, key=lambda b: (b["date"], b["start"], b["key"]))

    # 미리보기에서 뺀 블록 (F8-R23 · S04) — 나머지 배치는 그대로 두고, 뺀 과제·할 일 시간은 미배치로 옮긴다.
    # 공부 블록은 채우기라 빼도 미배치로 적지 않는다 — 그 공강이 빈 채로 남는다.
    drop = set(exclude or ())
    blocks = [b for b in planned if b["key"] not in drop]
    gone: dict[str, dict] = {}
    for b in res["blocks"]:
        if b["key"] in drop:
            g = gone.setdefault(b["refId"], {"title": b["title"], "minutes": 0, "type": b["taskType"],
                                              "course": b["course"], "href": b.get("href")})
            g["minutes"] += b["minutes"]
    unplaced = list(res["unplaced"])
    for ref, g in gone.items():
        unplaced.append({
            "refId": ref, "taskType": g["type"], "title": g["title"], "course": g["course"],
            "remainingMinutes": g["minutes"], "totalMinutes": g["minutes"], "reasonKey": "excluded",
            "reason": C.REASONS["excluded"], "href": g["href"],
            "text": f"{g['title']} {rules._fmt_len(g['minutes'])} — {C.REASONS['excluded']}",
        })

    day_strs = [d.isoformat() for d in days]
    kept_view = [_row_view(r) for r in kept_rows if first <= r["date"] <= last]
    grid = []
    for d in days:
        ds = d.isoformat()
        grid.append({
            "date": ds, "weekday": C.WEEKDAY_KO[d.weekday()], "weekend": d.weekday() >= 5,
            "classes": [{"start": hhmm(c["start"]), "end": hhmm(c["end"]), "title": c["title"], "canceled": c["canceled"]}
                        for c in sorted(classes.get(ds, []), key=lambda c: c["start"])],
            "events": [{"start": hhmm(b["start"]), "end": hhmm(b["end"]), "title": b["title"], "kind": b["kind"]}
                       for b in sorted(busy.get(ds, []), key=lambda b: b["start"])],
            "slots": [{"start": hhmm(s["start"]), "end": hhmm(s["end"]), "minutes": s["minutes"], "source": s["source"]}
                      for s in free.get(ds, [])],
        })

    has_classes = any(classes.values())
    tasks_n = len(tasks)
    today_d = now.date()
    ranked = sorted(targets, key=lambda t: (-rules.study_score(t, today_d, 0), t["date"], t["course"], t["examId"]))
    return {
        "range": {"start": first, "end": last, "days": n},
        "days": grid,
        "blocks": blocks,
        "kept": kept_view,
        "unplaced": unplaced,
        "deferred": res["deferred"],
        "dailyTotals": rules.daily_totals(day_strs, blocks, kept_view),
        "totalMinutes": sum(b["minutes"] for b in blocks),
        "studyMinutes": sum(b["minutes"] for b in blocks if b["taskType"] == "study"),
        # 공부 과목 고르는 순서 — 오늘 기준 점수(남은 진도율 ÷ 남은 날수). 화면이 '왜 이 과목인지'를 보여 준다
        "studyTargets": [{"examId": t["examId"], "title": t["title"], "course": t["course"], "color": t["color"],
                          "date": t["date"], "dday": (date.fromisoformat(t["date"]) - today_d).days,
                          "percent": t["percent"], "isAuto": t["isAuto"], "href": t["href"],
                          "score": round(rules.study_score(t, today_d, 0), 4)} for t in ranked],
        "adjustments": rules.adjustments(settings, unplaced),
        "existing": len([r for r in replace if r["placed_by"] == "auto"]),
        "state": {
            "timetable": has_classes,                     # 기간 안에 수업이 하나도 없다 → '시간표 먼저' 안내 (7절)
            "tasks": tasks_n,                             # 과제 · 할 일 수
            "study": len(targets),                        # 공부 블록을 만들 수 있는 시험 수 (진도 100% 제외)
            "fillStudy": bool(settings["fillStudy"]),
            "allUnplaced": tasks_n > 0 and not blocks and bool(unplaced),
        },
        "settings": settings,
        "exclude": sorted(drop),
        "signature": signature(blocks),
        "at": now.isoformat(timespec="seconds"),
    }


# ---------------------------------------------------------------- 등록 (F8-R21)

def register(con: sqlite3.Connection, events: list[dict], exams: list[dict], priority: list[dict],
             expect: Optional[str] = None, at: Optional[str] = None, range_days: Optional[int] = None,
             exclude: Iterable[str] = (), now: Optional[datetime] = None) -> dict:
    """미리보기와 같은 계산을 다시 해서 같은 결과면 등록한다. 자동 배치분(앞으로 · 미완료 · 고정 아님)은 새 결과로 바꾼다.

    at        미리보기를 계산한 시각 — 그 시각으로 다시 계산해야 '지금'이 몇 분 흘러도 같은 결과가 나온다(F5 교훈).
    expect    미리보기 signature — 다르면 Stale (그 사이 수업·일정·마감이 바뀌었다)."""
    real = (now or datetime.now()).replace(microsecond=0)
    when = real
    if at:
        try:
            t = datetime.fromisoformat(at).replace(tzinfo=None)
        except ValueError:
            raise Invalid(f"at 은 ISO 시각이어야 합니다: {at}")
        if t > real + timedelta(minutes=1) or real - t > timedelta(minutes=C.PREVIEW_MAX_AGE_MINUTES):
            raise Stale("미리보기가 오래되었습니다 — 다시 계산해 주세요")
        when = t
    pv = preview(con, events, exams, priority, None, when, range_days, exclude)
    if expect and pv["signature"] != expect:
        raise Stale("미리보기 뒤에 수업·일정·마감이 바뀌었습니다 — 다시 계산해 주세요")
    first, last = pv["range"]["start"], pv["range"]["end"]
    old = [r["id"] for r in store.rows(con) if not is_kept(r, when, first, last) and block_dt(r["date"], r["start"]) >= real]
    removed = store.delete(con, old)
    batch = uuid.uuid4().hex[:12]
    ids = [store.insert(con, b, batch) for b in pv["blocks"]]
    store.touch(con)
    return {"created": len(ids), "removed": removed, "batch": batch, "range": pv["range"],
            "studyCreated": sum(1 for b in pv["blocks"] if b["taskType"] == "study"),
            "unplaced": len(pv["unplaced"]), "totalMinutes": pv["totalMinutes"]}


# ---------------------------------------------------------------- 캘린더 (C1 kind=study · F8-S07 · S08)

def _overlaps(a: tuple[datetime, datetime], b: tuple[datetime, datetime]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


GONE = {
    "assignment": "끝낸 과제입니다 — 지워도 됩니다",
    "todo": "끝낸 할 일입니다 — 지워도 됩니다",
    "study": "시험이 지났거나 진도를 다 채웠습니다 — 지워도 됩니다",
    "exam": "학습 계획에서 빠진 분량입니다",
}


def conflicts_of(rows: list[Any], events: Optional[list[dict]], open_refs: Optional[dict[str, Optional[datetime]]],
                 now: datetime) -> dict[int, str]:
    """충돌 감지 (F8-R31) — 블록 id → 경고 한 줄. 완료했거나 지난 블록은 보지 않는다(R33).

    events     다른 일정 (수업 · 내 일정·시각 있는 할 일 · 시험 — 학사 일정은 보지 않는다) — None 이면 겹침은 보지 않는다
    open_refs  아직 남은 작업 {ref: 기한} — 과제는 마감, 공부는 시험 시작(시각 미정이면 그 날 0시), 할 일은 None.
               None 이면 '끝낸 작업'·'기한 뒤'는 보지 않는다"""
    out: dict[int, str] = {}
    spans = {r["id"]: (block_dt(r["date"], r["start"]), block_dt(r["date"], r["end"])) for r in rows}
    others: list[tuple[datetime, datetime, str, str]] = []
    for ev in events or ():
        p = ev.get("extendedProps") or {}
        kind = p.get("kind")
        if ev.get("allDay") or (kind != "class" and kind not in BUSY_KINDS):
            continue
        if kind == "class" and p.get("state") == "canceled":
            continue
        if kind == "user" and p.get("isTodo") and p.get("done"):
            continue
        s = parse_dt(ev.get("start"))
        if s is None:
            continue
        e = parse_dt(ev.get("end")) or s + timedelta(hours=1)
        others.append((s, e, kind, ev.get("title") or ""))
    for r in rows:
        span = spans[r["id"]]
        if r["done"] or span[1] <= now:
            continue
        msg = None
        for s, e, kind, title in others:
            if _overlaps(span, (s, e)):
                msg = f"{title} 수업과 겹칩니다" if kind == "class" else f"'{title}' 일정과 겹칩니다"
                break
        if msg is None:
            for r2 in rows:
                if r2["id"] != r["id"] and _overlaps(span, spans[r2["id"]]):
                    msg = f"다른 학습 블록 '{r2['title']}'과 겹칩니다"
                    break
        if msg is None and open_refs is not None:
            if r["ref_id"] not in open_refs:
                msg = GONE.get(r["task_type"], "더 할 일이 없는 블록입니다 — 지워도 됩니다")
            else:
                due = open_refs[r["ref_id"]]
                if due is not None and span[1] > due:
                    msg = "시험 뒤에 있습니다" if r["task_type"] == "study" else "마감 뒤에 있습니다"
        if msg:
            out[r["id"]] = msg
    return out


def to_event(r: Any, conflict: Optional[str] = None) -> dict:
    start = block_dt(r["date"], r["start"])
    end = block_dt(r["date"], r["end"])
    v = _row_view(r)
    return {
        "id": v["id"], "title": r["title"], "start": start.isoformat(timespec="seconds"),
        "end": end.isoformat(timespec="seconds"), "allDay": False, "editable": not r["done"],
        "extendedProps": {"kind": "study", **{k: v[k] for k in v if k not in ("id", "title", "date", "start", "end")},
                          "conflict": conflict},
    }


def open_refs_of(exams: Iterable[dict], priority: Iterable[dict],
                 events: Iterable[dict] = ()) -> dict[str, Optional[datetime]]:
    """아직 남은 작업 {ref: 기한} — 충돌 표시('끝낸 작업' · '기한 뒤')에 쓴다."""
    refs: dict[str, Optional[datetime]] = {}
    for x in exams:
        if x.get("percent") is not None and float(x["percent"]) >= 100:
            continue
        refs[x["examId"]] = datetime.fromisoformat(x["date"] + (f"T{x['time']}" if x.get("time") else ""))
    for it in priority:
        refs[it["id"]] = parse_dt(it.get("due"))
    for ev in events:
        p = ev.get("extendedProps") or {}
        if p.get("kind") == "user" and p.get("isTodo") and not p.get("done"):
            refs[f"todo:{ev.get('id')}"] = None
    return refs


# 공부 캘린더에만 두는 블록 — 전체 캘린더(/api/events)에는 넣지 않는다 (F5 D7 과 같은 규칙, 2026-10-07 사용자 요청).
#   'exam' 은 2026-10-06 판의 F5 하루치 배치(옛 블록)다.
STUDY_ONLY = ("study", "exam")


def is_study(r: Any) -> bool:
    return r["task_type"] in STUDY_ONLY


def calendar_events(con: sqlite3.Connection, start: Optional[str] = None, end: Optional[str] = None,
                    events: Optional[list[dict]] = None, open_refs: Optional[dict[str, Optional[datetime]]] = None,
                    now: Optional[datetime] = None) -> list[dict]:
    """/api/events 에 섞는 블록 (kind=study) — **과제 · 할 일 블록만**. 공부 블록은 공부 캘린더에만 있다(study_blocks).
    충돌이면 extendedProps.conflict 에 한 줄 (공부 블록과 겹친 것도 센다 — 같은 시간을 두 번 쓰지 않게)."""
    now = now or datetime.now()
    rows = store.rows(con, start, end)
    flags = conflicts_of(rows, events, open_refs, now) if rows else {}
    return [to_event(r, flags.get(r["id"])) for r in rows if not is_study(r)]


def study_blocks(con: sqlite3.Connection, start: str, end: str,
                 events: Optional[list[dict]] = None, open_refs: Optional[dict[str, Optional[datetime]]] = None,
                 now: Optional[datetime] = None) -> list[dict]:
    """F5 공부 캘린더에 섞을 **공강 공부** 블록 (2026-10-07) — F5 study_calendar 의 블록 모양으로.
    전체 캘린더에는 없으므로 충돌(겹침 · 시험 지남)도 여기 conflict 한 줄로 싣는다.
    체크·삭제는 공부 캘린더가 F8 API(/api/placement/blocks/{pb:n})로 한다."""
    now = now or datetime.now()
    rows = store.rows(con, start, end)
    flags = conflicts_of(rows, events, open_refs, now) if any(is_study(r) for r in rows) else {}
    out = []
    for r in rows:
        if r["task_type"] != "study":
            continue
        v = _row_view(r)
        x = store.extra(r)
        out.append({
            "blockId": v["id"], "date": r["date"], "time": r["start"], "endTime": r["end"], "minutes": r["minutes"],
            "examId": r["ref_id"], "course": r["course"], "color": v["color"],
            "examType": x.get("typeLabel") or "시험", "examDate": x.get("examDate") or r["date"],
            "done": bool(r["done"]), "editable": True, "deletable": True,
            "text": f"{r['course']} 공강 공부 {r['minutes']}분", "reason": r["reason"], "placedBy": r["placed_by"],
            "conflict": flags.get(r["id"]),
        })
    return out


def active_span(con: sqlite3.Connection, start: Optional[str], end: Optional[str],
                now: Optional[datetime] = None, study: bool = False) -> Optional[tuple[str, str]]:
    """충돌을 볼 블록(앞으로 · 미완료)이 있는 날짜 범위 — 없으면 None (다른 일정을 읽지 않아도 된다).
    study=False 면 전체 캘린더에 나가는 과제·할 일 블록만, True 면 공부 캘린더의 공부 블록만 본다."""
    now = now or datetime.now()
    live = [r for r in store.rows(con, start, end)
            if is_study(r) == study and not r["done"] and block_dt(r["date"], r["end"]) > now]
    if not live:
        return None
    return min(r["date"] for r in live), max(r["date"] for r in live)


def conflicts(con: sqlite3.Connection, events: list[dict], open_refs: Optional[dict[str, Optional[datetime]]],
              now: Optional[datetime] = None) -> dict:
    """GET /api/placement/conflicts — 겹친 블록 목록 + 배너 문구 (F8-S08)."""
    now = now or datetime.now()
    rows = store.rows(con, now.date().isoformat())
    flags = conflicts_of(rows, events, open_refs, now)
    items = [{**_row_view(r), "conflict": flags[r["id"]]} for r in rows if r["id"] in flags]
    return {"items": items, "count": len(items),
            "text": f"{len(items)}개 블록이 다른 일정과 겹치거나 더 필요 없습니다" if items else ""}


# ---------------------------------------------------------------- 옮기기 · 완료 · 지우기 (F8-R30 · R33 · R34)

def parse_id(raw: str) -> int:
    s = str(raw or "")
    if s.startswith(C.EVENT_PREFIX):
        s = s[len(C.EVENT_PREFIX):]
    if not s.isdigit():
        raise NotFound(f"학습 블록 id 가 아닙니다: {raw}")
    return int(s)


def _get(con: sqlite3.Connection, raw: str) -> Any:
    r = store.get(con, parse_id(raw))
    if r is None:
        raise NotFound(f"학습 블록이 없습니다: {raw}")
    return r


def _span_from_body(body: dict) -> tuple[str, str, str]:
    """{start, end} ISO (캘린더 끌어 옮기기) 또는 {date, start, end} HH:MM → (날짜, 시작, 끝)."""
    if body.get("allDay") or body.get("all_day"):
        raise Invalid("학습 블록은 종일 일정으로 옮길 수 없습니다 — 시간 칸에 놓아 주세요")
    if "date" in body:
        d = str(body["date"])
        try:
            date.fromisoformat(d)
        except ValueError:
            raise Invalid(f"날짜가 올바르지 않습니다: {d}")
        s, e = to_min(body.get("start")), to_min(body.get("end"), allow_24=True)
        if e <= s:
            raise Invalid("끝이 시작보다 늦어야 합니다")
        return d, hhmm(s), hhmm(e)
    s, e = parse_dt(body.get("start")), parse_dt(body.get("end"))
    if s is None or e is None or e <= s:
        raise Invalid("start · end 는 시각이 있는 ISO 값이어야 하고 끝이 시작보다 늦어야 합니다")
    d = s.date().isoformat()
    day_end = datetime(s.year, s.month, s.day) + timedelta(days=1)
    if e > day_end:
        raise Invalid("학습 블록은 자정을 넘길 수 없습니다")
    em = C.DAY_END if e == day_end else e.hour * 60 + e.minute
    return d, hhmm(s.hour * 60 + s.minute), hhmm(em)


def patch_block(con: sqlite3.Connection, raw: str, body: dict) -> dict:
    """PATCH /api/placement/blocks/{id} — {start, end}(옮기기 → 고정) · {done} · {fixed: false}(고정 풀기)."""
    r = _get(con, raw)
    if not isinstance(body, dict):
        raise Invalid("{start, end} · {done} 모양이어야 합니다")
    fields: dict[str, Any] = {}
    moved = False
    if any(k in body for k in ("start", "end", "date")):
        d, s, e = _span_from_body(body)
        if (d, s, e) != (r["date"], r["start"], r["end"]):
            fields.update({"date": d, "start": s, "end": e,
                           "minutes": to_min(e, allow_24=True) - to_min(s), "placed_by": "user"})
            moved = True
    if "done" in body:
        done = bool(body["done"])
        fields.update({"done": int(done), "done_at": store.now() if done else None})
    if body.get("fixed") is False and not moved:
        fields["placed_by"] = "auto"
    store.update(con, r["id"], fields)
    store.touch(con)
    out = store.get(con, r["id"])
    return {"block": _row_view(out), "event": to_event(out), "fixed": out["placed_by"] == "user", "moved": moved}


def delete_block(con: sqlite3.Connection, raw: str) -> dict:
    r = _get(con, raw)
    store.delete(con, [r["id"]])
    store.touch(con)
    return {"deleted": 1}


def delete_auto(con: sqlite3.Connection, start: Optional[str] = None, end: Optional[str] = None,
                now: Optional[datetime] = None) -> dict:
    """DELETE /api/placement?from=&to= — 기간 안의 **자동 배치 블록만** 지운다. 고정·완료·이미 시작한 블록은 남긴다 (F8-S10)."""
    now = now or datetime.now()
    for v, what in ((start, "시작"), (end, "끝")):
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise Invalid(f"{what} 날짜가 올바르지 않습니다: {v}")
    if start and end and end < start:
        raise Invalid("끝 날짜가 시작보다 앞입니다")
    ids = [r["id"] for r in store.rows(con, start, end)
           if r["placed_by"] == "auto" and not r["done"] and block_dt(r["date"], r["start"]) >= now]
    n = store.delete(con, ids)
    kept = len(store.rows(con, start, end))
    if n:
        store.touch(con)
    return {"deleted": n, "kept": kept}


# ---------------------------------------------------------------- 브리핑 · 상태

def today(con: sqlite3.Connection, now: Optional[datetime] = None) -> dict:
    """오늘 학습 블록 — F10 아침 브리핑 · F9 대화가 읽는다. '19:00 운영체제 중간고사 공부 · 21:00 품질 보고서'."""
    now = now or datetime.now()
    rows = store.rows(con, now.date().isoformat(), now.date().isoformat())
    items = [_row_view(r) for r in rows]
    left = [b for b in items if not b["done"] and block_dt(b["date"], b["end"]) > now]
    return {"date": now.date().isoformat(), "blocks": items,
            "totalMinutes": sum(b["minutes"] for b in items),
            "remainingMinutes": sum(b["minutes"] for b in left),
            "text": " · ".join(f"{b['start']} {b['title']}" for b in left)}


def status_summary(con: sqlite3.Connection, now: Optional[datetime] = None) -> dict:
    """/api/status 의 placement 칸 — 1분마다 불리므로 다른 일정을 읽지 않는다(충돌은 /api/events 가 단다)."""
    now = now or datetime.now()
    rows = store.rows(con, now.date().isoformat())
    future = [r for r in rows if not r["done"] and block_dt(r["date"], r["end"]) > now]
    t = today(con, now)
    nxt = min((r for r in future if not is_study(r)), key=lambda r: (r["date"], r["start"]), default=None)
    return {
        "available": True, "updatedAt": store.updated_at(con),
        "upcoming": len(future), "auto": sum(1 for r in future if r["placed_by"] == "auto"),
        "fixed": sum(1 for r in future if r["placed_by"] == "user"),
        "todayCount": len(t["blocks"]), "todayMinutes": t["totalMinutes"], "todayText": t["text"],
        "next": _row_view(nxt) if nxt else None,
    }
