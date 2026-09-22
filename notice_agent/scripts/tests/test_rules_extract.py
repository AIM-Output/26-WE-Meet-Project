"""규칙 추출·날짜 파싱 테스트 — 실제 공지 문장(2026-09 수집분)에서 가져온 표현들."""
from scripts.rules_extract import extract_rules
from scripts.textutil import is_grounded, parse_date, parse_period

DONGCHANG = """2026학년도 전남대학교 동창장학회 장학생을 선발하오니 해당하는 학생은 지원서를 제출하여 주시기 바랍니다.
1. 대상: 인공지능학부 재학생 동창회비 납부자
2. 신청자격
가. 2학기 이상 재학한 학생으로 가정환경이 어려운 자
나. 2025학년도 2학기 포함 전체 학기 평점이 3.5/4.5 이상인 자
다. 2026학년도 1학기 기준 한국장학재단 소득구간이 5구간 이하인 자
3. 제외사유
가. 휴학생, 휴학 예정 학생(군입대 포함)
4. 선발인원 1명 (생활비 200만원)
6. 제출서류 장학생 선발 신청서 1부, 재학증명서 1부, 성적증명서 1부, 한국장학재단 2026학년도 1학기 학자금 지원구간 통지서 1부.
7. 제출기간: 2026년 1월 19일(월) ~ 20일(화)
8. 제출방법: 학과실(AI융합대학 205호) 직접 방문
9. 문의사항: 인공지능학부실 530-4206"""

KUNRO = """2. 신청기간: 2026. 8. 12.(수) 09:00 ~ 2026. 9. 9.(수) 18:00
3. 신청자격: 대한민국 국적자 중 대학(교)에 재학 중인(복학생 포함) 학생으로 성적요건 및 소득요건을 충족한 학생
  - 성적기준: 직전학기 성적이 70점/100점 만점 이상인 자
  - 소득요건: 학자금 지원 9구간 이하
4. 국가근로장학금 신청 제외자: 휴학생, 졸업자, 자퇴자, 외국인학생"""

DOOEUL = """√ 26년 2학기 기준 국내 4년제 대학교 1학년 2학기 재학 중인 여자 대학생
√ 26년 정규 1학기 총 15학점 이상을 이수하고, 성적 3.5/4.5 이상 취득자
√ 대한민국 국적을 가진 자에 한함
선발인원 30명
접수기간 2026. 09. 01.(월) ~ 09. 30.(화) 18:00"""


def test_dongchang_rules():
    r = extract_rules("[장학] 2026학년도 전남대학교동창장학회 장학생 선발 안내", DONGCHANG)
    assert r.min_semesters_completed == 2
    assert r.min_gpa and r.min_gpa.value == 3.5 and r.min_gpa.scale == 4.5
    assert r.income_bracket_max == 5
    assert r.enrollment_status == ["재학"]
    assert r.application_period and r.application_period.start == "2026-01-19" and r.application_period.end == "2026-01-20"
    assert any("동창회비 납부자" in c for c in r.other_conditions)      # 전공·비정형 조건은 구조화하지 않고 남긴다
    assert r.major_include is None
    assert any("휴학생" in e for e in r.exclusions)
    assert r.selection_count == "1명"
    assert r.contact and "530-4206" in r.contact
    assert r.required_documents and any("재학증명서" in d for d in r.required_documents)
    assert r.confidence <= 0.6                                          # 규칙만으로는 자동 판정 문턱을 넘지 않는다
    fields = {e.field for e in r.evidence}
    assert {"min_gpa", "income_bracket_max", "min_semesters_completed", "application_period"} <= fields


def test_kunro_percent_scale_and_period_with_time():
    r = extract_rules("[장학안내] 2026학년도 2학기 2차 국가근로장학금 학생 신청 안내", KUNRO)
    assert r.min_gpa and r.min_gpa.value == 70 and r.min_gpa.scale == 100 and r.min_gpa.basis == "직전학기"
    assert r.income_bracket_max == 9
    assert r.nationality == "대한민국"
    assert r.application_period.start == "2026-08-12T09:00" and r.application_period.end == "2026-09-09T18:00"
    assert r.kind == "국가"


