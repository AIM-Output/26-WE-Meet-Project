"""원천(F11 목록 + 덮어쓰기)과 정보 추출 — 분류 · 주관 · 대상·장소·기간·혜택 · 결과·마감 표시 · 장학 거르기."""
from activity import collect, extract, registry

PROFILE = {"college": "AI융합대학", "department": "인공지능학부", "grade": 3}


def test_sources_are_f11_minus_scholarship_only():
    keys = [s["key"] for s in registry.sources()]
    from scholarship import registry as f11
    f11_keys = [s["key"] for s in f11.sources()]
    assert "jnu_scholarship" not in keys and "jnu_catalog" not in keys            # 장학만 올라오는 원천
    assert set(keys) == set(f11_keys) - {"jnu_scholarship", "jnu_catalog"}       # 나머지는 F11 과 같다
    assert registry.get("my_dept")["name"] == "내 학부(과) 공지"                    # 대외활동 쪽 이름
    assert registry.get("alumni")["require"][0] == "모집"                           # F11 의 '장학생' 조건을 바꿈


def test_profile_decides_sources_like_f11():
    rows = {r["key"]: r for r in registry.resolve(PROFILE)}
    assert rows["aicoss"]["enabled"] and rows["aicoss"]["relevance"]["level"] == "related"
    assert not rows["battery"]["enabled"] and rows["battery"]["relevance"]["level"] == "open"   # 전공 무관 참여 — 켤 수 있음
    assert rows["my_dept"]["relevance"]["level"] == "mine"
    rows = {r["key"]: r for r in registry.resolve(PROFILE, {"battery": True, "grow": False})}
    assert rows["battery"]["enabled"] and not rows["grow"]["enabled"] and rows["grow"]["userSet"]
    assert "capd" not in [r["key"] for r in registry.collectable(list(rows.values()))]          # relay 는 학교 공지로


def test_unit_for_writer():
    assert registry.unit_for("실험실특화형창업선도대학사업단", "[모집공고] 창업 아이템 경진대회")["key"] == "startuphub"
    assert registry.unit_for("학생과", "[대학생활] 상담 신청") is None


def test_skip_reasons():
    cfg = {"key": "jnu_notice"}
    assert collect.skip_reason("[장학안내] [우양재단] 2026 동행 장학생 모집", None, cfg) == "장학"
    assert collect.skip_reason("2026년 하반기 근로장학생 모집", None, cfg) == "장학"                       # F11 어휘 그대로
    assert collect.skip_reason("[채용공고] 2026 국제협력과 기간제 계약직 직원 채용", None, cfg) == "말머리 채용공고"
    assert collect.skip_reason("[행정공고] CCTV 설치 행정예고", None, cfg).startswith("말머리")
    assert collect.skip_reason("[취업정보] [광주상공회의소] 일반사무직 직원 채용", None, cfg) is None       # 기업 채용은 남긴다
    assert collect.skip_reason("교원 초빙 공고", None, cfg) == "거르는 어휘"
    alumni = registry.get("alumni")
    assert collect.skip_reason("동문 부고 알림", None, alumni) == "거르는 어휘"
    assert collect.skip_reason("동창회 소식지 발간", None, alumni) == "원천 조건"
    assert collect.skip_reason("동문 멘토링 참가자 모집", None, alumni) is None


