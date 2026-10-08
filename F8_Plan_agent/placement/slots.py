"""공강(빈 시간) 계산 — 순수 함수 (F8 5절 ①, F8-R01~R08 — 2026-10-07 개정).

    후보 구간
      낮 시간대(기본 09:00~18:00) 하나 — 저녁 19:00~24:00 은 F5 시험 공부 계획 전용이라 쓰지 않는다
    빼기
      − 수업 (+ 앞뒤 여유 10분)        휴강 회차는 수업이 아니다 (R08)
      − 기존 일정(시각이 있는 내 일정·할 일 · 시험 · 남겨 두는 블록) — 학사 일정은 보지 않는다(내 일정에 넣은 것만)
      − 점심 (기본 12:00~13:00, 설정으로 끄기)
      − 오늘이면 지금 이전
    버리기
      − 최소 길이(기본 30분) 미만 구간

남은 구간이 전부 공강이다 — 수업 사이뿐 아니라 첫 수업 전 · 마지막 수업 뒤 · 수업이 없는 날(공강 날)도.
주말은 설정(useWeekend, 기본 끔)을 따른다.
시각은 그 날 00:00 부터의 **분**(int)으로 다룬다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Iterable, Optional

from . import config as C
from .settings import minutes

Interval = tuple[int, int]


def merge(ivs: Iterable[Interval]) -> list[Interval]:
    out: list[list[int]] = []
    for s, e in sorted(i for i in ivs if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [(s, e) for s, e in out]


def subtract(base: Interval, cuts: Iterable[Interval]) -> list[Interval]:
    """base 구간에서 cuts 를 뺀 조각들 (시작 순)."""
    pieces = [base]
    for cs, ce in merge(cuts):
        nxt = []
        for s, e in pieces:
            if ce <= s or cs >= e:
                nxt.append((s, e))
                continue
            if cs > s:
                nxt.append((s, cs))
            if ce < e:
                nxt.append((ce, e))
        pieces = nxt
    return [p for p in pieces if p[1] > p[0]]


def round_up(now: datetime, step: int = C.NOW_ROUND_MINUTES) -> int:
    """지금 → 오늘 분. 10분 단위로 올린다(14:03 → 14:10). 초가 있으면 다음 분으로 본다."""
    m = now.hour * 60 + now.minute + (1 if now.second or now.microsecond else 0)
    return min(-(-m // step) * step, C.DAY_END)


def day_range(start: date, n: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n)]


def day_slots(d: date, classes: list[dict], busy: list[dict], settings: dict,
              now: Optional[datetime] = None) -> list[dict]:
    """하루의 공강 [{start, end, minutes, source: gap}] — 시작 순.

    classes: 그 날 수업 [{start, end, canceled}] (분) · busy: 그 날 차지된 구간 [{start, end}] (분)."""
    if d.weekday() >= 5 and not settings["useWeekend"]:
        return []
    if now is not None and d < now.date():
        return []
    window = (minutes(settings["dayStart"]), minutes(settings["dayEnd"]))
    live = merge((c["start"], c["end"]) for c in classes if not c.get("canceled"))
    buf = int(settings["bufferMinutes"])
    cuts: list[Interval] = [(s - buf, e + buf) for s, e in live]
    cuts += [(b["start"], b["end"]) for b in busy]
    if settings["lunchBreak"]:
        cuts.append((minutes(settings["lunchStart"]), minutes(settings["lunchEnd"])))
    if now is not None and d == now.date():
        cuts.append((0, round_up(now)))
    min_len = int(settings["minSlotMinutes"])
    return [{"start": s, "end": e, "minutes": e - s, "source": "gap"}
            for s, e in subtract(window, cuts) if e - s >= min_len]          # 30분 미만은 버린다 (R06)


def build(days: list[date], classes: dict[str, list[dict]], busy: dict[str, list[dict]], settings: dict,
          now: Optional[datetime] = None) -> dict[str, list[dict]]:
    """기간 전체의 공강 — {날짜: [슬롯]}. classes · busy 는 날짜(ISO) → 그 날 구간."""
    return {d.isoformat(): day_slots(d, classes.get(d.isoformat(), []), busy.get(d.isoformat(), []), settings, now)
            for d in days}