def test_dooeul_credits_and_short_dates_inherit_year():
    r = extract_rules("[장학안내][두을장학재단] 제29기 두을장학생 모집 안내", DOOEUL)
    assert r.min_credits_total == 15
    assert r.min_gpa.value == 3.5
    assert r.selection_count == "30명"
    assert r.application_period.start == "2026-09-01" and r.application_period.end == "2026-09-30T18:00"
    assert r.provider == "두을장학재단" and r.kind == "교외"


def test_grades_expressions():
    assert extract_rules("t", "지원자격: 3학년 이상 재학생").grades_allowed == [3, 4]
    assert extract_rules("t", "자연과학 및 공학계열 1,3학년 재학생").grades_allowed == [1, 3]
    assert extract_rules("t", "2학년 이상 4학년 이하 재학생").grades_allowed == [2, 3, 4]
    assert extract_rules("t", "2~3학년 재학생").grades_allowed == [2, 3]
    assert extract_rules("t", "일반학과 3학년 이상 학생으로 중소기업 취업희망자").grades_allowed == [3, 4]


def test_gpa_is_not_mistaken_for_date():
    # '3.5/4.5' 를 3월 5일로 읽으면 안 된다
    assert parse_date("전체 학기 평점이 3.5/4.5 이상인 자") is None
    assert parse_period("성적 3.5/4.5 이상") == (None, None)


def test_period_variants():
    assert parse_period("~9/16까지") == (None, "2026-09-16") or parse_period("~9/16까지")[1].endswith("-09-16")
    s, e = parse_period("9. 14.(월) ~ 9. 30.(수)")
    assert s.endswith("-09-14") and e.endswith("-09-30")
    s, e = parse_period("2026.9.1.~9.18.")
    assert (s, e) == ("2026-09-01", "2026-09-18")
    assert parse_date("2026년 9월 30일(수)") == "2026-09-30"
    assert parse_date("2026.09.11 13:21") == "2026-09-11T13:21"
    assert parse_date("2월 30일") is None       # 존재하지 않는 날짜


def test_grounding():
    src = "나. 2025학년도 2학기 포함 전체 학기 평점이 3.5/4.5 이상인 자"
    assert is_grounded("전체 학기 평점이 3.5/4.5 이상인 자", src)
    assert is_grounded("평점이  3.5 / 4.5  이상", src)          # 공백·기호 차이 무시
    assert not is_grounded("직전학기 평점 3.0 이상", src)


def test_dooeul_grade_gender_and_docs_filter():
    r = extract_rules("[장학안내][두을장학재단] 제29기 두을장학생 모집 안내", DOOEUL)
    assert r.grades_allowed == [1]                                   # '1학년 2학기 재학 중인'
    assert any("여자 대학생" in c for c in r.other_conditions)         # 성별 조건은 비정형 조건으로 남긴다


def test_period_prefers_application_line_over_validity_period():
    text = "√ 외국어 자격증 사본 (유효기간 : 2024.09.01.~2026.09.30.이내 유효성적)\n접수기간 2026. 09. 01.(월) ~ 09. 30.(화) 18:00"
    r = extract_rules("t", text)
    assert r.application_period.start == "2026-09-01" and r.application_period.end == "2026-09-30T18:00"


def test_documents_drop_table_cell_noise():
    text = "구비서류\n본인\n필수서류\n√ 대학교 재학증명서 1부\n√ 대학교 성적증명서 1부\n기타\n(해당자만)\n√ 사회봉사활동 확인서"
    r = extract_rules("t", text)
    assert r.required_documents == ["대학교 재학증명서 1부", "대학교 성적증명서 1부", "사회봉사활동 확인서"]
