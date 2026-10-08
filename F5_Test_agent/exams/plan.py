"""계획 계산기 — 순수 함수. `compute(exam, options, today) → 계획 한 벌` (F5 5절, F5-R20~R26).

DB 도, 파일도, 네트워크도 건드리지 않는다. 같은 입력이면 항상 같은 결과다 — 그래서 미리보기와 등록이
**같은 계산기**를 쓸 수 있다(등록만 부수효과를 갖는다, Frontend-Route 10-7 주석).

    학습 가능일  = 시작일(기본 오늘) … 시험 전날
      − 마무리 복습일 R (중간·기말 2일 / 나머지 1일, 설정 가능)   ← 가능일의 **끝쪽**에서 뗀다
      − 사용자 제외일                                            ← 0쪽으로 두고 나머지에 재분배
      = 학습일 D

    총 분량      = Σ(범위 내 자료 쪽수)   ← F4. 없으면 사용자 입력(쪽 또는 분)
    쪽당 시간    = 난이도 계수 (쉬움 1.5 / 보통 2.5 / 어려움 4분)
    하루 분량    = ceil(총 분량 ÷ D)      ← 균등 분할, 반올림 오차는 **마지막 날이 흡수**한다 (9절 '정확성')
    하루 시간    = 하루 분량 × 쪽당 시간

시간 배치 (2026-10-06 사용자 요청 D11)
    총 공부 시간 = 남은 분량 × 쪽당 시간. 사용자가 학습일마다 **공부할 시간을 직접 정할 수 있다**(`dayMinutes`).
    시간을 정한 날(고정)이 먼저 그 시간만큼 쪽수를 가져가고, **손대지 않은 날이 남은 분량을 고르게 나눈다** —
    그래서 한 날을 바꾸면 나머지가 따라 움직이고 합계는 늘 총 분량과 같다.
    모든 날을 고정했는데 합이 모자라면 `short`(등록 불가 + '남은 시간 마지막 날에 더하기'·'고르게 나누기'),
    넘치면 날짜 순으로 잘라 넣고 알린다. 쪽 반올림 오차(고정한 날마다 1쪽까지)는 경고하지 않고 흡수한다.
    마무리 복습일 = 전체 훑기(총 시간 × 0.3 ÷ R) + (선택) 예상 문제 풀이

판정
    학습일 D ≤ 0 (시험이 내일·오늘) → no_time — 계획 대신 남은 시간에 볼 우선순위
    직접 정한 시간이 모자람         → short   — 등록 불가 + 조정안
    그 외                          → ok

하루 학습 시간 기준(4시간)은 없다 — 2026-10-07 사용자 요청으로 '하루 N시간이 필요합니다'(over) · 여러 시험 합산(overlap)
경고와 그 조정안(학습일 늘리기 · 분량 줄이기 · 복습일 늘리기 …)을 지웠다. 하루에 몇 시간을 할지는 D11 시간 배치에서
사용자가 정하고, 그 시간은 저녁 시간대(기본 19:00~24:00)에 이어서 놓인다(service.study_calendar).
경고는 level 과 message 를 같이 준다 (9절 '접근성').
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Optional

from . import config as C

WEEKDAYS = "월화수목금토일"

VERDICT_LABEL = {
    "ok": "정상",
    "no_time": "시간 없음",
    "short": "배치 시간 부족",
}


class Invalid(ValueError):
    """계획 옵션이 규칙에 어긋난다 (422)."""


# ---------------------------------------------------------------- 옵션 정리

def normalize(exam: dict, options: Optional[dict] = None) -> dict:
    """화면·명령줄에서 온 옵션을 계산기가 쓰는 모양으로. 빠진 값은 기본값, 이상한 값은 Invalid."""
    o = dict(options or {})
    unit = o.get("unit") or "pages"
    if unit not in ("pages", "minutes"):
        raise Invalid(f"단위는 pages 또는 minutes 입니다: {unit!r}")

    difficulty = o.get("difficulty") or C.DEFAULT_DIFFICULTY
    if difficulty not in C.DIFFICULTY:
        raise Invalid(f"난이도는 {', '.join(C.DIFFICULTY)} 중 하나입니다: {difficulty!r}")
    page_minutes = o.get("pageMinutes")
    if page_minutes is None:
        page_minutes = C.page_minutes_for(difficulty)
    page_minutes = float(page_minutes)
    if not 0 < page_minutes <= C.PAGE_MINUTES_MAX:
        raise Invalid(f"쪽당 시간은 0보다 크고 {C.PAGE_MINUTES_MAX:g}분 이하여야 합니다: {page_minutes:g}")

    total_pages = _nonneg(o.get("totalPages"), "총 쪽수")
    total_minutes = _nonneg(o.get("totalMinutes"), "총 시간")
    if unit == "pages":
        if not total_pages:
            raise Invalid("총 쪽수를 넣어 주세요 — 범위 안에 인덱싱된 자료가 없으면 직접 입력합니다 (F5-R11)")
        total_minutes = _mins(total_pages * page_minutes)
    else:
        if not total_minutes:
            raise Invalid("총 학습 시간(분)을 넣어 주세요")
        total_pages = 0

    review_days = _int(o.get("reviewDays"), C.review_days_for(exam.get("type") or "etc"))
    if not 0 <= review_days <= C.MAX_REVIEW_DAYS:
        raise Invalid(f"마무리 복습일은 0~{C.MAX_REVIEW_DAYS}일 사이입니다: {review_days}")
    excluded = sorted({_date_str(d, "제외일") for d in (o.get("excludedDates") or [])})
    if len(excluded) > C.MAX_EXCLUDED:
        raise Invalid(f"제외일이 너무 많습니다 ({len(excluded)}개)")

    include_quiz = bool(o.get("includeQuiz"))
    quiz_count = _int(o.get("quizCount"), C.DEFAULT_QUIZ_COUNT if include_quiz else 0)
    if quiz_count < 0 or quiz_count > 500:
        raise Invalid(f"예상 문제 수가 이상합니다: {quiz_count}")
    if not include_quiz:
        quiz_count = 0

    return {
        "unit": unit, "totalPages": total_pages, "totalMinutes": total_minutes,
        "pageMinutes": page_minutes, "difficulty": difficulty,
        "reviewDays": review_days, "excludedDates": excluded,
        "includeQuiz": include_quiz, "quizCount": quiz_count,
        "startDate": _date_str(o["startDate"], "시작일") if o.get("startDate") else None,
        # 2026-10-01 — 날짜가 주 옵션이다: 며칠 공부할지(studyDays) 또는 어느 날 공부할지(studyDates, 사용자가 달력에서 고름)
        "studyDays": _study_count(o.get("studyDays")),
        "studyDates": sorted({_date_str(d, "학습 날짜") for d in (o.get("studyDates") or [])}),
        # 2026-10-06 — 학습일마다 사용자가 정한 공부 시간(분). 정하지 않은 날은 남은 분량을 고르게 나눈다
        "dayMinutes": _day_minutes(o.get("dayMinutes")),
        "scopeWeeks": sorted({int(w) for w in (o.get("scopeWeeks") or [])}),
        "scopeMaterialIds": list(o.get("scopeMaterialIds") or []),
    }


def _mins(x: float) -> int:
    """분은 **반올림(0.5 는 올림)** — 파이썬 기본 round 는 22.5 를 22 로 만든다(짝수 쪽으로)."""
    return int(x + 0.5)


def _day_minutes(v: Any) -> dict[str, int]:
    """{날짜: 분} — 학습일마다 직접 정한 공부 시간. 0분이면 그 날은 쉰다(블록을 만들지 않는다)."""
    if not v:
        return {}
    if not isinstance(v, dict):
        raise Invalid("dayMinutes 는 {날짜: 분} 모양입니다")
    out: dict[str, int] = {}
    for k, m in v.items():
        when = _date_str(k, "시간을 정한 날")
        n = _int(m, 0)
        if not 0 <= n <= 24 * 60:
            raise Invalid(f"하루 공부 시간은 0분~24시간 사이입니다: {when} {n}분")
        out[when] = n
    return dict(sorted(out.items()))


def _study_count(v: Any) -> Optional[int]:
    if v is None or v == "" or v == 0:
        return None
    n = _int(v, 0)
    if not 1 <= n <= 200:
        raise Invalid(f"학습일 수는 1~200일 사이입니다: {n}")
    return n


def _int(v: Any, default: int) -> int:
    if v is None or v == "":
        return default
    try:
        return int(v)
    except (TypeError, ValueError):
        raise Invalid(f"숫자가 아닙니다: {v!r}")


def _nonneg(v: Any, what: str) -> int:
    n = _int(v, 0)
    if n < 0:
        raise Invalid(f"{what}는 0 이상이어야 합니다: {n}")
    return n


def date_str(v: Any, what: str) -> str:
    """YYYY-MM-DD 로 정리한다. 형식이 틀리면 Invalid."""
    try:
        return date.fromisoformat(str(v)[:10]).isoformat()
    except ValueError:
        raise Invalid(f"{what} 형식이 잘못됐습니다: {v!r} (YYYY-MM-DD)")


_date_str = date_str


# ---------------------------------------------------------------- 날짜 나누기

def _span(start: date, last: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((last - start).days + 1)]


def split_days(exam_date: date, today: date, review_days: int, excluded: set[str],
               start_date: Optional[date] = None, study_dates: Optional[list[str]] = None,
               study_count: Optional[int] = None, blocked: Optional[set[str]] = None) -> dict:
    """가능일 → (학습일, 마무리 복습일, 제외된 날).

    - study_dates 를 주면 **그 날들이 학습일**이다(사용자가 달력에서 고름). 복습일은 남은 날 중 시험에 가까운 날부터.
    - study_count 를 주면 마무리 복습 **직전 N일**을 학습일로 잡는다('3일' → 시험 직전 복습일 바로 앞 3일).
    - 둘 다 없으면 복습일을 뺀 모든 날.
    blocked = 이미 완료한 날(재조정) — 다시 나누지 않는다.
    """
    blocked = blocked or set()
    start = max(today, start_date or today)
    available = _span(start, exam_date - timedelta(days=1)) if start < exam_date else []
    open_days = [d for d in available if d.isoformat() not in blocked]
    if study_dates:
        picked = {s for s in study_dates}
        study = [d for d in open_days if d.isoformat() in picked]
        rest = [d for d in open_days if d.isoformat() not in picked and d.isoformat() not in excluded]
        review = sorted(rest[-review_days:]) if review_days else []
        pool = len([d for d in open_days if d not in set(review)])
        skipped = [d for d in available if d.isoformat() in excluded and d.isoformat() not in picked]
    else:
        usable = [d for d in open_days if d.isoformat() not in excluded]
        review = sorted(usable[-review_days:]) if review_days else []
        review_set = set(review)
        candidates = [d for d in usable if d not in review_set]
        pool = len(candidates)
        study = candidates[-study_count:] if study_count else candidates
        skipped = [d for d in available if d.isoformat() in excluded and d.isoformat() not in blocked]
    return {"start": start, "available": available, "study": study, "review": review, "excluded": skipped,
            "pool": pool, "picked": bool(study_dates)}


def _even(total: int, n: int) -> list[int]:
    """총량을 n 일로 균등 분할 — 하루치는 ceil, **마지막 날이 나머지를 흡수**한다(합이 총량과 같다).

    총량이 날수보다 적으면 앞쪽 날만 채우고 남는 날은 0 을 돌려준다(빈 블록은 service 가 버린다)."""
    if n <= 0:
        return []
    per = math.ceil(total / n)
    out, left = [], total
    for _ in range(n):
        take = min(per, left)
        out.append(max(take, 0))
        left -= take
    return out


def allocate(total: int, dates: list[str], pins: dict[str, int], per_unit: float) -> dict:
    """학습일에 분량(쪽 또는 분)을 나눈다 — **시간을 정한 날 먼저, 나머지 날이 남은 분량을 고르게** (D11).

    pins = {날짜: 분} (학습일이 아닌 날의 값은 버린다). 고정한 날의 쪽수 = 분 ÷ 쪽당 시간(반올림).
    돌려주는 것: shares {날짜: 단위}, minutes {날짜: 분}, pinned [날짜], unassigned(모자란 단위), over(넘친 단위)
    고정한 날마다 1단위까지의 반올림 오차는 마지막 고정일이 흡수한다 — 경고하지 않는다.
    """
    pins = {d: m for d, m in pins.items() if d in set(dates)}
    pinned = [d for d in dates if d in pins]
    auto = [d for d in dates if d not in pins]
    want = {d: _mins(pins[d] / per_unit) for d in pinned}
    slack = len(pinned)                                   # 반올림 오차로 볼 만큼 (고정한 날마다 1단위)
    shares: dict[str, int] = {}
    minutes: dict[str, int] = {}
    over = 0
    room = total
    for d in pinned:
        take = min(want[d], room)
        over += want[d] - take
        room -= take
        shares[d] = take
        minutes[d] = pins[d]
    if over > slack:                                       # 정말로 넘쳤다 — 잘린 날은 실제로 넣은 만큼의 시간으로
        for d in pinned:
            if shares[d] < want[d]:
                minutes[d] = _mins(shares[d] * per_unit)
    else:
        over = 0
    for d, amount in zip(auto, _even(room, len(auto))):
        shares[d] = amount
        minutes[d] = _mins(amount * per_unit)
    unassigned = room if not auto else 0
    if 0 < unassigned <= slack and pinned:                # 반올림으로 남은 몇 쪽 — 마지막 고정일에 얹는다
        shares[pinned[-1]] += unassigned
        unassigned = 0
    return {"shares": shares, "minutes": minutes, "pinned": pinned, "pins": {d: pins[d] for d in pinned},
            "unassigned": unassigned, "over": over}


def _fit_pins(pins: dict[str, int], need: int) -> dict[str, int]:
    """넘친 고정 시간을 필요한 시간에 맞게 같은 비율로 줄인다 — 합이 정확히 need 가 되게 마지막 날이 맞춘다."""
    total = sum(pins.values())
    if not total:
        return dict(pins)
    keys = list(pins)
    out = {d: int(pins[d] * need / total) for d in keys}
    out[keys[-1]] += need - sum(out.values())
    return out


# ---------------------------------------------------------------- 본체

def compute(exam: dict, options: Optional[dict] = None, today: Optional[date] = None,
            carry: Optional[dict] = None) -> dict:
    """시험 + 옵션 → 날짜별 분량 표와 경고·조정안. 저장하지 않는다 (미리보기가 그대로 쓴다).

    carry      = {'pages','minutes','days'} — 재조정에서 **이미 완료한 분량**을 빼고 나머지만 다시 나눌 때
    """
    o = normalize(exam, options)
    today = today or date.today()
    exam_date = date.fromisoformat(exam["date"])
    start_date = date.fromisoformat(o["startDate"]) if o["startDate"] else None
    excluded = set(o["excludedDates"])
    carry = carry or {}
    done_pages = max(0, int(carry.get("pages") or 0))
    done_minutes = max(0, int(carry.get("minutes") or 0))
    carry_days = list(carry.get("days") or [])

    # 이미 완료한 날(carry)은 다시 나누지 않는다 — 안 그러면 그 날에 블록이 둘 생긴다
    carry_dates = {d["date"] for d in carry_days}
    parts = split_days(exam_date, today, o["reviewDays"], excluded, start_date,
                       o["studyDates"], o["studyDays"], blocked=carry_dates)
    study, review = parts["study"], parts["review"]

    unit_total = o["totalPages"] if o["unit"] == "pages" else o["totalMinutes"]
    per_unit = o["pageMinutes"] if o["unit"] == "pages" else 1.0
    left = max(0, unit_total - done_pages if o["unit"] == "pages" else unit_total - done_minutes)

    study_iso = [d.isoformat() for d in study]
    alloc = allocate(left, study_iso, o["dayMinutes"], per_unit)
    shares = [alloc["shares"][d] for d in study_iso]
    days: list[dict] = list(carry_days)
    for d, amount in zip(study, shares):
        iso = d.isoformat()
        if amount <= 0:
            continue                                        # 분량이 남지 않은 날(0분으로 정한 날 포함)은 블록을 만들지 않는다
        days.append(_day(d, pages=amount if o["unit"] == "pages" else 0,
                         minutes=alloc["minutes"][iso], kind="study", pinned=iso in alloc["pins"]))

    # 마무리 복습일 — 전체 훑기 + (선택) 예상 문제 풀이 (F5-R13·R20)
    skim_total = _mins(unit_total * per_unit * C.REVIEW_SKIM_RATIO)
    quiz_shares = _even(o["quizCount"], len(review)) if review else []
    for i, d in enumerate(review):
        quiz = quiz_shares[i] if i < len(quiz_shares) else 0
        minutes = _mins(skim_total / len(review)) + quiz * C.QUIZ_MINUTES_PER_ITEM
        days.append(_day(d, pages=0, minutes=minutes, kind="review", quiz=quiz))
    for d in parts["excluded"]:
        days.append(_day(d, pages=0, minutes=0, kind="excluded"))
    days.sort(key=lambda x: x["date"])

    daily_pages = shares[0] if shares else 0
    daily_minutes = _mins(daily_pages * per_unit) if o["unit"] == "pages" else (shares[0] if shares else 0)
    real = [d for d in days if d["kind"] != "excluded"]
    peak_day = max(real, key=lambda d: d["minutes"], default=None)
    peak = peak_day["minutes"] if peak_day else 0
    mine = [d for d in real if d["kind"] == "study" and not d["done"]]

    need = _mins(left * per_unit)
    allocation = {
        "needMinutes": need,                               # 총 공부 시간 (복습 제외) — 남은 분량 × 쪽당 시간
        "assignedMinutes": sum(d["minutes"] for d in mine),
        "unassignedUnits": alloc["unassigned"],
        "unassignedMinutes": _mins(alloc["unassigned"] * per_unit),
        "overMinutes": _mins(alloc["over"] * per_unit),
        "pinnedDates": alloc["pinned"],
        "autoDates": [d for d in study_iso if d not in alloc["pins"]],
        "reviewMinutes": sum(d["minutes"] for d in real if d["kind"] == "review"),
    }
    allocation["fixes"] = _allocation_fixes(alloc, need, study_iso, per_unit)

    verdict, warnings = _judge(o, exam, parts, left, alloc, per_unit)
    out = {
        "examId": exam.get("id"), "courseId": exam.get("courseId"), "courseName": exam.get("courseName", ""),
        "examDate": exam_date.isoformat(), "examTime": exam.get("time") or "",
        "examType": exam.get("type"), "examTypeLabel": C.type_label(exam.get("type") or "etc"),
        "state": "draft",
        **{k: o[k] for k in ("unit", "totalPages", "totalMinutes", "pageMinutes", "difficulty",
                             "reviewDays", "excludedDates", "includeQuiz", "quizCount",
                             "scopeWeeks", "scopeMaterialIds")},
        "startDate": parts["start"].isoformat(),
        "availableDays": len(parts["available"]),
        "studyDays": len(study),
        "studyDates": [d.isoformat() for d in study],
        "studyDatesPicked": parts["picked"],          # 사용자가 달력에서 날짜를 골랐나
        "studyPool": parts["pool"],                   # 학습일로 쓸 수 있는 날 수 (학습일 수 입력의 최댓값)
        "selectableDates": [d.isoformat() for d in parts["available"] if d.isoformat() not in carry_dates],
        "reviewDayDates": [d.isoformat() for d in review],
        "dailyPages": daily_pages,
        "dailyMinutes": daily_minutes,
        # 시간을 직접 정했으면 날마다 다르다 — 화면은 '하루 1시간~3시간'처럼 범위로 보여 준다
        "dayRange": {"minMinutes": min((d["minutes"] for d in mine), default=0),
                     "maxMinutes": max((d["minutes"] for d in mine), default=0),
                     "minPages": min((d["pages"] for d in mine), default=0),
                     "maxPages": max((d["pages"] for d in mine), default=0)},
        "dayMinutes": alloc["pins"],                  # 실제로 쓴 고정 시간 (학습일이 아닌 날의 값은 빠진다)
        "allocation": allocation,
        "days": days,
        "totals": {
            "pages": sum(d["pages"] for d in real),
            "minutes": sum(d["minutes"] for d in real),
            "quiz": sum(d["quiz"] for d in real),
            "blocks": len([d for d in real if d["minutes"] or d["pages"]]),
        },
        "carried": {"pages": done_pages, "minutes": done_minutes, "days": len(carry_days)},
        "peakMinutes": peak,
        "verdict": verdict,
        "verdictLabel": VERDICT_LABEL[verdict],
        "warnings": warnings,
        "peakDate": peak_day["date"] if peak_day else None,
        "adjustments": allocation["fixes"][:4],
        # 시간을 정한 날만으로 분량을 다 담지 못했으면(short) 등록하지 않는다 — 계획에서 빠지는 쪽이 생긴다
        "canRegister": bool([d for d in real if d["minutes"] or d["pages"]]) and verdict != "short",
    }
    return out


def _day(d: date, pages: int, minutes: int, kind: str, quiz: int = 0, pinned: bool = False) -> dict:
    return {"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "pages": pages, "minutes": minutes,
            "kind": kind, "quiz": quiz, "done": False, "moved": False, "pinned": pinned}


def _allocation_fixes(alloc: dict, need: int, study_iso: list[str], per_unit: float) -> list[dict]:
    """시간 배치가 어긋났을 때 한 번에 고치는 조정안 — 미리보기·옵션 화면이 같은 것을 쓴다."""
    pins = alloc["pins"]
    if not pins:
        return []
    even = {"key": "even_split", "label": "고르게 나누기",
            "detail": "직접 정한 시간을 풀고 학습일마다 같은 시간으로 나눕니다", "apply": {"dayMinutes": {}}}
    if alloc["unassigned"]:
        last = study_iso[-1]
        missing = max(need - sum(pins.values()), _mins(alloc["unassigned"] * per_unit))
        return [{"key": "fill_last", "label": f"남은 시간을 {_md(last)}에 더하기",
                 "detail": f"{_md(last)} 공부 시간을 {_hm(pins.get(last, 0))} → {_hm(pins.get(last, 0) + missing)}으로 늘립니다",
                 "apply": {"dayMinutes": {**pins, last: min(24 * 60, pins.get(last, 0) + missing)}}}, even]
    if alloc["over"]:
        return [{"key": "fit_pins", "label": "정한 시간 줄이기",
                 "detail": f"직접 정한 시간을 같은 비율로 줄여 총 {_hm(need)}에 맞춥니다",
                 "apply": {"dayMinutes": _fit_pins(pins, need)}}, even]
    return []


def _judge(o: dict, exam: dict, parts: dict, left: int, alloc: Optional[dict] = None,
           per_unit: float = 1.0) -> tuple[str, list[dict]]:
    """판정 + 경고. 하루 학습 시간 기준(4시간)은 보지 않는다 (2026-10-07)."""
    warnings: list[dict] = []
    study, available = parts["study"], parts["available"]
    alloc = alloc or {"unassigned": 0, "over": 0, "pins": {}}
    verdict = "ok"

    if not available:
        verdict = "no_time"
        # 가능일이 비는 것은 시작일이 이미 시험일 이후라는 뜻이다 — 오늘이 시험일이거나 시험이 지났다.
        when = "시험일이 지났습니다" if exam["date"] < parts["start"].isoformat() else "시험이 오늘입니다"
        warnings.append({"level": "error", "code": "no_time",
                         "message": f"{when} — 계획을 나눌 날이 없습니다. "
                                    f"남은 시간에는 요약과 예상 문제를 보세요"})
    elif not study:
        verdict = "no_time"
        warnings.append({"level": "error", "code": "no_study_days",
                         "message": f"학습일이 없습니다 — 남은 {len(available)}일이 모두 마무리 복습일이거나 제외일입니다. "
                                    f"복습일을 줄이거나 제외일을 지우면 분량이 나뉩니다"})
    elif alloc["unassigned"]:
        verdict = "short"
        miss = _mins(alloc["unassigned"] * per_unit)
        what = f"{alloc['unassigned']}쪽({_hm(miss)})" if o["unit"] == "pages" else _hm(miss)
        warnings.append({"level": "error", "code": "unassigned",
                         "message": f"{what}이 아직 어느 날에도 배치되지 않았습니다 — "
                                    f"남은 시간을 어느 날에 더하거나 고르게 나누세요"})

    if alloc["over"] and verdict != "no_time":
        warnings.append({"level": "warn", "code": "over_assigned",
                         "message": f"직접 정한 시간이 필요한 시간보다 {_hm(_mins(alloc['over'] * per_unit))} 많습니다 — "
                                    f"분량이 다 찬 뒤의 시간은 비워 둡니다"})

    if o["unit"] == "pages" and not o["totalPages"]:
        warnings.append({"level": "info", "code": "no_pages",
                         "message": "범위 안 자료의 쪽수를 찾지 못했습니다 — 쪽수를 직접 입력하세요"})
    if left <= 0 and study:
        warnings.append({"level": "info", "code": "nothing_left", "message": "남은 분량이 없습니다"})
    if o["studyDays"] and o["studyDays"] > parts["pool"] and not parts["picked"]:
        warnings.append({"level": "info", "code": "short_pool",
                         "message": f"학습일로 쓸 수 있는 날은 {parts['pool']}일뿐입니다 — {parts['pool']}일에 나눴습니다"})
    if parts["excluded"]:
        warnings.append({"level": "info", "code": "excluded",
                         "message": f"제외일 {len(parts['excluded'])}일은 0쪽으로 두고 나머지 날에 나눴습니다"})
    return verdict, warnings


def _hm(minutes: int) -> str:
    """분 → '4시간' · '3시간 20분' · '45분' (경고 문구가 숫자로 말하게, F5-R25)."""
    minutes = _mins(minutes)
    h, m = divmod(minutes, 60)
    if h and m:
        return f"{h}시간 {m}분"
    return f"{h}시간" if h else f"{m}분"


def _md(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


__all__ = ["compute", "normalize", "split_days", "allocate", "date_str", "Invalid", "VERDICT_LABEL", "WEEKDAYS"]