def test_categories():
    cases = {
        "[모집공고] 제24회 2026 전남대학교 창업 아이템 경진대회": "contest",
        "[공모전] 『2026 English Essay Contest』개최 안내": "contest",
        "[취업정보] [KIA]AutoLand광주 의전담당자 채용": "career",
        "인공지능혁신융합대학사업단 실험실습 기자재 대여 안내(2026년 2학기)": "rental",
        "2026 AICOSS-UNLV(미국) 글로벌 단기 파견 프로그램 참가자 선발": "global",
        "[대학생활] <징검다리 상담교수> 상담 신청 안내": "program",
        "[학사안내] 2026학년도 제2학기 휴학·복학 신청 안내": "academic",        # 분류는 하되 대외활동에서는 뺀다 (아래 테스트)
        "2026학년 2학기 기업 연계형 캡스톤디자인 과제 지원 안내": "program",
        "[학사] 2026년 공동운영마이크로디그리 신청 안내(상시가능)": "program",     # AICOSS '학사' 말머리여도 사업단 프로그램
        "KOICA 프로젝트 봉사단 (9기) 파라과이 모집": "volunteer",
        "2026 대학생 서포터즈 3기 모집": "club",
        "[취업정보] [(주)오뚜기] 2026년 하반기 대졸신입사원 및 외국인유학생 채용": "career",
    }
    for title, want in cases.items():
        assert extract.extract(title, "")["category"] == want, title


def test_title_host_and_board_category():
    t = "[취업정보] [KIA]AutoLand광주 의전담당자 채용(~10.13.(화))"
    assert extract.board_category(t) == "취업정보"
    assert extract.clean_title(t).startswith("[KIA]AutoLand")
    assert extract.host_from_title(t) == "KIA"
    assert extract.host_from_title("[공모전] [제주대학교] 제46회 백록학술상 공모전") == "제주대학교"
    assert extract.extract("2026 해커톤 참가자 모집", "", unit={"org": "AICOSS"})["host"] == "AICOSS"


BODY = """□ 모집대상 : 전남대학교 재학생 (전공 무관)
□ 장소 : 공과대학 7호관 세미나실
□ 교육기간 : 2026. 11. 2.(월) ~ 11. 6.(금)
□ 신청기간 : 2026. 10. 1.(수) ~ 2026. 10. 20.(월) 18:00
□ 혜택 : 수료증 발급 및 비교과 마일리지 20점
□ 참가비 : 무료
□ 모집인원 : 30명 내외
□ 제출서류 : 참가신청서 1부, 재학증명서 1부
□ 신청방법 : 구글폼 제출 (https://forms.example.invalid/abc)
"""


def test_fields():
    info = extract.extract("[모집공고] 2026 AI 부트캠프 교육생 모집", BODY, posted_at="2026-10-01")
    assert info["target"].startswith("전남대학교 재학생")
    assert info["place"] == "공과대학 7호관 세미나실"
    assert info["eventPeriod"].startswith("2026. 11. 2.")
    assert info["period"]["end"] == "2026-10-20T18:00"
    assert info["benefit"].startswith("수료증")
    assert info["fee"] == "무료"
    assert info["capacity"] == "30명"
    assert "재학증명서 1부" in info["documents"]
    assert info["applyUrl"] == "https://forms.example.invalid/abc"
    assert info["participation"] and not info["result"]
    assert info["evidence"]["target"].startswith("□ 모집대상")


def test_result_and_closed_marks():
    assert extract.extract("2026 AIM챌린지 본선 진출팀 발표", "")["result"]
    assert extract.extract("2026년 2학기 시스템 관리 TA 선발 결과 안내", "")["result"]
    assert not extract.extract("2026 AICOSS-UTAS 글로벌 학생프로그램 학생 선발 안내", "")["result"]
    assert extract.extract("(마감)글로벌 AI 역량강화 교육과정 교육생 모집", "")["closedMark"]
    assert extract.extract("대학원생 연구 참여 프로그램", "")["gradOnly"]


