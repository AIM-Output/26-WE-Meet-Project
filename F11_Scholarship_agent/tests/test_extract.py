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


# ── 2026-11-23 실측 — '확인 필요'로 쌓이던 공지에서 규칙이 놓친 것 ─────────────────

def test_two_digit_year_and_day_only_end():
    """'26. 을 26월로 읽어 기간을 통째로 놓치던 표기 (한국장학재단·재단 공고문)."""
    from scholarship.textutil import parse_period
    assert parse_period("(신청기간) '26. 11. 16.(월) ~ 26.(목) 18:00") == ("2026-11-16", "2026-11-26T18:00")
    assert parse_period("□ (모집기간) ’26. 10. 26.(월) ~ ’26. 11. 9.(월)") == ("2026-10-26", "2026-11-09")
    assert parse_period("신청기간: '26. 11. 24.(화) 09:00 ~ '27. 1. 7.(목) 18:00") == ("2026-11-24T09:00", "2027-01-07T18:00")
    assert parse_period("(신청기간 26.10.26.(월)~30.(금) 18:00까지)") == ("2026-10-26", "2026-10-30T18:00")
    assert parse_period("9. 14.(월) ~ 9. 30.(수)", 2026) == ("2026-09-14", "2026-09-30")          # 예전 표기는 그대로
    assert parse_period("1월 19일(월) ~ 20일(화)", 2026) == ("2026-01-19", "2026-01-20")
    r = X.extract("[장학안내] SW 아카데미 교육생 모집 안내", "□ (모집기간) ’26. 10. 26.(월) ~ ’26. 11. 9.(월)\n□ (교육기간) ’27. 1. ~ ’27. 12. (1년)")
    assert r["period"]["end"] == "2026-11-09" and r["period"]["strong"]


def test_period_on_the_line_after_its_label():
    body = "1. 학생 신청\n □ 신청 및 서류 제출 기간\n  ㅇ ’26. 10. 22.(수) 9시 ∼ ’26. 11. 12.(목) 18시\n   - 한국장학재단 누리집에서 신청"
    r = X.extract("[장학안내][한국장학재단] 푸른등대 기부장학금(2차) 신규장학생 선발 안내", body)
    assert r["period"]["start"] == "2026-10-22T09:00" and r["period"]["end"] == "2026-11-12T18:00"
    assert r["period"]["strong"] and "’26. 10. 22.(수) 9시" in r["evidence"]["period"]          # 근거는 날짜가 있는 원문 줄
    assert "제출 기간" not in r["evidence"]["period"]                                           # (이름표 줄을 이어 붙인 글자가 아니다)


def test_period_is_not_strong_when_labeled_deadlines_differ():
    body = "2. 신청기간: 2026. 11. 24.(화) 09:00 ~ 2027. 1. 7.(목) 18:00\n- 서류 제출 기간: 2026. 11. 24.(화) ~ 2027. 1. 14.(목)"
    r = X.extract("[장학안내] 2027학년도 1학기 국가장학금 1차 신청 안내", body)
    assert r["period"]["end"] == "2027-01-07T18:00" and not r["period"]["strong"]


def test_percentile_gpa_and_everyone_is_eligible_grade():
    r = X.extract("[장학안내] 국가근로장학금 학생 신청 안내", "3. 신청자격\n- 직전학기 성적 백분위 점수가 70점 이상인 자")
    assert r["minGpa"] == {"value": 70.0, "scale": 100.0, "basis": "직전학기"}
    body = ("1. 신청대상: 신입생, 재학생*, 복학생, 재입학생, 편입생 등 모든 대학생\n"
            "※ 매년 단계적으로 지원 대상 학년 확대 예정\n('27년 1학년 → '28년 1~2학년 → '29년 1~3학년 → '30년 1~4학년)")
    assert X.extract("[장학안내] 국가장학금 1차 신청 안내(지방 국립대학 신입생 등록금 전액 지원 포함)", body)["grades"] is None
    assert X.grades("※ 지원 학년 확대 일정\n('27년 1학년 → '28년 1~2학년)\n신청자격: 2~3학년 재학생")[0] == [2, 3]


