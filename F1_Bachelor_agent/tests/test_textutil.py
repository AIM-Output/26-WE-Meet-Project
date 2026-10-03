"""날짜 찾기 — 2026-09 전남대 공지에서 실제로 본 표기들."""
from datetime import date

from bachelor.textutil import clean_post_title, find_spans, is_grounded, normalize_title, parse_board_url

CTX = date(2026, 9, 14)


def one(text):
    spans = find_spans(text, CTX)
    assert spans, text
    return spans[0]


def test_period_with_end_time():
    s = one("1. 기 간 : 2026. 10. 1.(목) ~ 10. 2.(금) 16:00 [2일간]")
    assert (s.start, s.start_time, s.end, s.end_time) == (date(2026, 10, 1), None, date(2026, 10, 2), "16:00")
    assert s.year_explicit


def test_period_with_times_and_table_cell():
    s = one("분할납부 2회차 등록기간 | 2026. 9. 21.(화) 9:00 ~ 9. 23.(수) 16:00")
    assert (s.start, s.start_time, s.end, s.end_time) == (date(2026, 9, 21), "09:00", date(2026, 9, 23), "16:00")


def test_no_space_before_time_and_two_digit_year():
    assert one("폐강과목수강정정 기간: 2026. 9. 15.(화) 10:00 ~ 9. 16.(수)18:00").end_time == "18:00"
    s = one("- 기간: '26. 9. 2.(수) 09:00 ~ 9. 9.(수) 18:00")
    assert s.start == date(2026, 9, 2) and s.year_explicit


def test_spaced_weekday_and_classes_fraction_is_not_a_date():
    s = one("일반휴학 ( 등록 ) : 2026. 8. 18.( 화 ) ~ 수업일수 1/2 선인 10. 28.( 수 ) 까지 신청가능")
    assert (s.start, s.end) == (date(2026, 8, 18), date(2026, 10, 28))


def test_day_without_trailing_dot():
    assert one("교과구분 정정 신청 기간: 2026. 9. 21.(월) ~ 9.30(수)").end == date(2026, 9, 30)


def test_grade_split_and_day_only_continuation():
    spans = find_spans("8.7.(4학년), 8.10.(3학년), 8.11.(2학년), 8.12.(1학년), 8.13~14(전학년 공통)", date(2026, 8, 7))
    assert [s.start.day for s in spans] == [7, 10, 11, 12, 13]
    assert spans[-1].end == date(2026, 8, 14)


def test_time_only_continuation():
    s = one("2026. 9. 1. 10:00 ~ 17:00 설명회")
    assert (s.start, s.start_time, s.end, s.end_time) == (date(2026, 9, 1), "10:00", date(2026, 9, 1), "17:00")


def test_year_rollover_in_korean_format():
    s = one("휴·복학 신청은 12월 28일부터 1월 8일까지 받습니다")
    assert (s.start, s.end) == (date(2026, 12, 28), date(2027, 1, 8))


def test_deadline_marker():
    s = one("행정고시반 신규 실원 모집(~10.14.)")
    assert s.deadline and s.start == date(2026, 10, 14)


def test_not_dates():
    assert find_spans("성적 3.5/4.5 이상, 문의 062-530-1084, 수업일수 1/4선, 2일간", CTX) == []


def test_titles():
    assert clean_post_title("[학사안내]2026학년도 제2학기 최종 등록 공고") == "제2학기 최종 등록"
    assert clean_post_title("[학사안내]2026학년도 동계 계절학기 개설교과목 수요조사 실시 안내") == "동계 계절학기 개설교과목 수요조사"
    assert normalize_title("2026학년도 제2학기 최종 등록 공고") == normalize_title("제2학기 최종 등록")
    assert normalize_title("제74회 후기('26년 8월) 학위수여식") == normalize_title("제74회 후기(2026년 8월) 학위수여식")
    assert normalize_title("수강신청 (4학년)") != normalize_title("수강신청 (3학년)")


def test_grounding():
    src = "1. 기 간 : 2026. 10. 1.(목) ~ 10. 2.(금) 16:00 [2일간]"
    assert is_grounded("기간: 2026.10.1.(목) ~ 10.2.(금) 16:00", src)
    assert not is_grounded("2026. 10. 5. ~ 10. 9.", src)


def test_board_url():
    assert parse_board_url("https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do?bbsOpenWrdSeq=236") == {
        "base": "https://aisw.jnu.ac.kr", "site": "aisw", "board": "64", "category": "236",
        "categoryParam": "bbsOpenWrdSeq"}
    assert parse_board_url("https://cvg.jnu.ac.kr/bbs/cvg/1234/artclList.do?bbsClSeq=7&page=2")["categoryParam"] == "bbsClSeq"
    assert parse_board_url("https://cvg.jnu.ac.kr/cvg/3303/subview.do") is None
    assert parse_board_url("https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx") is None
