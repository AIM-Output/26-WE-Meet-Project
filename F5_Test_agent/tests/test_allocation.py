"""시간 배치 (2026-10-06 사용자 요청 D11) — 총 공부 시간을 학습일에 사용자가 자유롭게 나눈다.

사용자의 예: 학습일 3일이면 지금은 하루 5시간 36분씩 똑같이 나뉜다 → 3시간 · 5시간 · 8시간처럼 직접 배치하고 싶다.
규칙: 시간을 정한 날(고정)이 먼저 그 시간만큼 가져가고, 정하지 않은 날이 남은 분량을 고르게 나눈다.
"""
from datetime import date

import pytest

from exams import plan as P
from exams import service, store

from conftest import TODAY as SVC_TODAY, add_exam, courses  # noqa: E402

EXAM = {"id": "ex:1:a", "courseId": "1", "courseName": "운영체제", "type": "midterm",
        "date": "2026-10-23", "time": "14:00"}
TODAY = date(2026, 10, 13)
# 672쪽 × 1.5분 = 1008분(16시간 48분) — 3일이면 하루 5시간 36분 (사용자가 든 숫자)
BASE = {"totalPages": 672, "pageMinutes": 1.5, "reviewDays": 1, "studyDays": 3}
D1, D2, D3 = "2026-10-19", "2026-10-20", "2026-10-21"


def compute(**options):
    return P.compute(EXAM, {**BASE, **options}, TODAY)


def study(out):
    return {d["date"]: (d["pages"], d["minutes"], d["pinned"]) for d in out["days"] if d["kind"] == "study"}


def test_even_split_is_the_starting_point():
    out = compute()
    assert out["allocation"]["needMinutes"] == 1008
    assert study(out) == {D1: (224, 336, False), D2: (224, 336, False), D3: (224, 336, False)}
    assert out["dayMinutes"] == {} and out["allocation"]["fixes"] == []


def test_pinned_day_takes_its_time_and_the_rest_follow():
    """3시간으로 정하면 나머지 이틀이 남은 13시간 48분을 나눈다 — 합은 늘 총 시간."""
    out = compute(dayMinutes={D1: 180})
    assert study(out) == {D1: (120, 180, True), D2: (276, 414, False), D3: (276, 414, False)}
    assert out["allocation"]["assignedMinutes"] == 1008
    assert out["allocation"]["pinnedDates"] == [D1] and out["allocation"]["autoDates"] == [D2, D3]

    out = compute(dayMinutes={D1: 180, D2: 300})
    assert study(out) == {D1: (120, 180, True), D2: (200, 300, True), D3: (352, 528, False)}
    assert out["dayRange"] == {"minMinutes": 180, "maxMinutes": 528, "minPages": 120, "maxPages": 352}


def test_all_pinned_but_short_cannot_register():
    """3시간 · 5시간 · 8시간 = 16시간 — 총 16시간 48분에 48분(32쪽) 모자란다."""
    out = compute(dayMinutes={D1: 180, D2: 300, D3: 480})
    assert out["verdict"] == "short" and out["canRegister"] is False
    assert out["allocation"]["unassignedUnits"] == 32 and out["allocation"]["unassignedMinutes"] == 48
    w = next(w for w in out["warnings"] if w["code"] == "unassigned")
    assert w["level"] == "error" and "32쪽(48분)" in w["message"]
    keys = [a["key"] for a in out["adjustments"]]
    assert keys[:2] == ["fill_last", "even_split"]
    fill = out["adjustments"][0]
    assert fill["apply"]["dayMinutes"] == {D1: 180, D2: 300, D3: 528}

    fixed = compute(dayMinutes=fill["apply"]["dayMinutes"])
    assert fixed["verdict"] != "short" and fixed["canRegister"]
    assert sum(p for p, _, _ in study(fixed).values()) == 672
    assert compute(dayMinutes={})["allocation"]["fixes"] == []