def test_academic_admin_out_credit_exchange_in():
    """2026-10-25 사용자 결정 — 학사과·재무과 등의 정규학기 행정 안내(계절학기 포함)만 뺀다. 학점교류는 대외활동으로 남긴다."""
    cfg = {"key": "jnu_notice"}
    A = "학사 행정 안내"
    # 뺀다 — 학사 행정 부서의 글 · 정규학기 행정 제목
    assert collect.skip_reason("[학사안내] 2026학년도 2학기 교과구분 정정 실시 안내", None, cfg, "학사과") == A
    assert collect.skip_reason("[학사안내] 2026학년도 동계 계절학기 수강신청 안내", None, cfg, "학사과") == A
    assert collect.skip_reason("[학사안내] 2026학년도 2학기 분할납부 신청 안내", None, cfg, "재무과") == A
    assert collect.skip_reason("[학사안내] 최근 5년 이내 제적생 중 등록금 반환 대상자 안내", None, cfg, "재무과") == "장학"   # 등록금 = F11 어휘
    assert collect.skip_reason("[학사] 2026학년도 2학기 2차 폐강 교과목 및 수강정정 안내", None, cfg, "교육혁신본부") == A
    assert collect.skip_reason("2026학년도 제2학기 휴학·복학 신청 안내", None, cfg) == A
    # 남긴다 — 학점교류(학사과 글이어도) · 학과가 '[학사안내]'로 올린 워크숍 · 계절학기에 하는 해외 인턴 · 사업단 프로그램
    assert collect.skip_reason("[학사안내] 2026학년도 동계 계절학기 타 대학교(서울대) 교류수학 추천 안내", None, cfg, "학사과") is None
    assert collect.skip_reason("2026학년도 2학기 성균관대학교 학점교류 신청 안내(8/3(월) 9:00까지)", "학사", cfg, "AICOSS") is None
    assert collect.skip_reason("2026학년도 2학기 전남대학교 교류학생 학번 안내", "학사", cfg) is None
    assert collect.skip_reason("[학사안내] 2026 프랑코포니 문화예술 콘텐츠 워크숍 안내", None, cfg, "불어불문학과") is None
    assert collect.skip_reason("[학생모집] 2026년 동계 계절학기 해외(일본) 인턴십(4주) 참여학생 추가모집", None, cfg) is None
    assert collect.skip_reason("[학사] 2026년 공동운영마이크로디그리 신청 안내(상시가능)", "학사", cfg) is None
    assert collect.skip_reason("2026학년 2학기 기업 연계형 캡스톤디자인 과제 지원 안내", None, cfg) is None
    assert extract.extract("2026학년도 2학기 성균관대학교 학점교류 신청 안내", "", writer="학사과")["category"] == "program"
    assert extract.extract("[학사안내] 2026학년도 동계 계절학기 타 대학교(부산대) 교류수학 추천", "", writer="학사과")["category"] == "program"
    # 본문의 '학점' 한 마디로는 학사로 짐작하지 않는다
    info = extract.extract("「AICOSS Career Compass 2026」 진로실태 설문조사 참여 안내", "참여 시 비교과 학점 인정\n설문 기간: 10. 1. ~ 10. 20.")
    assert info["category"] != "academic"
    from activity import interests as I
    assert "academic" not in I.category_labels() and I.dropped_categories() == {"academic"}


def test_new_sources_overlay():
    assert registry.get("sojoong")["name"].startswith("SW중심대학사업단") and registry.get("aisw_sw") is None
    assert registry.get("aicoss")["cate"] == "전남대학교"
    sanhak = registry.get("sanhak")
    assert collect.skip_reason("2026년 제2회 산학연협력단지조성지원사업단 직원 채용 합격자 공고", None, sanhak) == "거르는 어휘"
    assert collect.skip_reason("연구실 안전교육 이수 현황", None, sanhak) == "원천 조건"
    assert collect.skip_reason("2026학년도 G-RISE 공유대학 AI 3合 특강 운영 안내", None, sanhak) is None
    assert collect.skip_reason("학생인건비 교육과정 참여 안내", None, sanhak) == "거르는 어휘"
    assert collect.skip_reason("[3차 멘토링] 캡스톤디자인 WE-Meet 프로젝트 멘토링 보고서", None, {"key": "nccoss_apply"}) == "거르는 어휘"
    keys = {r["key"] for r in registry.resolve({"college": "AI융합대학", "department": "인공지능학부"}) if r["enabled"]}
    assert {"jnu_events", "lec", "counsel", "startup_center", "nccoss_apply", "sojoong", "futurecar", "sanhak"} <= keys
