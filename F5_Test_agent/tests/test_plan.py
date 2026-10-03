"""계산기 (F5 5절) — 요구사항정의서의 예시와 상한·제외일·재조정 규칙."""
from datetime import date

import pytest

from exams import config as C
from exams import plan as P

EXAM = {"id": "ex:1:a", "courseId": "1", "courseName": "운영체제", "type": "midterm",
        "date": "2026-10-23", "time": "14:00"}
TODAY = date(2026, 10, 13)


# 요구사항정의서 F5 5절 예시의 입력 — 기본값이 바뀌어도(2026-10-02) 계산 규칙 시험은 이 값으로 고정한다
DOC = {"totalPages": 120, "difficulty": "normal", "reviewDays": 2, "pageMinutes": 2.5}


def compute(**options):
    o = {**DOC, **options}
    if "difficulty" in options and "pageMinutes" not in options:
        o.pop("pageMinutes")                       # 난이도만 바꾼 시험은 난이도 계수를 쓴다
    return P.compute(EXAM, o, TODAY)


# ---------------------------------------------------------------- 요구사항정의서 F5 5절 '예시'

def test_doc_example():
    """10/23 중간고사 · 오늘 10/13 · 120쪽 · 보통(2.5분/쪽)
    → 가능일 10일 − 복습 2일 = 학습일 8일 · 하루 15쪽 · 37.5분 → 상한 이내."""
    out = compute()
    assert out["availableDays"] == 10
    assert out["reviewDays"] == 2                    # 중간고사 기본값 (F5-R20)
    assert out["studyDays"] == 8
    assert out["dailyPages"] == 15                   # ceil(120 / 8)
    assert out["dailyMinutes"] == 38                 # 15 × 2.5 = 37.5 → 38분
    assert out["verdict"] == "ok"
    study = [d for d in out["days"] if d["kind"] == "study"]
    assert [d["date"] for d in study] == [f"2026-10-{d}" for d in range(13, 21)]
    assert out["reviewDayDates"] == ["2026-10-21", "2026-10-22"]     # 시험 직전 2일
    assert all(d["pages"] == 0 for d in out["days"] if d["kind"] == "review")


def test_split_sums_to_total():
    """분할 결과의 합이 총 분량과 같아야 한다 — 반올림 오차는 마지막 날이 흡수한다 (9절 '정확성')."""
    for total in (1, 7, 8, 9, 113, 120, 121, 999):
        out = compute(totalPages=total)
        assert out["totals"]["pages"] == total, total
        study = [d for d in out["days"] if d["kind"] == "study"]
        assert all(d["pages"] > 0 for d in study)    # 0쪽 블록은 만들지 않는다
        if len(study) > 1:
            assert study[-1]["pages"] <= study[0]["pages"]


def test_difficulty_changes_minutes():
    """기본 난이도 계수 — 쉬움 1 · 보통 1.5 · 어려움 2분/쪽 (2026-10-02)."""
    assert compute(difficulty="easy")["dailyMinutes"] == 15        # 15 × 1
    assert compute(difficulty="normal")["dailyMinutes"] == 23      # 15 × 1.5 = 22.5 → 23
    assert compute(difficulty="hard")["dailyMinutes"] == 30        # 15 × 2
    assert compute(pageMinutes=3.5)["dailyMinutes"] == 53          # 직접 넣은 값이 난이도를 이긴다 (52.5 → 53)


def test_excluded_dates_redistribute():
    """제외일은 0쪽으로 두고 나머지에 재분배한다 (F5-R22)."""
    out = compute(excludedDates=["2026-10-15", "2026-10-19"])
    assert out["studyDays"] == 6
    assert out["dailyPages"] == 20                   # ceil(120 / 6)
    assert out["totals"]["pages"] == 120
    skipped = [d for d in out["days"] if d["kind"] == "excluded"]
    assert [d["date"] for d in skipped] == ["2026-10-15", "2026-10-19"]
    assert all(d["pages"] == 0 and d["minutes"] == 0 for d in skipped)
    assert any(w["code"] == "excluded" for w in out["warnings"])


def test_excluded_review_day_shifts_review_earlier():
    """마무리 복습일이 제외일이면 그 앞으로 밀려 잡힌다."""
    out = compute(excludedDates=["2026-10-22"])
    assert out["reviewDayDates"] == ["2026-10-20", "2026-10-21"]