def test_process_and_info_notices_are_not_applications():
    for t in ("[장학안내]2026학년도 2학기 도전장학생(비상) 선발 2단계 면접평가 안내",
              "[장학안내]2026학년도 2학기 중소기업 취업연계 장학(희망사다리 I유형) 신규장학생 추천 기준 안내",
              "[장학안내]2026학년도 2학기 도전장학생(비상) 최종 선발 공고"):
        r = X.extract(t, "")
        assert r["infoOnly"] and r["infoKind"] == "process", t
    for t in ("[장학안내][한국장학재단] 청년지원정보 통합제공 플랫폼 '통학로' 안내", "[학사안내]최근 5년 이내 제적생 중 등록금 반환 대상자 안내"):
        r = X.extract(t, "")
        assert r["infoOnly"] and r["infoKind"] == "info", t
    r = X.extract("[장학안내][대산농촌재단] 2027년도 장학생 선발 안내", "")
    assert not r["infoOnly"] and r["infoKind"] is None


def test_preferences_and_notes_are_not_conditions():
    body = ("​1. 추천인원: 학부 재학생 2명(재단에서 최종심사 후 선발인원 확정)\n"
            "○ 지급시기 : 2026. 12. 10.(목) / 노벨평화상 수상 26주년 기념식\n"
            "② 동서화합에 노력한 대학생 또는\n그 분야에 공적이 있는 사람의 대학생 자녀\n"
            "※ 영농기반이 있는 영농희망자, 농학계열 재학생 우대\n"
            "라. 우대사항 : 리더십활동 유경험자\n○ 아래 항목은 서류심사 시 가산점 부여\n- 대한민국인재상 수상\n- 대통령상 또는 국무총리상 수상\n"
            "5. 선발절차 : 대학추천 → 서류심사\n"
            "- 수상 실적 : 수상확인서 또는 상장사본 제출(사본-담당자 확인 후 원본대조필 날인)\n"
            "- 추가 지원에 약정하지 않는 경우 국가장학금 (I유형, 다자녀) 지원 금액으로 지원\n"
            "- 신청 기간동안 2학기 봉사유형 및 취업연계유형 상시신청이 가능합니다.\n"
            "- 전자공학과 재학생으로 지도교수의 추천을 받은 자")
    r = X.extract("[장학안내] ○○재단 장학생 선발 안내", body)
    assert r["otherConditions"] == ["그 분야에 공적이 있는 사람의 대학생 자녀", "전자공학과 재학생으로 지도교수의 추천을 받은 자"]


def test_exclusions_listed_once_and_only_the_list():
    # 머리 줄 아래 글머리표 목록만 — 목록 뒤 설명 문단(▶ …)·동의서 표의 '중복수혜'는 제외 사유가 아니다. 앞의 U+200B 는 게시판 편집기가 넣는다
    body = ("​5. 선발제외대상\n- 휴학생, 국가근로 부정수급자\n- 계절학기 및 현장실습 참여 학생\n"
            "▶ 위 근로학생 중 참여하고자 하는 학생은 '26. 11. 20.(금)까지 기존 근로를 종료하여야 함\n"
            "제공·조회 목적 | 법정 보고·세무, 재학·성적·소득요건·중복수혜 등 확인\n6. 근로기간: 2027. 1. 1.(금) ~ 2. 12.(금)")
    r = X.extract("[장학안내] 국가근로장학금 동계방학 집중근로 신청 안내", body)
    assert r["exclusions"] == ["휴학생, 국가근로 부정수급자", "계절학기 및 현장실습 참여 학생"]
    assert r["otherConditions"] == []                       # 제외 사유로 잡은 줄을 기타 조건에 또 넣지 않는다
    # 한 줄짜리 '… 신청 제외자: …' 는 머리 줄 규칙과 줄 규칙에 두 번 잡힌다 → 하나만
    r = X.extract("[장학안내] 국가근로장학금 학생 신청 안내", "​4. 국가근로장학금 신청 제외자: 휴학생, 졸업생, 자퇴자, 외국인학생\n5. 근로기간: 2027년 3월")
    assert r["exclusions"] == ["휴학생, 졸업생, 자퇴자, 외국인학생"]


