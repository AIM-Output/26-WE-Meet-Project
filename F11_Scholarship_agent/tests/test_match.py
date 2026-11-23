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


def test_labeled_deadline_expires_even_with_few_conditions(profile):
    """이름표('모집기간')가 붙은 줄에서 글자로 읽은 마감은 조건을 덜 뽑았어도(저신뢰) 믿는다 — 지난 공지가 '확인 필요'에 3주 남지 않게."""
    body = "□ (모집기간) ’26. 9. 26.(토) ~ ’26. 10. 5.(월)\n□ (신청방법) 공식 홈페이지를 통한 온라인 신청"
    r = decide("[장학안내] SW 아카데미 교육생 모집 안내", body, profile)                  # TODAY = 2026-10-09
    assert r["confidence"] < 0.6 and r["verdict"] == "expired"
    r = decide("[장학안내] SW 아카데미 교육생 모집 안내", "서류는 2026. 10. 5.(월)까지 방문 접수", profile)
    assert r["verdict"] == "needs_review" and "지났을 수" in r["reasons"][0]["message"]   # 이름표 없는 줄은 예전대로 3주 보류


def test_ocr_deadline_is_not_trusted_as_expired(profile):
    req = X.extract("[장학안내] ○○재단 장학생 선발", "", default_year=2026, ocr_text="[본문 이미지 OCR]\n제출기한 : 2026. 10. 5.(월)")
    r = M.decide(req, profile, {"title": "t"}, TODAY)
    assert req["period"]["strong"] and req["ocrFields"] == ["period"]
    assert r["verdict"] == "needs_review" and "지났을 수" in r["reasons"][0]["message"]   # OCR 로 읽은 날짜는 틀렸을 수 있다


LONG = "장학생 신청 기간 및 방법을 안내하오니 학생 여러분은 적극 신청하여 주시기 바랍니다. " * 7


def test_fail_read_from_body_text_stands_even_with_ocr_attachment(profile):
    body = LONG + "\n1. 신청기간: 2026. 10. 1.(목) ~ 2026. 10. 20.(화)\n2. 신청자격: 1학년 재학생\n"
    ocr = "[첨부 OCR: 신청 방법.pdf]\n홈페이지 접속 후 로그인"
    req = X.extract("[장학안내] 장학생 선발", body, default_year=2026, ocr_text=ocr)
    assert not req["ocrCapped"] and M.decide(req, profile, {}, TODAY)["verdict"] == "ineligible"   # 미달 조건을 본문 글자에서 읽었다
    req = X.extract("[장학안내] 장학생 선발", body.replace("2. 신청자격: 1학년 재학생\n", ""), default_year=2026,
                    ocr_text=ocr + "\n신청자격 : 1학년 재학생")
    r = M.decide(req, profile, {}, TODAY)
    assert r["verdict"] == "needs_review" and "OCR" in r["reasons"][0]["message"]                 # OCR 에서 읽은 조건의 미달은 단정하지 않는다


def test_process_notice_is_not_applicable(profile):
    r = decide("[장학안내]2026학년도 2학기 도전장학생(비상) 선발 2단계 면접평가 안내", "2. 면접일시: 2026. 11. 6.(금) 09:30~12:00", profile)
    assert r["verdict"] == "not_applicable" and "선발 절차" in r["reasons"][0]["message"]


def test_only_exclusions_left_is_eligible(profile):
    """조건을 모두 충족하고 제외 사유만 남으면 '해당' — 제외 사유는 근거에 남는다 (2026-11-23 결정)."""
    body = FULL + "5. 신청 제외자: 휴학생, 졸업생, 국가근로 부정수급 제재 대상자\n"
    r = decide("[장학안내] [(재)테스트장학재단] 장학생 선발", body, profile)
    assert r["verdict"] == "eligible" and r["hint"] == "제외 사유 확인" and r["unknown"] == ["exclusion"]
    assert any(x["field"] == "exclusion" and x["status"] == "unknown" for x in r["reasons"])
    profile["enrollmentStatus"] = "휴학"                        # 프로필로 알 수 있는 제외 사유는 가른다
    r = decide("[장학안내] [(재)테스트장학재단] 장학생 선발", body.replace("본교 2학년 이상 재학생", "본교 2학년 이상"), profile)
    assert r["verdict"] == "ineligible" and any(x["field"] == "exclusion" and x["status"] == "fail" for x in r["reasons"])
    profile["enrollmentStatus"] = "재학"
    r = decide("[장학안내] [(재)테스트장학재단] 장학생 선발", body + "6. 학과장의 추천을 받은 자\n", profile)
    assert r["verdict"] == "needs_review"                      # 추천 같은 기타 조건이 남으면 그대로 확인 필요


def test_percentile_requirement_uses_school_conversion(profile):
    """100점(백분위) 조건 — 전남대 환산(평점×10+55)이 기준을 2점 이상 넘을 때만 충족, 가깝거나 낮으면 모름 (2026-11-23 결정)."""
    body = FULL.replace("직전학기 평점 3.0/4.5 이상", "직전학기 성적 백분위 점수가 70점 이상")
    r = decide("[장학안내] 국가근로장학금 학생 신청 안내", body, profile)             # 직전 학기 3.6 → 91점
    g = next(x for x in r["reasons"] if x["field"] == "minGpa")
    assert g["status"] == "pass" and "환산" in g["message"] and "91점" in g["message"] and r["verdict"] == "eligible"
    profile["lastSemesterGpa"] = {"value": 1.6, "scale": 4.5, "basis": "직전학기"}     # 71점 — 기준과 1점 차이
    g = next(x for x in decide("[장학안내] 국가근로장학금 학생 신청 안내", body, profile)["reasons"] if x["field"] == "minGpa")
    assert g["status"] == "unknown" and "71점" in g["message"]
    profile["lastSemesterGpa"] = {"value": 1.0, "scale": 4.5, "basis": "직전학기"}     # 65점 — 낮아도 미달로 단정하지 않는다
    assert next(x for x in decide("[장학안내] 국가근로장학금 학생 신청 안내", body, profile)["reasons"] if x["field"] == "minGpa")["status"] == "unknown"
    profile["lastSemesterGpa"] = {"value": 3.9, "scale": 4.3, "basis": "직전학기"}     # 4.3 만점은 환산식이 달라 환산하지 않는다
    g = next(x for x in decide("[장학안내] 국가근로장학금 학생 신청 안내", body, profile)["reasons"] if x["field"] == "minGpa")
    assert g["status"] == "unknown" and "환산표" in g["message"]


def test_unrelated_project_is_review(profile):
    from scholarship import registry
    profile.update(college="인문대학", department="사학과")
    unit = registry.get("battery")
    r = M.decide(X.extract("이차전지융합전공 장학생 모집", FULL, default_year=2026), profile, {"unit": unit}, TODAY)
    u = next(x for x in r["reasons"] if x["field"] == "unit")
    assert u["status"] == "unknown" and r["verdict"] == "needs_review"
