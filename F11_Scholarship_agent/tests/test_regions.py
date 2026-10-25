"""지역 장학 판정 — 전남대 장학안내 게시판 실제 제목(2026-10-09)."""
import pytest

from scholarship import regions as R


@pytest.mark.parametrize("title, provinces, level", [
    ("[장학안내] [(재)포항시장학회] 2026년도 대학교 장학생 선발 안내", ["경북"], "city"),
    ("[장학안내] [(제)경주시장학회]2026년 장학생 선발 안내", ["경북"], "city"),
    ("[장학안내] [통영시] 2026년 상반기분 통영시 대학생 학자금 이자 지원", ["경남"], "city"),
    ("[장학안내] [(재) 김해시미래인재장학재단] 2026년 장학생 선발 안내", ["경남"], "city"),
    ("[장학안내] [재단법인 논산시장학회] 2026년도 하반기 재단법인 논산시장학회", ["충남"], "city"),
    ("[장학안내] [정읍시민장학재단] 우수인재장학금 장학생 선발 안내", ["전북"], "city"),
    ("[장학안내] [(재)춘천인재육성장학재단] 2026년도 하반기 봄내장학생 선발", ["강원"], "city"),
    ("[장학안내] [(재)광산장학회] 2026년도 장학생 선발공고", ["광주"], "city"),
    ("[장학안내] [전남인재평생교육진흥원] 2026년 하반기 전남인재육성 장학생", ["전남"], "province"),
    ("[장학안내] [(재)대전청년내일재단] 2026년 성취(대) 장학생 선발계획", ["대전"], "province"),
    ("[장학안내] [재단법인 서울미래인재재단] 2026년 하반기 서울인재대학장학", ["서울"], "province"),
    ("[장학안내] [울산광역시] 대학(원)생 학자금 대출 이자지원사업 안내", ["울산"], "province"),
    ("[장학안내] [대구광역시 달서인재육성장학재단] 2026년도 하반기 장학생", ["대구"], "province"),
    ("[장학안내] [전남광주통합특별시] 광주권 대학생 학자금대출 이자지원 안내", ["광주", "전남"], "province"),
])
def test_regional_foundations(title, provinces, level):
    r = R.detect(title)
    assert r is not None and r["provinces"] == provinces and r["level"] == level


@pytest.mark.parametrize("title", [
    "[장학안내] [아산사회복지재단] 2027년 북한이탈청소년장학생 선발 안내",     # 아산시가 아니다 (현대 아산재단)
    "[장학안내] [한국장학재단] 희망사다리 장학생 대상 대전 일자리 박람회 홍보",  # 대전은 조건이 아니라 행사 장소
    "[장학안내] 2026학년도 2학기 취업연계 중점대학 유형(광주은행) 국가근로장학생 모집 안내",
    "[장학안내] 2026학년도 여수캠퍼스 청경나래 장학금(구 학생성공지원금)",       # 캠퍼스 — 지역 조건이 아니다(match 의 캠퍼스 규칙)
    "[장학안내] [인천광역시의료원] 2026년 인천형 공공간호사 장학생 모집 안내",   # 의료원 — 지역 재단이 아니다
    "전남대학교 2026학년도 장학생 선발",
])
def test_not_regional(title):
    assert R.detect(title) is None


def test_body_residency_line_and_school_mention():
    r = R.detect("장학생 선발", "1. 지원자격: 본인 또는 부모가 포항시에 주소를 둔 자\n접수처 주소: 광주광역시 북구 용봉로 77")
    assert r["provinces"] == ["경북"] and r["bodyLines"] and not r["mentionsSchool"]
    r = R.detect("장학생 선발", "논산시에 주소를 두거나 논산시 소재 고등학교를 졸업한 자")
    assert r["mentionsSchool"]


def test_province_of():
    assert R.province_of("광주") == ("광주",)
    assert R.province_of("전라남도") == ("전남",)
    assert R.province_of("모름") == ()