def test_catalog_line_with_nothing_left_to_check():
    """평점·학점(구조화)과 '… 중에서 선발'·계획서 제출뿐인 수혜자격 줄은 따로 확인할 조건이 아니다."""
    r = X.extract("취업더하기장학금", "[일반 장학금]\n▷ 직전 학기 평균평점이 1.75 이상이고 12학점 이상 이수한 자로서 취업계획서 제출자 중에서 선발",
                  catalog=True)
    assert r["minGpa"]["value"] == 1.75 and r["minCreditsLast"] == 12 and r["otherConditions"] == []
    r = X.extract("미래성장장학금", "[일반 장학금]\n▷ 직전 학기 평균평점이 1.75 이상이고 12학점 이상 이수한 자로서 장학금 활용 계획서 및 실행 보고서 "
                                  "제출자 중에서 선발", catalog=True)
    assert r["otherConditions"] == []
    assert X.qualification_residue("재학생: 위 해당자 중 직전 학기 평균평점이 1.75(실점 72.5점) 이상이고, 12학점 이상 이수한 자 중에서 선발") == ""
    assert "추천" in X.qualification_residue("직전학기 평균평점이 2.5(실점 79.99점)이상이고 12학점 이상 이수한 자로 학군단장이 추천한 자 중에서 선발")
    assert "선발위원회" in X.qualification_residue("품행이 단정하고 국가와 사회발전에 이바지할 수 있다고 인정된 자로서 장학생 선발위원회에서 선발된 자")


BODY_TEXT = ("국가근로장학금 학생 신청 기간 및 신청 방법을 안내하오니, 학생 여러분은 적극 신청하여 주시기 바랍니다.\n"
             "1. 신청방법: 한국장학재단 홈페이지 또는 모바일 앱 ※ 자세한 방법은 첨부파일 참고\n"
             "2. 신청기간: 2026. 11. 24.(화) 09:00 ~ 2027. 1. 7.(목) 18:00\n"
             "3. 신청자격\n- 대한민국 국적으로 국내 대학의 재학생\n- 직전학기 12학점 이상 이수하고 평점 3.0/4.5 이상인 자\n"
             "4. 근로기간: 2027년 3월 ~ 2027년 8월\n5. 국가근로장학금 통합신청 관련 문의: 1599-2290\n"
             "6. 안내사항\n- 국가근로장학금은 근로장학생의 근로 시간에 따라 장학금이 지급됩니다.\n"
             "- 국가근로장학금은 소속대학이 확정된 학생만 신청할 수 있으며, 소속대학이 미정인 신(편)입생은 2차 학생신청기간을 이용하여야 합니다.\n")
MANUAL_OCR = "[첨부 OCR: 학생신청 방법 (홈페이지).pdf]\n국가근로징학금 : 2027년 1학기\n1자학생신청 방법\n한국장학지1단 홈페이지 접속 후 로그인"


def test_ocr_cap_only_when_a_value_came_from_ocr():
    """본문에 조건이 다 있고 스캔한 신청 매뉴얼만 OCR 로 읽은 공지 — 조건은 글자로 읽힌 본문에서 뽑았으니 묶지 않는다."""
    r = X.extract("[장학안내] 국가근로장학금 학생 신청 안내", BODY_TEXT, ocr_text=MANUAL_OCR)
    assert r["ocr"] and r["ocrFields"] == [] and not r["ocrCapped"] and r["confidence"] >= 0.6
    assert any("본문에서 뽑았습니다" in n for n in r["notes"])
    # 평점이 OCR 덩어리에만 있으면 그 값은 틀렸을 수 있다 → 상한
    r = X.extract("[장학안내] 국가근로장학금 학생 신청 안내", BODY_TEXT.replace("하고 평점 3.0/4.5 이상인 자", "한 자"),
                  ocr_text=MANUAL_OCR + "\n성적기준 : 직전학기 평점 3.0/4.5 이상")
    assert r["ocrFields"] == ["minGpa"] and r["ocrCapped"] and r["confidence"] <= 0.55
    # 글자로 읽힌 원문이 거의 없으면(포스터 공지) OCR 에서 뽑은 값이 없어도 상한
    r = X.extract("[장학안내] ○○재단 장학생 선발", "", ocr_text="[본문 이미지 OCR]\n장학생을 모집합니다\n많은 지원 바랍니다")
    assert r["ocrCapped"] and r["ocrFields"] == []
    # 가르지 않고 받으면(F12 · 예전 방식) 전부 OCR 로 본다
    r = X.extract("[장학안내] ○○재단 장학생 선발", BODY_TEXT, ocr=True)
    assert r["ocrCapped"] and r["ocrFields"] is None
