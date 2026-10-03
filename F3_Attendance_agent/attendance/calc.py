"""출결 계산기 — 순수 함수 `summarize(sessions, settings, adjust, now)` (요구사항정의서 F3 6절). LLM 없음 (F3-R37).

단위는 **회(수업한 날)** 다 (2026-09-29 수정 ① — 전남대는 출석을 하루 단위로 부른다. 월 2교시·수 1교시 과목도 각각 1회).

총 횟수
    예정 = 정규 회차 수 (시간표 × 개강~종강)
    총 횟수 = 예정 − 휴강(자동: 학사일정 휴업·휴강 · e클래스 공지 / 내가 표시) + 보강(학교 지정 보강일 + 내가 추가, 휴강한 보강은 빼고)
유효 결석
    결석 = '결석' 회차 수
    지각 환산 = floor((지각 + 직접 조정 지각) ÷ 환산기준)
    직접 조정 = 직접 고친 결석 횟수 (F3-R23 — 회차 기록에 가짜 결석을 만들지 않는다)
    공결은 빼고, 미입력은 결석으로 세지 않는다 (F3-R21·R24)
    유효 결석 = 결석 + 지각 환산 + 직접 조정 (0 아래로 내려가지 않는다)
허용 = 총 횟수 × 한도 비율(기본 1/4) · 남은 여유 = 허용 − 유효 결석 · 더 빠질 수 있는 횟수 = floor(남은 여유)

상태 (6절 기준표 — 위에서부터 먼저 맞는 것)
    —     총 횟수가 0 (계산 불가, 경고 없음)
    초과  유효 결석 > 허용                ('1/4 초과'. 정확히 1/4 이면 아직 초과가 아니다 — Q2)
    안전  아직 한 번도 빠지지 않음          (회차가 아주 적은 과목이 시작부터 '위험'으로 뜨지 않게)
    위험  남은 여유 < 1회                  (한 번 더 빠지면 초과)
    주의  유효 결석 ≥ 허용 × 0.5
    안전  그 밖
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Optional

from . import config as C

LEVELS = ("safe", "caution", "danger", "over")
LEVEL_RANK = {None: -1, "safe": 0, "caution": 1, "danger": 2, "over": 3}
LEVEL_LABEL = {"safe": "안전", "caution": "주의", "danger": "위험", "over": "초과", None: "—"}
_EPS = 1e-9


def _r(x: float) -> float:
    return round(x + 0.0, 2)


def ended(s: dict, now: datetime) -> bool:
    """수업이 끝났나 — 미입력 경고(F3-R22)는 끝난 회차만 센다."""
    return f"{s['date']}T{s['end']}" <= now.strftime("%Y-%m-%dT%H:%M")


def started(s: dict, now: datetime) -> bool:
    return f"{s['date']}T{s['start']}" <= now.strftime("%Y-%m-%dT%H:%M")


def summarize(sessions: list[dict], settings: Optional[dict] = None, adjust: Optional[dict] = None,
              now: Optional[datetime] = None) -> dict:
    st = {"limitRatio": C.DEFAULT_LIMIT_RATIO, "lateToAbsence": C.DEFAULT_LATE_TO_ABSENCE, **(settings or {})}
    adj = {"absent": 0, "late": 0, **(adjust or {})}
    now = now or datetime.now()

    regular = [s for s in sessions if s["kind"] == "regular"]
    canceled = [s for s in regular if s["state"] == "canceled"]
    held_makeups = [s for s in sessions if s["kind"] == "makeup" and s["state"] == "scheduled"]
    countable = [s for s in sessions if s["state"] == "scheduled"]
    auto = [s for s in canceled if s.get("cancelSource") in ("academic", "eclass")]

    total = len(regular) - len(canceled) + len(held_makeups)
    absent = sum(1 for s in countable if s["attendance"] == "absent")
    late = sum(1 for s in countable if s["attendance"] == "late")
    excused = sum(1 for s in countable if s["attendance"] == "excused")
    present = sum(1 for s in countable if s["attendance"] == "present")
    late_total = max(0, late + int(adj["late"] or 0))
    ratio_late = int(st["lateToAbsence"] or 0)
    converted = late_total // ratio_late if ratio_late > 0 else 0
    manual = int(adj["absent"] or 0)
    effective = max(0, absent + converted + manual)
    allowed = total * float(st["limitRatio"])
    remaining = allowed - effective

    level: Optional[str]
    if total <= 0:
        level = None
    elif effective > allowed + _EPS:
        level = "over"
    elif effective <= 0:
        level = "safe"
    elif remaining < 1 - _EPS:
        level = "danger"
    elif effective >= allowed * C.CAUTION_RATIO - _EPS:
        level = "caution"
    else:
        level = "safe"

    spare = max(0, math.floor(remaining + _EPS)) if level is not None else None
    unchecked = [s for s in countable if s["attendance"] is None and ended(s, now)]
    upcoming = [s for s in countable if not started(s, now)]

    return {
        "totalCount": total,
        "plannedCount": len(regular), "canceledCount": len(canceled), "makeupCount": len(held_makeups),
        "autoCanceledCount": len(auto),
        "autoCanceled": {"academic": sum(1 for s in auto if s["cancelSource"] == "academic"),
                         "eclass": sum(1 for s in auto if s["cancelSource"] == "eclass")},
        "absentCount": absent, "lateCount": late, "excusedCount": excused, "presentCount": present,
        "lateCounted": late_total, "convertedCount": converted,
        "manualAdjust": {"absent": manual, "late": int(adj["late"] or 0)},
        "effectiveAbsent": effective, "allowed": _r(allowed), "remaining": _r(remaining),
        "spareSessions": spare,
        "level": level, "levelLabel": LEVEL_LABEL[level],
        "uncheckedSessions": len(unchecked), "upcomingSessions": len(upcoming),
        "sessionCount": len(sessions),
        "basis": basis_text(len(regular), len(canceled), len(held_makeups), total, len(auto)),
    }


def _n(x: float) -> str:
    return f"{x:g}" if abs(x - round(x, 2)) < _EPS else f"{x:.2f}"


def basis_text(planned: int, canceled: int, makeup: int, total: int, auto: int) -> str:
    """F3-S02 근거 줄 — '총 30회 = 예정 32 − 휴강 3 + 보강 1 (자동 휴강 2)'"""
    s = f"총 {total}회 = 예정 {planned} − 휴강 {canceled} + 보강 {makeup}"
    if auto:
        s += f" (휴강 중 {auto}회는 학사일정·공지에서 자동)"
    return s


def alert_text(name: str, level: str, s: dict) -> tuple[str, str]:
    """상태가 올라갈 때 알림 문구 (F3-R33·R34 — 남은 여유를 숫자로)."""
    eff, allowed = s["effectiveAbsent"], _n(s["allowed"])
    if level == "over":
        return (f"출석 미달 · {name}",
                f"결석 {eff}회로 허용 {allowed}회(1/4)를 넘었습니다 — 학과·교수님께 확인하세요")
    if level == "danger":
        return (f"한 번 더 빠지면 F · {name}",
                f"결석 {eff}회 / 허용 {allowed}회 — 남은 여유 {_n(max(0.0, s['remaining']))}회, 다음 결석이면 한도를 넘습니다")
    return (f"출결 주의 · {name}",
            f"결석 {eff}회 / 허용 {allowed}회 — 앞으로 {s['spareSessions']}번 더 빠질 수 있습니다")
