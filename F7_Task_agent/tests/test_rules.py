"""계산 규칙 (F7 5절) — 그룹 기준 · 정렬 · 이유 문구 · 유형별 기본 시간 · 예외(8절)."""
import time
from datetime import datetime, timedelta

from conftest import NOW, example_items, item, spec
from tasks import config as C
from tasks import rules
from tasks import settings as S


def ranked(items, now=NOW, settings=None):
    return rules.rank(items, now, settings or spec())


# ---------------------------------------------------------------- 5절 예시 표

def test_example_table_groups_and_order():
    rows = ranked(example_items())
    assert [(r["title"], r["group"], r["rank"]) for r in rows] == [
        ("퀴즈 2회", "now", 1),
        ("실습 과제", "week", 1),
        ("팀 프로젝트 보고서", "week", 2),       # 마감은 품질 보고서보다 늦지만 여유가 적어 위로 (5절 '마감순과 다른 지점')
        ("품질 보고서", "week", 3),
        ("기말 프로젝트", "later", 1),
    ]


def test_example_table_numbers():
    by = {r["title"]: r for r in ranked(example_items())}
    q = by["퀴즈 2회"]
    assert q["estimatedHours"] == 0.5 and q["estimateSource"] == "default"
    assert q["neededHours"] == 0.75
    assert abs(q["remainingHours"] - 9.98) < 0.01
    team = by["팀 프로젝트 보고서"]
    assert team["estimateSource"] == "user" and team["neededHours"] == 75
    assert abs(team["slackHours"] - 54.98) < 0.005          # 5절 표는 23:59 를 24:00 으로 어림한 55h
    assert abs(by["품질 보고서"]["slackHours"] - 68.5) < 0.01
    assert abs(by["실습 과제"]["slackHours"] - 29.48) < 0.005


def test_example_reasons():
    by = {r["title"]: r["reason"] for r in ranked(example_items())}
    assert by["퀴즈 2회"] == "마감 10시간 전 · 30분 필요"
    assert by["실습 과제"] == "마감 1일 전 · 3시간 필요"
    assert by["품질 보고서"] == "마감 3일 전 · 5시간 필요"


# ---------------------------------------------------------------- 그룹 경계

def test_within_24h_is_now_even_with_slack():
    rows = ranked([item("a", "짧은 과제", (NOW + timedelta(hours=23)).isoformat(), est=0.25)])
    assert rows[0]["group"] == "now"


def test_negative_slack_is_now_even_far_away():
    # 마감 3일 뒤지만 50시간 × 1.5 = 75 > 72 → 지금 해야 함
    rows = ranked([item("a", "큰 보고서", (NOW + timedelta(hours=72)).isoformat(), est=50)])
    assert rows[0]["group"] == "now"
    assert rows[0]["reason"] == "지금 시작해도 빠듯 (50시간 필요, 72시간 남음)"


def test_not_enough_time_is_spelled_out():
    rows = ranked([item("a", "보고서", (NOW + timedelta(hours=2)).isoformat(), est=3)])
    assert rows[0]["group"] == "now" and rows[0]["short"] is True
    assert rows[0]["reason"] == "시간이 부족합니다 (3시간 필요, 2시간 남음)"


def test_week_boundary_is_seven_days_of_slack():
    due_in = 7 * 24 + 3 * 1.5                       # 여유가 딱 7일
    rows = ranked([item("a", "과제", (NOW + timedelta(hours=due_in)).isoformat())])
    assert rows[0]["group"] == "week"
    rows = ranked([item("a", "과제", (NOW + timedelta(hours=due_in + 0.1)).isoformat())])
    assert rows[0]["group"] == "later"


def test_overdue_first_and_reason():
    rows = ranked([
        item("a", "다음 주 과제", "2026-10-01T23:59:00"),
        item("b", "2주차 실습", "2026-09-23T23:59:00"),
        item("c", "어제 저녁", "2026-09-25T09:00:00"),
    ])
    assert [r["id"] for r in rows] == ["b", "c", "a"]       # 놓친 마감이 맨 위, 그 안에서 여유(더 음수) 순
    assert rows[0]["group"] == "overdue"
    assert rows[0]["reason"] == "마감 2일 지남 · 미제출"
    assert rows[1]["reason"] == "마감 5시간 지남 · 미제출"


