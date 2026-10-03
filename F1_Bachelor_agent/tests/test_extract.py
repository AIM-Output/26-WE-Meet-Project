"""추출 — 학사일정 표 행과 공지 본문 (형식은 2026-09 실측 그대로, 내용은 줄였다)."""
from datetime import date

from bachelor import config as C
from bachelor.classify import classify_type, semester_of
from bachelor.extract import from_post, from_table
from bachelor.sources.base import Post
from bachelor.sources.calendar_table import parse
from bachelor.sources.jnu_board import is_academic

TODAY = date(2026, 9, 28)
TABLE_CFG = C.BUILTIN_SOURCES[0]
NOTICE_CFG = C.BUILTIN_SOURCES[1]

PAGE = """<script>var scheduleYear = 2026;var scheduleData = [
{"start":"2013-01-07","end":"2013-01-11","title":"옛날 일정"},
{"start":"2026-08-07","end":"2026-08-14","title":"제2학기 수강신청(학년별): 8.7.(4학년), 8.10.(3학년), 8.11.(2학년), 8.12.(1학년), 8.13~14(전학년 공통)"},
{"start":"2026-09-01","end":"2026-09-01","title":"제2학기 개강"},
{"start":"2026-10-19","end":"2026-10-23","title":"제2학기 중간고사"},
{"start":"2026-12-10","end":"2026-12-10","title":"9. 24.(목) 추석연휴 보강"},
{"start":"2026-12-11","end":"2026-12-11","title":"9. 25.(금) 추석연휴 보강"},
{"start":"2026-12-15","end":"2027-01-06","title":"제2학기 교수수업개선서(CQI) 입력"},
{"start":"2027-01-04","end":"2027-01-04","title":"제2학기 성적제출 마감"},
{"start":"2027-02-27","end":"2027-02-27","title":"2027학년도 입학식"},
{"start":"2027-02-27","end":"2027-02-27","title":"2027학년도 입학식"}
];</script>"""


def by_title(cands):
    return {c.title: c for c in cands}


def test_table_rows():
    cands = from_table(parse(PAGE), TABLE_CFG, TODAY)
    t = by_title(cands)
    assert "옛날 일정" not in t                                          # 오래된 행은 가져오지 않는다
    assert sum(1 for c in cands if c.title == "2027학년도 입학식") == 1   # 같은 행 두 번 → 하나
    exam = t["제2학기 중간고사"]
    assert (exam.type, exam.start, exam.end, exam.confidence, exam.semester) == (
        "exam", date(2026, 10, 19), date(2026, 10, 23), 0.95, "2026-2")
    assert t["제2학기 개강"].type == "vacation" and t["제2학기 개강"].end is None
    assert t["제2학기 성적제출 마감"].audience.roles == ["faculty"]      # 교원 일정
    assert t["제2학기 성적제출 마감"].semester == "2026-2"               # 1월이지만 2학기
    assert t["2027학년도 입학식"].audience.grades == [1]


def test_table_grade_split():
    t = by_title(from_table(parse(PAGE), TABLE_CFG, TODAY))
    assert "제2학기 수강신청 (학년별)" in t
    third = t["제2학기 수강신청 (3학년)"]
    assert third.start == date(2026, 8, 10) and third.audience.grades == [3] and third.type == "course_reg"
    common = t["제2학기 수강신청 (전학년 공통)"]
    assert (common.start, common.end, common.audience.grades) == (date(2026, 8, 13), date(2026, 8, 14), None)


def test_table_makeup_rows_become_holiday_period():
    t = by_title(from_table(parse(PAGE), TABLE_CFG, TODAY))
    hol = t["추석연휴 (휴업)"]
    assert (hol.type, hol.start, hol.end) == ("holiday", date(2026, 9, 24), date(2026, 9, 25))
    assert t["9. 24.(목) 추석연휴 보강"].type == "etc"                   # 보강일은 휴일이 아니다


