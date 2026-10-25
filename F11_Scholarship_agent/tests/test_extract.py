"""요건 추출 규칙 — 근거(원문 한 줄)가 붙는지, 날짜가 아닌 숫자를 날짜로 읽지 않는지."""
from scholarship import extract as X


def test_basic_fields_with_evidence():
    body = ("1. 지원자격: 본교 2학년 이상 재학생\n"
            "2. 성적기준: 직전학기 평점 3.0/4.5 이상, 직전학기 12학점 이상 이수\n"
            "3. 소득기준: 학자금 지원 8구간 이하\n"
            "4. 신청기간: 2026. 10. 1.(수) ~ 2026. 10. 20.(월) 18:00\n"
            "5. 제출서류: 장학금 신청서 1부, 성적증명서 1부\n")
    r = X.extract("[장학안내] [(재)테스트장학재단] 2026 장학생 선발", body)
    assert r["grades"] == [2, 3, 4]
    assert r["minGpa"] == {"value": 3.0, "scale": 4.5, "basis": "직전학기"}
    assert r["minCreditsLast"] == 12
    assert r["incomeMax"] == 8
    assert r["period"]["end"] == "2026-10-20T18:00"
    assert r["evidence"]["minGpa"].startswith("2. 성적기준")
    assert r["provider"] == "(재)테스트장학재단" and r["kind"] == "교외"
    assert r["confidence"] >= 0.6


def test_gpa_line_is_not_a_period():
    """'평점 3.5 이상(4.5 만점 기준) … 까지' 를 3월 5일~4월 3일로 읽던 실측 버그 (대전청년내일재단, 2026-10-09)."""
    body = "3. 직전 학기까지의 전체 평균 평점 3.5 이상(4.5 만점 기준) 또는 3.3 이상(4.3 만점 기준) 성적을 가진 학생"
    r = X.extract("[장학안내] 성취장학생 선발", body, default_year=2026)
    assert r["period"] is None
    assert r["minGpa"]["value"] == 3.5


def test_catalog_gpa_with_parenthesis():
    r = X.extract("진리장학금", "[우수 장학금]\n▷ 성적이 우수하고 품행이 단정한 자\n- 재학생: 직전 학기 평균평점이 2.5(실점 79.99점) "
                                   "이상이고, 12학점 이상 이수한 자 중에서 선발", catalog=True)
    assert r["minGpa"]["value"] == 2.5 and r["minCreditsLast"] == 12
    assert r["otherConditions"] == []                       # '누구나'에 가까운 문구는 조건으로 남기지 않는다


def test_catalog_special_condition_kept():
    r = X.extract("학군단 장학금", "[특별 장학금]\n▷ 학군단 장학생으로 선발된 자 - 직전학기 평균평점이 2.5 이상이고 12학점 이상 이수한 자",
                  catalog=True)
    assert any("학군단" in c for c in r["otherConditions"])


def test_grades_and_freshman_patterns():
    assert X.grades("국내 4년제 대학의 자연과학 및 공학계열 학과에 재학 중인 1학년 및 3학년")[0] == [1, 3]
    assert X.grades("재학 중인 신입생 및 3학년")[0] == [1, 3]
    assert X.grades("3학년 이상")[0] == [3, 4]


def test_fields_groups_campus_college():
    r = X.extract("[장학안내] 2027년 의생명과학분야 대학 장학생 선발 안내", "")
    assert r["fields"] == ["의약"]
    r = X.extract("[장학안내] [전남동부보훈지청] 2026학년도 2학기 보훈(가족)장학 신청", "")
    assert r["groups"][0]["profileKey"] == "veteranFamily" and r["groupsSure"]
    r = X.extract("[장학안내] 2026학년도 다문화·탈북학생 멘토링 장학금 멘토(학부생) 모집", "")
    assert not r["groups"]                                   # 돕는 활동(멘토) 모집 — 대상 집단이 아니다
    r = X.extract("[장학안내] 2026학년도 여수캠퍼스 청경나래 장학금", "")
    assert r["campus"] == "여수"
    r = X.extract("[장학안내] 사회과학대학 2026학년도 성취·성장 장학사업 안내", "")
    assert r["colleges"] == ["사회과학대학"]


def test_not_for_undergrads_and_info_only():
    assert X.extract("2026학년도 2학기 대학원 저소득층(창조) 장학금 신청 안내", "")["gradOnly"]
    assert not X.extract("[한국장학재단]2026년 2학기 농촌출신대학(원)생 학자금 대출", "")["gradOnly"]
    assert X.extract("[장학안내] 2026년 장학금 부정수급 자진신고 캠페인 홍보", "")["infoOnly"]
    assert not X.extract("[장학안내] 고졸 후학습자 장학사업 신규장학생 신청기간 연장 안내", "")["infoOnly"]


def test_image_only_needs_ocr():
    r = X.extract("[장학안내] 장학생 선발", "", image_only=True)
    assert r["needsOcr"] and r["confidence"] == 0.0
