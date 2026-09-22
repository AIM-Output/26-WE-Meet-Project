"""LLM 결과 병합·근거 검증 테스트 — 네트워크 없이 가짜 LLM 출력으로 merge() 만 검증."""
from scripts.extract import LLMRequirements, merge
from scripts.rules_extract import extract_rules
from scripts.schemas import GPA, Evidence
from scripts.tests.test_rules_extract import DONGCHANG


def test_ungrounded_llm_value_is_dropped_and_rule_value_kept():
    rules = extract_rules("t", DONGCHANG)
    llm = LLMRequirements(
        min_gpa=GPA(value=3.0, scale=4.5),                      # 원문은 3.5 — 근거도 지어냄
        income_bracket_max=5,
        evidence=[Evidence(field="min_gpa", quote="평점 3.0 이상인 자"),
                  Evidence(field="income_bracket_max", quote="한국장학재단 소득구간이 5구간 이하인 자")],
    )
    req = merge(rules, llm, DONGCHANG)
    assert req.min_gpa.value == 3.5                              # 근거 없는 LLM 값 → 규칙 값으로 대체
    assert req.income_bracket_max == 5
    assert any("min_gpa" in n for n in req.notes)
    assert req.extractor == "llm+rules"


def test_semester_sentence_cannot_ground_grade_field():
    # 실측 사례: '2학기 이상 재학한 학생' 을 근거로 학년 [2,3,4] 를 만든 경우 → 근거 무관 처리로 값이 빠져야 한다
    rules = extract_rules("t", DONGCHANG)
    llm = LLMRequirements(grades_allowed=[2, 3, 4],
                          evidence=[Evidence(field="grades_allowed", quote="2학기 이상 재학한 학생")])
    req = merge(rules, llm, DONGCHANG)
    assert req.grades_allowed is None
    assert req.min_semesters_completed == 2


def test_llm_needs_ocr_not_trusted_when_body_is_long():
    rules = extract_rules("t", DONGCHANG)
    llm = LLMRequirements(needs_ocr=True)
    req = merge(rules, llm, DONGCHANG)
    assert req.needs_ocr is False


def test_agreement_raises_confidence_above_threshold():
    rules = extract_rules("t", DONGCHANG)
    llm = LLMRequirements(
        min_semesters_completed=2, min_gpa=GPA(value=3.5, scale=4.5, basis="전체"), income_bracket_max=5,
        enrollment_status=["재학"],
        evidence=[Evidence(field="min_semesters_completed", quote="2학기 이상 재학한 학생으로 가정환경이 어려운 자"),
                  Evidence(field="min_gpa", quote="전체 학기 평점이 3.5/4.5 이상인 자"),
                  Evidence(field="income_bracket_max", quote="한국장학재단 소득구간이 5구간 이하인 자"),
                  Evidence(field="enrollment_status", quote="인공지능학부 재학생 동창회비 납부자")],
    )
    req = merge(rules, llm, DONGCHANG)
    assert req.confidence >= 0.6
    assert all(e.grounded for e in req.evidence if e.field in ("min_gpa", "income_bracket_max"))