def test_midnight_deadline_counts_as_previous_day():
    # '9월 22일 자정까지' = 9/23 00:00 → 9/25 기준 3일 지남 (9/22 마감)
    rows = ranked([item("a", "자정 과제", "2026-09-23T00:00:00")])
    assert rows[0]["reason"] == "마감 3일 지남 · 미제출"


def test_stale_overdue_flag():
    rows = ranked([item("a", "오래된 것", (NOW - timedelta(days=15)).isoformat()),
                   item("b", "얼마 전", (NOW - timedelta(days=3)).isoformat())])
    by = {r["id"]: r for r in rows}
    assert by["a"]["stale"] is True and by["b"]["stale"] is False


def test_no_due_goes_to_its_own_group_last():
    rows = ranked([item("a", "마감 없는 과제", None), item("b", "과제", "2026-09-27T12:00:00")])
    assert [r["group"] for r in rows] == ["week", "nodue"]
    nd = rows[1]
    assert nd["remainingHours"] is None and nd["slackHours"] is None
    assert nd["reason"] == "마감 없음 · 3시간 필요"


def test_done_items_are_excluded():
    rows = ranked([
        item("a", "제출함", "2026-09-26T12:00:00", submitted=True),
        item("b", "내가 체크함", "2026-09-26T12:00:00", userDone=True),
        item("c", "사라진 과제", "2026-09-26T12:00:00", removed=True),
        item("d", "남은 과제", "2026-09-26T12:00:00"),
    ])
    assert [r["id"] for r in rows] == ["d"]


def test_sort_is_stable_on_ties():
    due = "2026-09-27T12:00:00"
    items = [item("z", "B 과제", due, course="운영체제"), item("y", "A 과제", due, course="운영체제"),
             item("x", "과제", due, course="객체지향")]
    a = [r["id"] for r in ranked(items)]
    b = [r["id"] for r in ranked(list(reversed(items)))]
    assert a == b == ["x", "y", "z"]                          # 마감 같음 → 과목명 → 제목


# ---------------------------------------------------------------- 유형 · 소요시간

def test_kind_of():
    assert rules.kind_of("퀴즈", "3주차 퀴즈") == "quiz"
    assert rules.kind_of("동영상", "1주차 강의") == "video"
    assert rules.kind_of("과제", "10/7 진도점검 발표") == "project"       # 실측: 발표가 과제로 들어온다
    assert rules.kind_of("과제", "개인프로젝트1. 프로젝트 제안서 작성") == "project"
    assert rules.kind_of("과제", "퀴즈 풀이 보고서") == "assignment"      # e클래스가 과제라고 한 것은 과제
    assert rules.kind_of("일정", "온라인 퀴즈 2회") == "quiz"            # 캘린더에서만 보인 일정은 제목으로
    assert rules.kind_of("일정", "중간 정리 동영상 시청") == "video"
    assert rules.kind_of("", "보고서") == "assignment"


def test_default_hours_per_kind():
    rows = ranked([item("q", "퀴즈", "2026-10-30T12:00:00", etype="퀴즈"),
                   item("v", "영상", "2026-10-30T12:00:00", etype="동영상"),
                   item("p", "팀 프로젝트 중간 발표", "2026-10-30T12:00:00"),
                   item("a", "실습", "2026-10-30T12:00:00")])
    assert {r["id"]: r["estimatedHours"] for r in rows} == {"q": 0.5, "v": 1.0, "p": 5.0, "a": 3.0}
    assert {r["id"]: r["kindLabel"] for r in rows} == {"q": "퀴즈", "v": "동영상", "p": "프로젝트", "a": "과제"}