def test_review_days_option():
    assert compute(reviewDays=0)["studyDays"] == 10
    assert compute(reviewDays=0)["reviewDayDates"] == []
    assert compute(reviewDays=4)["studyDays"] == 6
    quiz = compute(reviewDays=2, includeQuiz=True, quizCount=20)
    review = [d for d in quiz["days"] if d["kind"] == "review"]
    assert [d["quiz"] for d in review] == [10, 10]   # 문제도 복습일에 나눠 넣는다 (F5-R13)
    assert quiz["totals"]["quiz"] == 20


def test_review_minutes_are_skim_not_full_read():
    """마무리 복습은 '전체 훑기' — 정독 시간의 일부만 잡는다 (config.REVIEW_SKIM_RATIO)."""
    out = compute()
    review = [d for d in out["days"] if d["kind"] == "review"]
    expected = round(120 * 2.5 * C.REVIEW_SKIM_RATIO / 2)
    assert [d["minutes"] for d in review] == [expected, expected]


# ---------------------------------------------------------------- 상한 검사 (F5 5절 표)

def test_over_cap_warns_with_numbers():
    """하루 시간이 상한을 넘으면 숫자로 경고한다 (F5-R25)."""
    out = compute(totalPages=900, capMinutes=240)
    assert out["verdict"] == "over"
    over = [w for w in out["warnings"] if w["code"] == "over_cap"]
    assert over and "기준" in over[0]["message"]                 # 상한은 옵션이 아니라 하루 기준(4시간)이다 (2026-10-02)
    assert "시간" in over[0]["message"]
    assert out["needsConfirm"] is True
    assert out["canRegister"] is True                # 막지는 않는다 — 확인을 한 번 더 받는다


def test_over_cap_offers_adjustments_that_work():
    """조정안 (F5-R24) — 3개 안에 '분량 줄이기'가 있고, 누르면 실제로 풀린다. '상한 올리기'는 없다 (2026-10-02)."""
    out = compute(totalPages=900, capMinutes=240)
    keys = [a["key"] for a in out["adjustments"]]
    assert len(keys) <= 3 and "less_scope" in keys and "raise_cap" not in keys
    adj = next(a for a in out["adjustments"] if a["key"] == "less_scope")
    again = compute(**{"totalPages": 900, "capMinutes": 240, **adj["apply"]})
    assert again["verdict"] != "over"


def test_review_overflow_offers_review_adjustments():
    """복습일이 넘쳤으면 '분량 줄이기'가 아니라 복습일·문제 수를 권한다."""
    out = compute(totalPages=900, capMinutes=300, includeQuiz=True, quizCount=200)
    assert out["verdict"] == "over"
    peak = max(out["days"], key=lambda d: d["minutes"])
    assert peak["kind"] == "review"
    keys = {a["key"] for a in out["adjustments"]}
    assert "more_review" in keys or "less_quiz" in keys
    assert "less_scope" not in keys


def test_no_time_when_exam_is_today():
    out = P.compute(EXAM, {"totalPages": 100}, date(2026, 10, 23))
    assert out["verdict"] == "no_time"
    assert out["days"] == []
    assert out["canRegister"] is False
    assert any(w["code"] == "no_time" for w in out["warnings"])


def test_no_time_when_only_review_days_left():
    """시험이 내일이면 가능일 1일이 전부 복습일이 된다 → '시간 없음'이지만 복습 블록은 준다."""
    out = P.compute(EXAM, {"totalPages": 100}, date(2026, 10, 22))
    assert out["verdict"] == "no_time"
    assert out["studyDays"] == 0
    assert [d["kind"] for d in out["days"]] == ["review"]
    assert out["canRegister"] is True


def test_overlap_with_other_plans():
    """여러 시험이 겹치면 하루 총 시간을 합산해 검사한다 (F5-R23)."""
    load = {"2026-10-15": {"minutes": 220, "courses": ["컴퓨터네트워크"]}}
    out = P.compute(EXAM, {**DOC}, TODAY, other_load=load)
    assert out["verdict"] == "overlap"
    assert out["overlap"] and out["overlap"][0]["date"] == "2026-10-15"
    assert out["overlap"][0]["minutes"] == 220 + 38
    msg = [w["message"] for w in out["warnings"] if w["code"] == "overlap"]
    assert msg and "컴퓨터네트워크" in msg[0]


