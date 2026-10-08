"""오늘 남은 시간 (F7-R21 · 5절) — `지금 해야 함` 합계와 견줄 값.

    오늘 남은 시간 = 취침 시각 − 지금 − 오늘 남은 수업·일정 시간 − 오늘 남은 학습 분량

  - 수업(F3 kind=class, 휴강 제외) · 내 일정(C1 kind=user, 종일·할 일 제외) · 시험(F5 kind=exam)이 **지금 ~ 취침** 사이에
    차지하는 시간을 겹침 없이 더한다(같은 시간에 두 일정이 있어도 한 번만 뺀다).
  - 학습 블록(F5)은 날짜 단위라 시각이 없다 → 오늘 아직 체크하지 않은 분량(분)만 덩어리로 뺀다.
  - 과제 마감(deadline) · 학사 일정(academic) · 종일 일정은 시간을 차지하지 않는다.

'오늘'은 취침 시각 기준이다. 새벽 5시 전이면 아직 어젯밤으로 본다 — 새벽 1시에 연 화면이 '오늘 남은 23시간'을 보여 주면 안 된다.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterable, Optional

from . import config as C
from . import settings as S

BUSY_KINDS = {"class", "user", "exam"}
UNTIMED_EVENT_HOURS = 1.0               # 끝 시각이 없는 일정(시험 등)은 한 시간으로 본다
DAY_TURNS_AT = 5                        # 새벽 5시 전이면 아직 '어젯밤'


def bed_at(now: datetime, bed_time: str) -> datetime:
    """지금이 속한 밤의 취침 시각."""
    night = now.date() if now.hour >= DAY_TURNS_AT else (now - timedelta(days=1)).date()
    return datetime.combine(night, datetime.min.time()) + timedelta(minutes=S.bed_minutes(bed_time))


def _parse(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        d = datetime.fromisoformat(str(s).replace(" ", "T").replace("Z", ""))
    except ValueError:
        return None
    return d.replace(tzinfo=None)


def busy_intervals(events: Iterable[dict], start: datetime, end: datetime) -> list[dict]:
    """[start, end) 안에서 시간을 차지하는 일정 — 잘라 낸 구간과 이름."""
    out = []
    for ev in events or ():
        p = ev.get("extendedProps") or {}
        kind = p.get("kind")
        if kind not in BUSY_KINDS or ev.get("allDay"):
            continue
        if kind == "class" and p.get("state") == "canceled":
            continue
        if kind == "user" and p.get("isTodo"):
            continue
        s = _parse(ev.get("start"))
        if s is None:
            continue
        e = _parse(ev.get("end")) or s + timedelta(hours=UNTIMED_EVENT_HOURS)
        a, b = max(s, start), min(e, end)
        if b > a:
            out.append({"title": ev.get("title") or "", "kind": kind, "start": a, "end": b})
    out.sort(key=lambda x: (x["start"], x["end"]))
    return out


def union_hours(intervals: list[dict]) -> float:
    total, cur_s, cur_e = 0.0, None, None
    for it in intervals:
        if cur_e is None or it["start"] > cur_e:
            if cur_e is not None:
                total += (cur_e - cur_s).total_seconds()
            cur_s, cur_e = it["start"], it["end"]
        else:
            cur_e = max(cur_e, it["end"])
    if cur_e is not None:
        total += (cur_e - cur_s).total_seconds()
    return total / 3600


def budget(now: datetime, settings: dict, events: Iterable[dict] = (), study_minutes: float = 0.0,
           need_hours: float = 0.0) -> dict:
    """오늘 남은 시간 막대(F7-S05)에 쓰는 값."""
    bed = bed_at(now, settings.get("bedTime") or C.DEFAULT_BED_TIME)
    until_bed = max(0.0, (bed - now).total_seconds() / 3600)
    busy = busy_intervals(events, now, bed) if until_bed > 0 else []
    busy_h = min(until_bed, union_hours(busy))
    study_h = min(until_bed - busy_h, max(0.0, float(study_minutes or 0)) / 60)
    left = max(0.0, until_bed - busy_h - study_h)
    return {
        "bedTime": settings.get("bedTime") or C.DEFAULT_BED_TIME,
        "bedAt": bed.isoformat(timespec="minutes"),
        "untilBedHours": round(until_bed, 2),
        "busyHours": round(busy_h, 2),
        "studyHours": round(study_h, 2),
        "leftHours": round(left, 2),
        "needHours": round(need_hours, 2),
        "over": need_hours > left + 1e-9,
        "busy": [{"title": b["title"], "kind": b["kind"], "start": b["start"].isoformat(timespec="minutes"),
                  "end": b["end"].isoformat(timespec="minutes")} for b in busy],
    }