def test_pins_over_the_need_are_trimmed_in_date_order():
    out = compute(dayMinutes={D1: 900, D2: 600})
    assert study(out) == {D1: (600, 900, True), D2: (72, 108, True)}           # 10/21 은 남은 분량이 없다
    assert out["allocation"]["overMinutes"] == 492
    assert any(w["code"] == "over_assigned" for w in out["warnings"])
    assert out["canRegister"]
    fit = next(a for a in out["adjustments"] if a["key"] == "fit_pins")
    assert sum(fit["apply"]["dayMinutes"].values()) == 1008


def test_rounding_is_not_a_warning():
    """253쪽 × 1.5분 = 380분을 190분 · 190분으로 — 127쪽씩이면 1쪽 넘지만 반올림이라 조용히 맞춘다."""
    out = compute(totalPages=253, studyDays=2, dayMinutes={D2: 190, D3: 190})
    assert out["allocation"]["overMinutes"] == 0 and out["verdict"] == "ok"
    assert [p for p, _, _ in study(out).values()] == [127, 126]
    under = compute(totalPages=253, studyDays=2, dayMinutes={D2: 189, D3: 189})   # 126쪽씩 → 1쪽 남음
    assert under["verdict"] == "ok" and sum(p for p, _, _ in study(under).values()) == 253


def test_long_pinned_day_has_no_warning():
    """직접 8시간으로 정한 날도, 자동으로 나눈 긴 날도 경고하지 않는다 — 하루 기준이 없다 (2026-10-07)."""
    out = compute(totalPages=400, dayMinutes={D1: 60, D2: 60, D3: 480})
    assert out["verdict"] == "ok" and not [w for w in out["warnings"] if w["level"] in ("error", "warn")]
    assert compute()["verdict"] == "ok"


def test_zero_minutes_skips_the_day_and_foreign_dates_are_ignored():
    out = compute(dayMinutes={D1: 0, "2026-10-10": 120})
    assert study(out) == {D2: (336, 504, False), D3: (336, 504, False)}
    assert out["dayMinutes"] == {D1: 0}                                       # 학습일이 아닌 날의 값은 버린다


def test_minutes_unit():
    out = compute(totalPages=0, unit="minutes", totalMinutes=600, dayMinutes={D1: 100})
    assert study(out) == {D1: (0, 100, True), D2: (0, 250, False), D3: (0, 250, False)}


def test_bad_day_minutes():
    with pytest.raises(P.Invalid):
        compute(dayMinutes={D1: 2000})
    with pytest.raises(P.Invalid):
        compute(dayMinutes=[180])
    with pytest.raises(P.Invalid):
        compute(dayMinutes={"10월 19일": 60})


# ---------------------------------------------------------------- 등록 · 재조정 (service)

def test_registered_plan_keeps_the_pins(db, materials):
    """등록하면 정한 시간이 저장되고, 다시 만들기·재조정 화면이 그 값을 물려받는다."""
    e = add_exam(db, when="2026-10-23")
    opts = {"totalPages": 145, "pageMinutes": 2, "reviewDays": 1, "studyDays": 3,
            "dayMinutes": {"2026-10-19": 60, "2026-10-20": 120}}
    made = service.create_plan(db, e["id"], opts, SVC_TODAY, courses)
    plan = made["plan"]
    assert plan["dayMinutes"] == {"2026-10-19": 60, "2026-10-20": 120}
    days = {d["date"]: d for d in plan["days"]}
    assert days["2026-10-19"]["minutes"] == 60 and days["2026-10-19"]["pinned"]
    assert days["2026-10-21"]["pages"] == 145 - 30 - 60 and not days["2026-10-21"]["pinned"]

    o = service.default_options(db, store.exam(db, e["id"]), SVC_TODAY)
    assert o["dayMinutes"] == {"2026-10-19": 60, "2026-10-20": 120}
    # 첫날을 끝낸 뒤에는 그 날의 고정 값을 넘기지 않는다
    service.patch_day(db, plan["planId"], "2026-10-19", {"done": True}, SVC_TODAY, courses)
    o = service.default_options(db, store.exam(db, e["id"]), SVC_TODAY)
    assert o["dayMinutes"] == {"2026-10-20": 120}


def test_new_plan_starts_even(db, materials):
    e = add_exam(db)
    assert service.default_options(db, store.exam(db, e["id"]), SVC_TODAY)["dayMinutes"] == {}
