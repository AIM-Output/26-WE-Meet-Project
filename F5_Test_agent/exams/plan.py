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
    마무리 복습일 = 전체 훑기(총 시간 × 0.3 ÷ R) + (선택) 예상 문제 풀이

상한 검사 (F5 5절 표)
    하루 시간 ≤ 상한          → ok
    하루 시간 > 상한          → over    + 조정안 3가지
    여러 시험 합산 > 상한      → overlap + 어느 날 어느 과목이 몰렸는지
    학습일 D ≤ 0 (시험이 내일·오늘) → no_time — 계획 대신 남은 시간에 볼 우선순위

경고는 **숫자로** 말한다 ("하루 6시간이 필요합니다", F5-R25). 색만으로 표시하지 않으려고 level 과 message 를
같이 준다 (9절 '접근성').
"""
from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any, Optional

from . import config as C

WEEKDAYS = "월화수목금토일"

VERDICT_LABEL = {
    "ok": "정상",
    "over": "하루 상한 초과",
    "overlap": "다른 과목과 겹침",
    "no_time": "시간 없음",
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
    cap = _int(o.get("capMinutes"), C.DEFAULT_CAP_MINUTES)
    if not 30 <= cap <= 24 * 60:
        raise Invalid(f"하루 상한은 30분~24시간 사이입니다: {cap}분")

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
        "reviewDays": review_days, "excludedDates": excluded, "capMinutes": cap,
        "includeQuiz": include_quiz, "quizCount": quiz_count,
        "startDate": _date_str(o["startDate"], "시작일") if o.get("startDate") else None,
        # 2026-10-01 — 날짜가 주 옵션이다: 며칠 공부할지(studyDays) 또는 어느 날 공부할지(studyDates, 사용자가 달력에서 고름)
        "studyDays": _study_count(o.get("studyDays")),
        "studyDates": sorted({_date_str(d, "학습 날짜") for d in (o.get("studyDates") or [])}),
        "scopeWeeks": sorted({int(w) for w in (o.get("scopeWeeks") or [])}),
        "scopeMaterialIds": list(o.get("scopeMaterialIds") or []),
    }


def _mins(x: float) -> int:
    """분은 **반올림(0.5 는 올림)** — 파이썬 기본 round 는 22.5 를 22 로 만든다(짝수 쪽으로)."""
    return int(x + 0.5)


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


# ---------------------------------------------------------------- 본체

def compute(exam: dict, options: Optional[dict] = None, today: Optional[date] = None,
            other_load: Optional[dict[str, int]] = None, carry: Optional[dict] = None) -> dict:
    """시험 + 옵션 → 날짜별 분량 표와 경고·조정안. 저장하지 않는다 (미리보기가 그대로 쓴다).

    other_load = {날짜: 다른 계획의 분} — 여러 시험 합산 상한 검사 (F5-R23)
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

    shares = _even(left, len(study))
    days: list[dict] = list(carry_days)
    for d, amount in zip(study, shares):
        if amount <= 0:
            continue                                        # 분량이 남지 않은 날은 블록을 만들지 않는다
        days.append(_day(d, pages=amount if o["unit"] == "pages" else 0,
                         minutes=_mins(amount * per_unit), kind="study"))

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

    overlap = _overlap(real, other_load or {}, o["capMinutes"])
    verdict, warnings = _judge(o, exam, parts, peak_day, overlap, left)
    out = {
        "examId": exam.get("id"), "courseId": exam.get("courseId"), "courseName": exam.get("courseName", ""),
        "examDate": exam_date.isoformat(), "examTime": exam.get("time") or "",
        "examType": exam.get("type"), "examTypeLabel": C.type_label(exam.get("type") or "etc"),
        "state": "draft",
        **{k: o[k] for k in ("unit", "totalPages", "totalMinutes", "pageMinutes", "difficulty",
                             "reviewDays", "excludedDates", "capMinutes", "includeQuiz", "quizCount",
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
        "overlap": overlap,
        "peakDate": peak_day["date"] if peak_day else None,
        "adjustments": (_adjustments(o, parts, real, peak, per_unit, today)
                        if verdict in ("over", "overlap") else []),
        # 상한을 넘어도 등록을 막지는 않는다 — 확인을 한 번 더 받는다 (Frontend-Route 10-8)
        "canRegister": bool([d for d in real if d["minutes"] or d["pages"]]),
        "needsConfirm": verdict in ("over", "overlap"),
    }
    return out


def _day(d: date, pages: int, minutes: int, kind: str, quiz: int = 0) -> dict:
    return {"date": d.isoformat(), "weekday": WEEKDAYS[d.weekday()], "pages": pages, "minutes": minutes,
            "kind": kind, "quiz": quiz, "done": False, "moved": False}


def _overlap(days: list[dict], other_load: dict[str, Any], cap: int) -> list[dict]:
    """같은 날 다른 과목 계획과 합산해 상한을 넘는 날 (F5-R23 · S06).

    other_load 의 값은 분(int) 이거나 {'minutes', 'courses'} 다 — 명령줄에서는 숫자만 넘긴다."""
    out = []
    for d in days:
        raw = other_load.get(d["date"]) or 0
        if isinstance(raw, dict):
            other_minutes, courses = int(raw.get("minutes") or 0), list(raw.get("courses") or [])
        else:
            other_minutes, courses = int(raw), []
        if not other_minutes:
            continue
        total = d["minutes"] + other_minutes
        if total > cap:
            out.append({"date": d["date"], "minutes": total, "mine": d["minutes"], "others": other_minutes,
                        "cap": cap, "courses": courses})
    return out


def _judge(o: dict, exam: dict, parts: dict, peak_day: Optional[dict], overlap: list[dict],
           left: int) -> tuple[str, list[dict]]:
    warnings: list[dict] = []
    study, available = parts["study"], parts["available"]
    peak = peak_day["minutes"] if peak_day else 0
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
    elif peak > o["capMinutes"]:
        verdict = "over"
        where = f"{_md(peak_day['date'])} 에 " if peak_day else ""
        what = "마무리 복습에 " if peak_day and peak_day["kind"] == "review" else ""
        warnings.append({"level": "error", "code": "over_cap",
                         "message": f"{where}{what}{_hm(peak)}이 필요합니다 — "
                                    f"하루 기준 {_hm(o['capMinutes'])}을 넘습니다"})
    elif overlap:
        verdict = "overlap"

    if overlap and verdict != "no_time":
        worst = max(overlap, key=lambda x: x["minutes"])
        names = ", ".join(worst["courses"]) if worst["courses"] else "다른 과목"
        warnings.append({"level": "warn", "code": "overlap",
                         "message": f"{_md(worst['date'])} 에 {names} 계획과 합쳐 {_hm(worst['minutes'])}입니다 "
                                    f"— 상한 {_hm(worst['cap'])}"})
        if verdict == "ok":
            verdict = "overlap"

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


def _fit_pages(o: dict, n: int, per_unit: float, cap: int) -> int:
    """상한 안에 들어오는 총 쪽수 — 학습일과 마무리 복습일 **둘 다** 본다.

    학습일:  ceil(총/ n) × 쪽당 ≤ 상한
    복습일:  총 × 쪽당 × 훑기비율 ÷ R + 문제시간 ≤ 상한
    복습일 쪽을 빼먹으면 '분량 줄이기'를 눌러도 경고가 그대로 남는다."""
    limits = [cap * n / per_unit]
    r = o["reviewDays"]
    if r:
        quiz_minutes = _even(o["quizCount"], r)[0] * C.QUIZ_MINUTES_PER_ITEM if o["quizCount"] else 0
        room = max(1, cap - quiz_minutes)
        limits.append(room * r / (per_unit * C.REVIEW_SKIM_RATIO))
    return max(1, int(min(limits)))


def _adjustments(o: dict, parts: dict, days: list[dict], peak: int, per_unit: float,
                 today: date) -> list[dict]:
    """조정안 (F5-R24) — 사용자가 하나를 고르면 `apply` 를 옵션에 덮어 다시 계산한다.

    넘친 곳이 **학습일**이냐 **마무리 복습일**이냐에 따라 다른 것을 권한다 — 복습일이 넘쳤는데
    '분량 줄이기'를 권하면 눌러도 경고가 그대로다.
    """
    study_fix: list[dict] = []
    review_fix: list[dict] = []
    cap = o["capMinutes"]
    n = len(parts["study"])
    study_peak = max((d["minutes"] for d in days if d["kind"] == "study"), default=0)
    review_peak = max((d["minutes"] for d in days if d["kind"] == "review"), default=0)

    if study_peak > cap and n and n < parts["pool"]:
        total_minutes = sum(d["minutes"] for d in days if d["kind"] == "study")
        need = min(parts["pool"], max(n + 1, math.ceil(total_minutes / cap)))
        study_fix.append({"key": "more_days", "label": "학습일 늘리기",
                          "detail": f"학습일을 {n}일 → {need}일로 늘리면 하루 부담이 줄어듭니다",
                          "apply": {"studyDays": need, "studyDates": []}})
    if study_peak > cap:
        if o["startDate"] and o["startDate"] > today.isoformat():
            gained = (date.fromisoformat(o["startDate"]) - today).days
            study_fix.append({"key": "start_earlier", "label": "시작일 앞당기기",
                        "detail": f"오늘부터 시작하면 학습일이 {gained}일 늘어납니다",
                        "apply": {"startDate": today.isoformat()}})
        elif o["excludedDates"]:
            study_fix.append({"key": "drop_excluded", "label": "제외일 지우기",
                        "detail": f"제외일 {len(o['excludedDates'])}일을 학습일로 쓰면 하루 분량이 줄어듭니다",
                        "apply": {"excludedDates": []}})
        elif o["reviewDays"] > 1:
            study_fix.append({"key": "less_review", "label": "마무리 복습일 줄이기",
                        "detail": f"복습일을 {o['reviewDays']}일 → {o['reviewDays'] - 1}일로 두면 "
                                  f"학습일이 하루 늘어납니다",
                        "apply": {"reviewDays": o["reviewDays"] - 1}})
        if n and o["unit"] == "pages":
            fit = _fit_pages(o, n, per_unit, cap)
            if fit < o["totalPages"]:
                study_fix.append({"key": "less_scope", "label": "분량 줄이기",
                            "detail": f"{o['totalPages']}쪽 → {fit}쪽이면 하루 {_hm(cap)} 안에 들어옵니다",
                            "apply": {"totalPages": fit}})

    if review_peak > cap:
        spare = len(parts["available"]) - len(parts["review"])
        if o["reviewDays"] < C.MAX_REVIEW_DAYS and spare > 1:
            review_fix.append({"key": "more_review", "label": "마무리 복습일 늘리기",
                        "detail": f"복습일을 {o['reviewDays']}일 → {o['reviewDays'] + 1}일로 나누면 "
                                  f"복습 하루가 가벼워집니다",
                        "apply": {"reviewDays": o["reviewDays"] + 1}})
        if o["includeQuiz"] and o["quizCount"]:
            room = max(0, cap - (review_peak - _even(o["quizCount"], max(1, o["reviewDays"]))[0]
                                 * C.QUIZ_MINUTES_PER_ITEM))
            fit = max(0, int(room / C.QUIZ_MINUTES_PER_ITEM) * max(1, o["reviewDays"]))
            review_fix.append({"key": "less_quiz", "label": "예상 문제 줄이기",
                        "detail": f"문제를 {o['quizCount']}개 → {fit}개로 줄이면 복습일이 상한 안에 들어옵니다"
                                  if fit else "예상 문제 풀이를 빼면 복습일이 가벼워집니다",
                        "apply": {"quizCount": fit, "includeQuiz": bool(fit)}})

    # 하루 상한은 사용자가 고르는 옵션이 아니다(2026-10-02) — '상한 올리기'는 권하지 않는다
    return (study_fix + review_fix)[:3]


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


__all__ = ["compute", "normalize", "split_days", "date_str", "Invalid", "VERDICT_LABEL", "WEEKDAYS"]
