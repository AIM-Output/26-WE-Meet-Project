"""매칭 규칙 경계값 테스트 — 여기는 테스트가 필수다 (AI_MODULES `rule`/`notice` 완료기준).

    .venv\\Scripts\\python -m pytest scripts/tests -q
"""
from datetime import date

import pytest

from scripts.match import decide
from scripts.schemas import GPA, Evidence, Period, Profile, Requirements

TODAY = date(2026, 9, 13)


def prof(**kw) -> Profile:
    base = dict(grade=3, semesters_completed=5, enrollment_status="재학", college="AI융합대학",
                department="인공지능학부", field_group="공학계열", gpa=GPA(value=3.8, scale=4.5),
                earned_credits=84, last_semester_credits=18, income_bracket=6, nationality="대한민국")
    base.update(kw)
    return Profile(**base)


def req(**kw) -> Requirements:
    base = dict(confidence=0.9, application_period=Period(end="2026-09-30"))
    base.update(kw)
    return Requirements(**base)


def verdict(r: Requirements, p: Profile, **kw) -> str:
    return decide(r, p, today=TODAY, **kw).verdict


# ── 학년 ────────────────────────────────────────────────────
def test_grade_pass_and_fail():
    assert verdict(req(grades_allowed=[3, 4]), prof(grade=3)) == "eligible"
    assert verdict(req(grades_allowed=[3, 4]), prof(grade=2)) == "ineligible"


def test_grade_unknown_when_profile_missing():
    assert verdict(req(grades_allowed=[3, 4]), prof(grade=None)) == "needs_review"


# ── 평점: 경계값 '딱 충족' 은 통과, 척도 다르면 확인 필요 ─────────
def test_gpa_boundary_exact():
    assert verdict(req(min_gpa=GPA(value=3.5, scale=4.5)), prof(gpa=GPA(value=3.5, scale=4.5))) == "eligible"
    assert verdict(req(min_gpa=GPA(value=3.5, scale=4.5)), prof(gpa=GPA(value=3.49, scale=4.5))) == "ineligible"


def test_gpa_scale_mismatch_is_review_not_fail():
    r = req(min_gpa=GPA(value=70, scale=100, basis="직전학기"))
    assert verdict(r, prof()) == "needs_review"                       # 백분위 값이 없다
    assert verdict(r, prof(last_semester_gpa_percent=71.0)) == "eligible"
    assert verdict(r, prof(last_semester_gpa_percent=69.9)) == "ineligible"


def test_gpa_last_semester_falls_back_to_overall():
    r = req(min_gpa=GPA(value=3.0, scale=4.5, basis="직전학기"))
    assert verdict(r, prof(last_semester_gpa=None)) == "eligible"     # 전체 평점으로 대신 판정 (근거 문구에 표시)


# ── 학점 / 학기 ───────────────────────────────────────────
def test_credits_total_and_last_semester():
    assert verdict(req(min_credits_total=84), prof(earned_credits=84)) == "eligible"
    assert verdict(req(min_credits_total=85), prof(earned_credits=84)) == "ineligible"
    assert verdict(req(min_credits_last_semester=12), prof(last_semester_credits=12)) == "eligible"
    assert verdict(req(min_credits_last_semester=12), prof(last_semester_credits=None)) == "needs_review"


def test_semesters():
    assert verdict(req(min_semesters_completed=2), prof(semesters_completed=2)) == "eligible"
    assert verdict(req(min_semesters_completed=6), prof(semesters_completed=5)) == "ineligible"


# ── 전공: 이름 일치 / 계열 별칭 / 판단 불가 ─────────────────────
def test_major_include_by_department_name():
    assert verdict(req(major_include=["인공지능학부"]), prof()) == "eligible"
    assert verdict(req(major_include=["경영학부"]), prof()) == "ineligible"


def test_major_include_by_field_group_alias():
    assert verdict(req(major_include=["자연과학 및 공학계열"]), prof(field_group="공학계열")) == "eligible"
    assert verdict(req(major_include=["이공·상경·인문사회 계열"]), prof(field_group="공학계열")) == "eligible"