def test_overlap_accepts_plain_minutes():
    out = P.compute(EXAM, {"totalPages": 120}, TODAY, other_load={"2026-10-15": 220})
    assert out["verdict"] == "overlap"


# ---------------------------------------------------------------- 시간 단위 · 시작일 · 재조정

def test_minutes_unit_without_materials():
    """자료가 없으면 시간으로 넣는다 (F5-R11 — 화면에서는 뺐지만 명령줄·API 는 받는다)."""
    out = P.compute(EXAM, {"unit": "minutes", "totalMinutes": 480, "reviewDays": 2}, TODAY)
    assert out["totalPages"] == 0
    assert out["totals"]["minutes"] == 480 + sum(
        d["minutes"] for d in out["days"] if d["kind"] == "review")
    assert out["dailyMinutes"] == 60                 # ceil(480 / 8)


def test_start_date_later_than_today():
    out = compute(startDate="2026-10-16")
    assert out["startDate"] == "2026-10-16"
    assert out["studyDays"] == 5
    out = compute(startDate="2026-10-01")            # 오늘보다 앞이면 오늘부터
    assert out["startDate"] == TODAY.isoformat()


def test_carry_keeps_done_days_and_splits_the_rest():
    """재조정 — 완료한 날은 그대로 두고 남은 분량만 남은 날에 나눈다 (F5 5절)."""
    carry = {"pages": 30, "minutes": 75,
             "days": [{"date": "2026-10-13", "weekday": "화", "pages": 30, "minutes": 75,
                       "kind": "study", "quiz": 0, "done": True, "moved": False}]}
    out = P.compute(EXAM, {"totalPages": 120, "reviewDays": 2}, date(2026, 10, 14), carry=carry)
    assert out["carried"] == {"pages": 30, "minutes": 75, "days": 1}
    assert out["totals"]["pages"] == 120             # 완료분 + 남은 분량 = 총 분량
    assert out["days"][0]["done"] is True
    assert out["studyDays"] == 7                     # 10/14~10/20
    assert out["dailyPages"] == 13                   # ceil(90 / 7)


def test_carry_day_is_not_split_twice():
    """이미 완료한 날이 오늘이어도 그 날에 블록이 둘 생기지 않는다."""
    carry = {"pages": 15, "minutes": 38,
             "days": [{"date": TODAY.isoformat(), "weekday": "화", "pages": 15, "minutes": 38,
                       "kind": "study", "quiz": 0, "done": True, "moved": False}]}
    out = P.compute(EXAM, {**DOC}, TODAY, carry=carry)
    dates = [d["date"] for d in out["days"]]
    assert len(dates) == len(set(dates))
    assert out["totals"]["pages"] == 120


# ---------------------------------------------------------------- 옵션 검사

@pytest.mark.parametrize("options", [
    {},                                              # 쪽수도 시간도 없다
    {"totalPages": -1},
    {"totalPages": 100, "difficulty": "보통"},
    {"totalPages": 100, "pageMinutes": 0},
    {"totalPages": 100, "pageMinutes": 999},
    {"totalPages": 100, "reviewDays": 99},
    {"totalPages": 100, "capMinutes": 5},
    {"totalPages": 100, "excludedDates": ["10/15"]},
    {"totalPages": 100, "startDate": "언젠가"},
    {"unit": "days", "totalPages": 100},
])
def test_bad_options_rejected(options):
    with pytest.raises(P.Invalid):
        P.compute(EXAM, options, TODAY)


def test_review_day_default_is_one_day_for_every_type():
    """마무리 복습 기본값은 모든 유형에서 시험 전날 하루 (2026-10-02)."""
    for t in ("midterm", "final", "quiz", "presentation", "etc"):
        out = P.compute({**EXAM, "type": t}, {"totalPages": 40}, TODAY)
        assert out["reviewDays"] == 1 and out["reviewDayDates"] == ["2026-10-22"], t


def test_no_raise_cap_adjustment():
    """하루 상한은 옵션이 아니다 — '상한 올리기'를 권하지 않는다 (2026-10-02). 경고는 숫자로 남는다."""
    out = compute(totalPages=900)
    assert out["verdict"] == "over"
    assert "raise_cap" not in {a["key"] for a in out["adjustments"]}
    assert any("시간" in w["message"] for w in out["warnings"] if w["code"] == "over_cap")