BODY = """공 고
우리 대학교에서는 2026학년도 제2학기 최종 등록기간을 다음과 같이 공고하오니 기한 내에 납부하시기 바랍니다.
1. 기 간 : 2026. 10. 1.(목) ~ 10. 2.(금) 16:00 [2일간]
2. 납입금 납부장소 : 광주, 농협, 국민, 신한은행 전국지점
◇ 휴학 신청 기간 ◾ 일반휴학 ( 미등록 ) : 2026. 10. 1.( 목 ) ~ 10. 2.( 금 ) ◾ 휴학 연장 : 2026. 10. 1.( 목 ) ~ 10. 2.( 금 ) * 2026. 8. 31. 까지 휴학만료인자가 휴학을 연장할 경우
일반복학 | 2026. 7. 1.( 수 ) ~ 8. 21.( 금 ) | . 일반휴학 : 2026. 8. 31. 까지 휴학 만료인 자
➣ 등록금 고지서 확인은 2026. 10. 1.(목)부터 가능
2026. 9. 14.
전 남 대 학 교 총 장"""


def test_notice_body():
    p = Post(post_id="70363", title="[학사안내]2026학년도 제2학기 최종 등록 공고", url="https://x/70363",
             posted_at="2026-09-14", writer="학사과", body=BODY)
    t = by_title(from_post(p, NOTICE_CFG, today=TODAY))
    reg = t["제2학기 최종 등록"]                                          # '기 간' 은 이름이 아니다 → 공지 제목
    assert (reg.start, reg.end, reg.end_time, reg.type) == (date(2026, 10, 1), date(2026, 10, 2), "16:00", "tuition")
    assert reg.confidence >= C.AUTO_THRESHOLD
    assert t["일반휴학 (미등록)"].type == "registration"
    assert t["휴학 연장"].audience.enrollment == ["휴학"]
    back = t["일반복학"]                                                  # 표 행: 셋째 칸의 날짜는 자격 조건
    assert (back.start, back.end) == (date(2026, 7, 1), date(2026, 8, 21))
    assert "등록금 고지서 확인은" not in t                               # 같은 날의 문장 조각은 버린다
    assert all(c.start != date(2026, 9, 14) for c in t.values())         # 서명 날짜
    assert all(c.start != date(2026, 8, 31) for c in t.values())         # 조건 속 날짜


def test_notice_image_only_goes_to_review():
    p = Post(post_id="1", title="[학사안내]2026학년도 2학기 수강취소 안내", url="u", posted_at="2026-09-11",
             body="", image_only=True)
    [c] = from_post(p, NOTICE_CFG, today=TODAY)
    assert c.start is None and "needs_ocr" in c.flags and c.confidence < C.WEAK_THRESHOLD


def test_notice_attachment_text():
    p = Post(post_id="2", title="[학사안내]2026학년도 2학기 수강취소 안내", url="u", posted_at="2026-09-11",
             body="", image_only=True, writer="학사과")
    cands = from_post(p, NOTICE_CFG, extra=[("attachment", "❍ 신청: 9. 22.(화) 09:00 ~ 9. 23.(수) 17:00")], today=TODAY)
    [c] = cands
    assert (c.title, c.start, c.start_time, c.end_time) == ("2학기 수강취소", date(2026, 9, 22), "09:00", "17:00")
    assert "attachment" in c.flags


def test_board_filter():
    assert is_academic("[학사안내] 2026학년도 2학기 수강취소 안내", "학사과")
    assert is_academic("[학사안내] 재학생 분할납부 2회차 고지서 출력", "재무과")
    assert not is_academic("[학사안내] 연구교수 초빙 공고", "학사과")
    assert not is_academic("[학사안내] PSAT 스타트 특강 (9.4.~ 9.6.)", "진로취업지원실")


def test_classify():
    assert classify_type("창업휴학 (등록)") == "registration"
    assert classify_type("분할납부 2회차 등록") == "tuition"
    assert classify_type("10. 5.(월) 개천절 대체휴일 보강") == "etc"
    assert semester_of("제1학기 수업계획서 입력", date(2027, 1, 6)) == "2027-1"
    assert semester_of("동계 계절학기", date(2026, 12, 28)) == "2026-2"
    assert semester_of("수강희망과목 예약", date(2026, 2, 2)) == "2026-1"