def test_major_include_unknown_when_no_field_group():
    # 계열 표현인데 프로필에 계열 정보가 없으면 '비해당' 이 아니라 '확인 필요'
    assert verdict(req(major_include=["예체능계열"]), prof(field_group=None)) == "needs_review"


def test_major_exclude():
    assert verdict(req(major_exclude=["인공지능학부"]), prof()) == "ineligible"
    assert verdict(req(major_exclude=["의약계열"]), prof(field_group="공학계열")) == "needs_review"


# ── 소득구간 / 국적 / 학적 ───────────────────────────────────
def test_income_bracket():
    assert verdict(req(income_bracket_max=8), prof(income_bracket=8)) == "eligible"
    assert verdict(req(income_bracket_max=5), prof(income_bracket=6)) == "ineligible"
    assert verdict(req(income_bracket_max=5), prof(income_bracket=None)) == "needs_review"


def test_nationality_and_enrollment():
    assert verdict(req(nationality="대한민국"), prof(nationality="미국")) == "ineligible"
    assert verdict(req(enrollment_status=["재학"]), prof(enrollment_status="휴학")) == "ineligible"
    assert verdict(req(enrollment_status=["재학", "휴학"]), prof(enrollment_status="휴학")) == "eligible"


# ── 비정형 조건·제외 사유는 자동 판정하지 않는다 ─────────────────
def test_other_conditions_force_review():
    r = req(other_conditions=["동창회비 납부자"])
    mr = decide(r, prof(), today=TODAY)
    assert mr.verdict == "needs_review"
    assert any("동창회비" in x.message for x in mr.reasons)


# ── 마감 / 신뢰도 / 결과 공지 ────────────────────────────────
def test_deadline_boundary():
    assert decide(req(application_period=Period(end="2026-09-13")), prof(), today=TODAY).verdict == "eligible"   # 마감 당일은 아직 유효
    mr = decide(req(application_period=Period(end="2026-09-12")), prof(), today=TODAY)
    assert mr.verdict == "expired" and mr.days_left == -1


def test_low_confidence_never_auto_decides():
    # 규칙상 '비해당' 이어도 추출 신뢰도가 낮으면 확인 필요
    assert verdict(req(grades_allowed=[4], confidence=0.4), prof(grade=3)) == "needs_review"
    assert verdict(req(needs_ocr=True, confidence=0.9), prof()) == "needs_review"


def test_result_notice_not_applicable():
    assert verdict(req(), prof(), is_result_notice=True) == "not_applicable"


def test_reasons_carry_evidence():
    r = req(grades_allowed=[3, 4], evidence=[Evidence(field="grades_allowed", quote="3학년 이상 재학생")])
    mr = decide(r, prof(grade=2), today=TODAY)
    fail = next(x for x in mr.reasons if x.status == "fail")
    assert fail.evidence == "3학년 이상 재학생" and "현재 2학년" in fail.message


def test_same_input_same_output():
    r, p = req(grades_allowed=[3, 4], min_gpa=GPA(value=3.5, scale=4.5)), prof()
    a, b = decide(r, p, today=TODAY), decide(r, p, today=TODAY)
    assert a.model_dump(exclude={"matched_at"}) == b.model_dump(exclude={"matched_at"})


def test_recently_expired_low_confidence_goes_to_review():
    # 저신뢰 추출의 마감일은 틀릴 수 있다 → 최근 지난 건은 확인 필요, 오래 지난 건은 expired
    assert decide(req(application_period=Period(end="2026-09-10"), confidence=0.4), prof(), today=TODAY).verdict == "needs_review"
    assert decide(req(application_period=Period(end="2026-07-01"), confidence=0.4), prof(), today=TODAY).verdict == "expired"
    assert decide(req(application_period=Period(end="2026-09-10"), confidence=0.9), prof(), today=TODAY).verdict == "expired"
