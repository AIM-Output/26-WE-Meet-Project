"""우선순위 계산 규칙 — 요구사항정의서 F7 5절을 그대로 옮긴 순수 함수. 저장도 입출력도 없다.

    남은 시간 h = (마감 일시 − 지금)            시간 단위, 음수면 지난 마감
    필요 시간 w = 예상 소요시간 × 안전계수       사람은 예상보다 오래 걸린다
    여유      s = h − w

    놓친 마감    h < 0 이고 미제출
    지금 해야 함 s ≤ 0 또는 h ≤ 24시간
    이번 주      s ≤ 7일
    나중에       그 외
    (마감 없음   마감이 없는 과제 — 순위 계산에서 빼고 맨 아래에 따로, 8절)

정렬: 그룹 → s 오름차순 → 마감 빠른 순 → 과목명 → 제목 → id (같은 입력·같은 시각이면 항상 같은 순서, 9절 '안정성').
입력 과제는 F6 원장의 화면용 모양(eclass.service.view) 그대로다 — id · title · type · due · courseShort · submitted ·
userDone · done · removed · estimateHours(사용자가 고친 값, 없으면 None).
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from . import config as C

_PROJECT = re.compile(r"프로젝트|project|캡스톤|capstone|발표|presentation", re.I)
_QUIZ = re.compile(r"퀴즈|quiz|쪽지\s*시험", re.I)
_VIDEO = re.compile(r"동영상|영상|강의\s*시청|video|vod", re.I)


def half_up(x: float) -> int:
    """반올림(.5 는 올림). 파이썬 round 는 짝수 쪽으로 가서 2.5 → 2 가 된다 — 화면 숫자가 규칙과 어긋난다 (F5 와 같은 규칙)."""
    return int(math.floor(x + 0.5))


# ---------------------------------------------------------------- 유형 · 소요시간 (가)

def kind_of(etype: str, title: str) -> str:
    """F6 의 type(과제·퀴즈·동영상·일정) + 제목 → assignment · quiz · video · project (F7-R01).

    e클래스가 퀴즈·동영상이라고 한 것은 그대로 믿는다. 과제·일정 중 제목에 발표·프로젝트가 있으면 프로젝트(기본 4시간)로 본다
    — e클래스에는 '발표/프로젝트' 유형이 따로 없다(실측 2026-10-06: '10/7 진도점검 발표' 가 과제로 들어온다).
    캘린더에서만 보인 '일정'은 제목으로 퀴즈·동영상을 한 번 더 가른다."""
    etype = (etype or "").strip()
    title = title or ""
    if etype == "퀴즈":
        return "quiz"
    if etype == "동영상":
        return "video"
    if _PROJECT.search(title):
        return "project"
    if etype != "과제":
        if _QUIZ.search(title):
            return "quiz"
        if _VIDEO.search(title):
            return "video"
    return "assignment"


def clamp_hours(h: Any) -> Optional[float]:
    """사용자 입력 소요시간 → 쓸 수 있는 값. 숫자가 아니면 None, 0·음수는 최소 0.25시간으로 보정한다 (8절)."""
    try:
        v = float(h)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return min(C.MAX_HOURS, max(C.MIN_HOURS, v))


def estimate_of(item: dict, settings: dict) -> tuple[float, str, str]:
    """(예상 소요시간, 출처 default|user, 유형) — 사용자가 고친 값이 있으면 그것, 없으면 유형별 기본값 (F7-R01·R02)."""
    kind = kind_of(item.get("type", ""), item.get("title", ""))
    user = clamp_hours(item.get("estimateHours")) if item.get("estimateHours") is not None else None
    if user is not None:
        return user, "user", kind
    hours = (settings.get("defaultHours") or {}).get(kind, C.KINDS[kind]["hours"])
    return max(C.MIN_HOURS, float(hours)), "default", kind


# ---------------------------------------------------------------- 문구

def fmt_hours(h: float) -> str:
    """0.5 → '30분' · 3 → '3시간' · 1.75 → '1시간 45분' (프론트 dates.fmtHours 와 같은 모양)."""
    m = half_up(max(0.0, h) * 60)
    if m < 60:
        return f"{m}분"
    hh, mm = divmod(m, 60)
    return f"{hh}시간 {mm}분" if mm else f"{hh}시간"


def _deadline_day(due: datetime):
    """00:00 마감은 전날 마감이다(F6 자정 규칙) — 10/5 00:00 은 10/4 마감."""
    return (due - timedelta(minutes=1)).date()


def _until(h: float, due: datetime, now: datetime) -> str:
    """남은 시간 → '40분' · '8시간' · '3일' (h > 0). 하루가 넘으면 **달력 날짜 차이** — 화면의 D-day 칩(D-3)과 같은 수."""
    if h < 1:
        return f"{max(1, half_up(h * 60))}분"
    if h <= C.NOW_WITHIN_HOURS:
        return f"{max(1, half_up(h))}시간"
    return f"{max(1, (_deadline_day(due) - now.date()).days)}일"


def _since(due: datetime, now: datetime) -> str:
    """지난 시간 → '40분' · '14시간' · '2일'. 하루가 넘으면 **달력 날짜 차이**로 센다 (그제 마감 = 2일 지남).
    00:00 마감은 전날 밤 마감이다(F6 자정 규칙) — 10/5 00:00 은 10/4 마감으로 센다."""
    late = (now - due).total_seconds() / 3600
    if late < 1:
        return f"{max(1, half_up(late * 60))}분"
    if late < 24:
        return f"{half_up(late)}시간"
    return f"{max(1, (now.date() - _deadline_day(due)).days)}일"


def reason_of(h: Optional[float], est: float, s: Optional[float], due: Optional[datetime], now: datetime) -> str:
    """이유 한 줄 (F7-R15 · 5절 표). 모든 항목에 붙는다 — 사용자가 규칙을 추측하지 않아도 되게 (9절 '투명성')."""
    if h is None or due is None:
        return f"마감 없음 · {fmt_hours(est)} 필요"
    if h < 0:
        return f"마감 {_since(due, now)} 지남 · 미제출"
    if s is not None and s <= 0:
        # 소요시간이 남은 시간보다 크면(안전계수 없이도 못 끝낸다) '시간이 부족합니다'를 밝힌다 (8절)
        head = "시간이 부족합니다" if est > h else "지금 시작해도 빠듯"
        return f"{head} ({fmt_hours(est)} 필요, {fmt_hours(h)} 남음)"
    return f"마감 {_until(h, due, now)} 전 · {fmt_hours(est)} 필요"


# ---------------------------------------------------------------- 한 건 계산 (나)

def parse_due(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace(" ", "T"))
    except ValueError:
        return None


def group_of(h: Optional[float], s: Optional[float]) -> str:
    if h is None or s is None:
        return "nodue"
    if h < 0:
        return "overdue"
    if s <= 0 or h <= C.NOW_WITHIN_HOURS:
        return "now"
    if s <= C.WEEK_SLACK_HOURS:
        return "week"
    return "later"


def is_open(item: dict) -> bool:
    """계산 대상 — 제출 완료·내가 체크함·사라진 과제는 뺀다 (F7-R13)."""
    return not (item.get("done") or item.get("submitted") or item.get("userDone") or item.get("removed"))


def evaluate(item: dict, now: datetime, settings: dict) -> dict:
    """과제 한 건 → F7 계산 결과(응답 전용 필드, 6절). 원장 값은 그대로 두고 옆에 붙인다."""
    est, source, kind = estimate_of(item, settings)
    factor = float(settings.get("safetyFactor") or C.SAFETY_FACTOR)
    due = parse_due(item.get("due"))
    w = est * factor
    if due is None:
        h = s = None
    else:
        h = (due - now).total_seconds() / 3600
        s = h - w
    group = group_of(h, s)
    stale = group == "overdue" and h is not None and -h > C.STALE_OVERDUE_DAYS * 24
    return {
        "kind": kind, "kindLabel": C.KINDS[kind]["label"],
        "estimatedHours": est, "estimateSource": source,
        "remainingHours": None if h is None else round(h, 2),
        "neededHours": round(w, 2),
        "slackHours": None if s is None else round(s, 2),
        "group": group, "groupLabel": C.GROUPS[group]["label"],
        "reason": reason_of(h, est, s, due, now),
        "short": bool(h is not None and 0 <= h < est),      # 안전계수 없이도 못 끝낸다
        "stale": stale,                                      # 2주 넘게 지난 놓친 마감 — 접어 둔다
        "_slack": s, "_due": due,
    }


def sort_key(row: dict) -> tuple:
    """그룹 → s 오름차순 → 마감 → 과목명 → 제목 → id. 마감 없음은 제목 순."""
    due = row["_due"]
    return (C.GROUP_ORDER.index(row["group"]),
            row["_slack"] if row["_slack"] is not None else 0.0,
            due.isoformat() if due else "",
            row.get("courseShort") or "", row.get("title") or "", row.get("id") or "")


def rank(items: Iterable[dict], now: datetime, settings: dict) -> list[dict]:
    """미완료 과제 → 계산 결과를 붙여 급한 순으로. 그룹 안 순서(rank)는 1부터 (F7-R11·R12·R13)."""
    rows = [{**it, **evaluate(it, now, settings)} for it in items if is_open(it)]
    rows.sort(key=sort_key)
    counter: dict[str, int] = {}
    for r in rows:
        counter[r["group"]] = counter.get(r["group"], 0) + 1
        r["rank"] = counter[r["group"]]
    for r in rows:
        r.pop("_slack", None)
        r.pop("_due", None)
    return rows
