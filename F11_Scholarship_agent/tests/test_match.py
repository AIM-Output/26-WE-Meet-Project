"""판정 규칙 — 요구사항정의서 F11 5절 (해당 / 확인 필요 / 비해당 / 마감 / 대상 아님) + 조건별 근거."""
from conftest import TODAY

from scholarship import extract as X
from scholarship import match as M

FULL = ("1. 지원자격: 본교 2학년 이상 재학생\n2. 성적기준: 직전학기 평점 3.0/4.5 이상, 직전학기 12학점 이상 이수\n"
        "3. 신청기간: 2026. 10. 1.(수) ~ 2026. 10. 20.(월) 18:00\n4. 제출서류: 장학금 신청서 1부\n")


def decide(title, body, profile, **notice):
    return M.decide(X.extract(title, body, default_year=2026), profile, {"title": title, **notice}, TODAY)


def test_eligible_with_reasons(profile):
    r = decide("[장학안내] [(재)테스트장학재단] 장학생 선발", FULL, profile)
    assert r["verdict"] == "eligible" and r["label"] == "해당"
    gpa = next(x for x in r["reasons"] if x["field"] == "minGpa")
    assert gpa["status"] == "pass" and "3.6" in gpa["message"] and gpa["evidence"]
    assert r["daysLeft"] == 11


def test_unknown_profile_value_is_review_not_fail(profile):
    profile["lastSemesterGpa"] = None
    profile["gpa"] = None
    r = decide("[장학안내] 장학생 선발", FULL, profile)
    assert r["verdict"] == "needs_review"
    assert next(x for x in r["reasons"] if x["field"] == "minGpa")["status"] == "unknown"


def test_scale_mismatch_is_unknown(profile):
    profile["lastSemesterGpa"] = {"value": 3.9, "scale": 4.3, "basis": "직전학기"}
    r = decide("[장학안내] 장학생 선발", FULL, profile)
    g = next(x for x in r["reasons"] if x["field"] == "minGpa")
    assert g["status"] == "unknown" and "환산하지 않습니다" in g["message"]


def test_fail_is_ineligible(profile):
    profile["grade"] = 1
    assert decide("[장학안내] 장학생 선발", FULL, profile)["verdict"] == "ineligible"


def test_expired_and_not_applicable(profile):
    body = FULL.replace("2026. 10. 20.(월)", "2026. 9. 20.(일)")
    assert decide("[장학안내] 장학생 선발", body, profile)["verdict"] == "expired"
    assert decide("[장학안내] 2026학년도 대학원 저소득층 장학금 신청 안내", FULL, profile)["verdict"] == "not_applicable"
    assert decide("[장학안내] 2학기 국가근로장학생 선발 결과", FULL, profile, isResult=True)["verdict"] == "not_applicable"


def test_sensitive_income_prompt(profile):
    r = decide("[장학안내] 장학생 선발", FULL + "5. 소득기준: 학자금 지원 8구간 이하\n", profile)
    inc = next(x for x in r["reasons"] if x["field"] == "incomeMax")
    assert inc["status"] == "unknown" and inc["sensitive"] == "incomeBracket"
    assert r["hint"] == "정보 입력 필요" and "incomeBracket" in r["sensitive"]
    profile["incomeBracket"] = 9
    assert decide("[장학안내] 장학생 선발", FULL + "5. 소득기준: 학자금 지원 8구간 이하\n", profile)["verdict"] == "ineligible"


def test_regional_title_fail_even_when_body_is_image(profile):
    """제목의 [지역 재단]은 본문이 이미지여도 확실하다 — 다만 출신 고교 기준일 수 있어 출신 고교를 모르면 묻는다."""
    title = "[장학안내][(재)포항시장학회] 2026년도 대학교 장학생 선발 안내"
    req = X.extract(title, "", image_only=True)
    r = M.decide(req, profile, {"title": title}, TODAY)
    assert r["verdict"] == "needs_review" and "highSchoolRegion" in r["sensitive"]
    profile["highSchoolRegion"] = "광주"
    r = M.decide(req, profile, {"title": title}, TODAY)
    assert r["verdict"] == "ineligible"


def test_regional_body_says_address_only(profile):
    body = FULL + "※ 신청자격: 본인 또는 부모가 포항시에 1년 이상 주소를 둔 자\n"
    assert decide("[장학안내][(재)포항시장학회] 장학생 선발", body, profile)["verdict"] == "ineligible"


def test_regional_same_province_pass(profile):
    r = decide("[장학안내] [전남광주통합특별시] 광주권 대학생 학자금대출 이자지원 안내", FULL, profile)
    assert next(x for x in r["reasons"] if x["field"] == "residency")["status"] == "pass"


def test_college_and_campus_from_title(profile):
    assert decide("[장학안내] 사회과학대학 2026학년도 성취·성장 장학사업 안내", FULL, profile)["verdict"] == "ineligible"
    assert decide("[장학안내] 2026학년도 여수캠퍼스 청경나래 장학금", FULL, profile)["verdict"] == "ineligible"
    assert decide("[장학안내] AI융합대학 성취 장학 안내", FULL, profile)["verdict"] == "eligible"


def test_groups(profile):
    t = "[장학안내] [전남동부보훈지청] 2026학년도 2학기 보훈(가족)장학 신청 안내"
    assert decide(t, FULL, profile)["verdict"] == "ineligible"            # 해당 사항 '없음'을 골랐다
    profile["flags"] = None
    r = decide(t, FULL, profile)
    assert r["verdict"] == "needs_review" and "flags" in r["sensitive"]    # 아직 안 물어봤다 → 묻는다
    profile["flags"] = {"veteranFamily": True}
    assert decide(t, FULL, profile)["verdict"] == "eligible"


def test_user_override_keeps_reasons(profile):
    profile["grade"] = 1
    req = X.extract("[장학안내] 장학생 선발", FULL, default_year=2026)
    r = M.decide(req, profile, {}, TODAY, override={"verdict": "eligible"})
    assert r["verdict"] == "eligible" and r["systemVerdict"] == "ineligible" and r["flipped"]
    assert r["warning"] == "조건 미달 항목이 있습니다"
    assert any(x["status"] == "fail" for x in r["reasons"])


def test_unrelated_project_is_review(profile):
    from scholarship import registry
    profile.update(college="인문대학", department="사학과")
    unit = registry.get("battery")
    r = M.decide(X.extract("이차전지융합전공 장학생 모집", FULL, default_year=2026), profile, {"unit": unit}, TODAY)
    u = next(x for x in r["reasons"] if x["field"] == "unit")
    assert u["status"] == "unknown" and r["verdict"] == "needs_review"
