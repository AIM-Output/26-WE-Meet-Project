"""계산기 회귀 — 요구사항정의서 F3 6절 규칙(2026-09-29: 날짜(회) 단위)과 예시, 주1회·주2회·휴강·보강·공결 조합."""
from datetime import datetime

from attendance import calc
from conftest import session, weekly

NOW = datetime(2026, 12, 31, 12, 0)          # 전부 지난 회차


def example(absent=3, late=3):
    """6절 예시: 주 2회(화·목) × 15주 = 30회, 휴강 1회. 결석 3회 + 지각 3회."""
    tue = weekly("2026-09-01", 15)
    thu = weekly("2026-09-03", 15)
    tue[0]["state"], tue[0]["cancelSource"] = "canceled", "user"
    for s in tue[1:1 + absent]:
        s["attendance"] = "absent"
    for s in thu[:late]:
        s["attendance"] = "late"
    return tue + thu


def test_spec_example_is_caution():
    s = calc.summarize(example(), now=NOW)
    assert (s["plannedCount"], s["canceledCount"], s["makeupCount"], s["totalCount"]) == (30, 1, 0, 29)
    assert s["allowed"] == 7.25
    assert (s["absentCount"], s["convertedCount"], s["effectiveAbsent"]) == (3, 1, 4)      # 지각 3 → 결석 1
    assert s["remaining"] == 3.25 and s["spareSessions"] == 3
    assert s["level"] == "caution"                                                      # 4 ≥ 7.25 × 0.5
    assert s["basis"] == "총 29회 = 예정 30 − 휴강 1 + 보강 0"


def test_danger_then_over():
    s = calc.summarize(example(absent=6), now=NOW)
    assert s["effectiveAbsent"] == 7 and s["remaining"] == 0.25 and s["level"] == "danger" and s["spareSessions"] == 0
    s = calc.summarize(example(absent=7), now=NOW)
    assert s["effectiveAbsent"] == 8 and s["level"] == "over"


def test_exactly_quarter_is_not_over():
    ss = weekly("2026-09-01", 16)                       # 16회, 허용 4
    for x in ss[:4]:
        x["attendance"] = "absent"
    s = calc.summarize(ss, now=NOW)
    assert s["allowed"] == 4 and s["effectiveAbsent"] == 4 and s["level"] == "danger"
    ss[4]["attendance"] = "absent"
    assert calc.summarize(ss, now=NOW)["level"] == "over"


def test_day_is_one_count_regardless_of_length():
    """월 2교시 · 수 1교시 과목도 하루 = 1회 (2026-09-29 수정 ①)."""
    ss = [session("2026-09-07", start="13:00", end="14:50"), session("2026-09-09", start="13:00", end="13:50")]
    ss[0]["attendance"] = "absent"
    s = calc.summarize(ss, now=NOW)
    assert s["totalCount"] == 2 and s["effectiveAbsent"] == 1


def test_caution_threshold_half():
    ss = weekly("2026-09-01", 20)                       # 20회, 허용 5
    for x in ss[:2]:
        x["attendance"] = "absent"
    assert calc.summarize(ss, now=NOW)["level"] == "safe"       # 2 < 2.5
    ss[2]["attendance"] = "absent"
    assert calc.summarize(ss, now=NOW)["level"] == "caution"    # 3 ≥ 2.5, 여유 2 ≥ 1


def test_excused_and_unchecked_do_not_count():
    ss = weekly("2026-09-01", 10)
    ss[0]["attendance"] = "excused"
    s = calc.summarize(ss, now=NOW)
    assert s["effectiveAbsent"] == 0 and s["excusedCount"] == 1 and s["level"] == "safe"
    assert s["uncheckedSessions"] == 9


def test_late_conversion_setting():
    ss = weekly("2026-09-01", 16)
    for x in ss[:3]:
        x["attendance"] = "late"
    assert calc.summarize(ss, now=NOW)["convertedCount"] == 1
    assert calc.summarize(ss, {"lateToAbsence": 0}, now=NOW)["convertedCount"] == 0
    assert calc.summarize(ss, {"lateToAbsence": 2}, now=NOW)["convertedCount"] == 1


def test_manual_adjust_counts():
    ss = weekly("2026-09-01", 16) + weekly("2026-09-03", 16)   # 32회, 허용 8
    s = calc.summarize(ss, adjust={"absent": 2, "late": 3}, now=NOW)
    assert s["manualAdjust"] == {"absent": 2, "late": 3} and s["effectiveAbsent"] == 3 and s["level"] == "safe"
    assert calc.summarize(ss, adjust={"absent": -5}, now=NOW)["effectiveAbsent"] == 0


def test_limit_ratio_setting():
    ss = weekly("2026-09-01", 15)
    assert calc.summarize(ss, {"limitRatio": 1 / 3}, now=NOW)["allowed"] == 5


def test_auto_cancels_and_makeups():
    ss = weekly("2026-09-01", 10)
    ss[3]["state"], ss[3]["cancelSource"] = "canceled", "academic"
    ss[4]["state"], ss[4]["cancelSource"] = "canceled", "eclass"
    mk = session("2026-12-10", kind="makeup")
    mk_canceled = session("2026-12-11", kind="makeup", state="canceled", cancel="user")
    s = calc.summarize(ss + [mk, mk_canceled], now=NOW)
    assert (s["plannedCount"], s["canceledCount"], s["makeupCount"], s["totalCount"]) == (10, 2, 1, 9)
    assert s["autoCanceled"] == {"academic": 1, "eclass": 1} and "자동" in s["basis"]


def test_no_sessions_is_dash_and_zero_absence_is_safe():
    s = calc.summarize([], now=NOW)
    assert s["level"] is None and s["levelLabel"] == "—" and s["spareSessions"] is None
    tiny = weekly("2026-09-01", 2)                      # 2회, 허용 0.5 — 한 번 빠지면 초과
    assert calc.summarize(tiny, now=NOW)["level"] == "safe"
    tiny[0]["attendance"] = "absent"
    assert calc.summarize(tiny, now=NOW)["level"] == "over"


def test_unchecked_counts_only_ended_sessions():
    ss = [session("2026-10-20", start="09:00", end="10:50"), session("2026-10-21", start="13:00", end="13:50")]
    s = calc.summarize(ss, now=datetime(2026, 10, 20, 12, 0))
    assert s["uncheckedSessions"] == 1 and s["upcomingSessions"] == 1


def test_alert_texts_have_numbers():
    title, body = calc.alert_text("운영체제", "danger", calc.summarize(example(absent=6), now=NOW))
    assert title == "한 번 더 빠지면 F · 운영체제" and "결석 7회 / 허용 7.25회" in body and "0.25회" in body
    title, body = calc.alert_text("운영체제", "over", calc.summarize(example(absent=7), now=NOW))
    assert title.startswith("출석 미달") and "결석 8회" in body
    title, body = calc.alert_text("운영체제", "caution", calc.summarize(example(), now=NOW))
    assert "3번 더 빠질 수 있습니다" in body