def test_new_defaults_without_settings():
    """2026-10-06 기본값 — 안전계수 1.0(필요 시간 = 예상 그대로) · 과제 2시간 · 퀴즈 30분 · 동영상 50분 · 프로젝트 4시간."""
    rows = rules.rank([item("q", "퀴즈", "2026-10-30T12:00:00", etype="퀴즈"),
                       item("v", "영상", "2026-10-30T12:00:00", etype="동영상"),
                       item("p", "중간 발표", "2026-10-30T12:00:00"),
                       item("a", "실습", "2026-09-26T14:00:00")], NOW, C.default_settings())
    by = {r["id"]: r for r in rows}
    assert {k: round(r["estimatedHours"], 4) for k, r in by.items()} == {"q": 0.5, "v": 0.8333, "p": 4.0, "a": 2.0}
    assert by["a"]["neededHours"] == 2.0 and by["a"]["reason"] == "마감 24시간 전 · 2시간 필요"
    assert by["v"]["reason"].endswith("· 50분 필요")


def test_user_estimate_zero_or_negative_is_clamped():
    rows = ranked([item("a", "과제", "2026-10-30T12:00:00", est=0), item("b", "과제2", "2026-10-30T12:00:00", est=-3)])
    assert all(r["estimatedHours"] == C.MIN_HOURS and r["estimateSource"] == "user" for r in rows)


def test_settings_change_groups():
    """안전계수·기본 시간을 바꾸면 계산이 따라간다 (F7-R05)."""
    it = [item("a", "실습 과제", "2026-09-27T14:00:00")]            # 48시간 남음, 기본 3시간
    assert ranked(it)[0]["group"] == "week"
    s = spec()
    s["defaultHours"]["assignment"] = 40                             # 40 × 1.5 = 60 > 48
    assert ranked(it, settings=s)[0]["group"] == "now"
    s = spec()
    s["safetyFactor"] = 3.0
    assert ranked(it, settings=s)[0]["neededHours"] == 9.0


def test_settings_from_file_are_used(tmp_path):
    S.save({"defaultHours": {"quiz": 1}})
    rows = ranked([item("q", "퀴즈", "2026-10-30T12:00:00", etype="퀴즈")], settings=S.load())
    assert rows[0]["estimatedHours"] == 1.0


# ---------------------------------------------------------------- 문구 · 반올림

def test_fmt_hours():
    assert rules.fmt_hours(0.5) == "30분"
    assert rules.fmt_hours(3) == "3시간"
    assert rules.fmt_hours(1.75) == "1시간 45분"
    assert rules.fmt_hours(0.25) == "15분"


def test_half_up_not_bankers():
    assert rules.half_up(2.5) == 3 and rules.half_up(22.5) == 23


def test_days_left_match_dday_chip():
    """'마감 N일 전'은 화면의 D-day 칩과 같은 달력 날짜 차이다 (2026-10-06 화면 확인: 86시간 남은 10/9 마감이 'D-3 · 4일 전'으로 어긋났다)."""
    now = datetime(2026, 10, 6, 9, 45)
    rows = ranked([item("a", "요구사항 명세서", "2026-10-09T23:59:00", est=1),
                   item("b", "자정 과제", "2026-10-10T00:00:00", est=1)], now=now)
    assert [r["reason"] for r in rows] == ["마감 3일 전 · 1시간 필요", "마감 3일 전 · 1시간 필요"]


def test_minutes_left_reason():
    rows = ranked([item("a", "퀴즈", (NOW + timedelta(minutes=40)).isoformat(), etype="퀴즈", est=0.25)])
    assert rows[0]["reason"] == "마감 40분 전 · 15분 필요"


# ---------------------------------------------------------------- 성능 (9절: 100건 10ms)

def test_hundred_items_fast():
    items = [item(f"dl:{i}", f"과제 {i}", (NOW + timedelta(hours=i * 7 - 50)).isoformat(),
                  etype=("과제", "퀴즈", "동영상")[i % 3], est=(None if i % 4 else i % 9 + 1)) for i in range(100)]
    best = min(_timed(lambda: ranked(items)) for _ in range(5))
    assert best < 0.010, f"100건 계산에 {best * 1000:.1f}ms"


def _timed(fn):
    t = time.perf_counter()
    fn()
    return time.perf_counter() - t
