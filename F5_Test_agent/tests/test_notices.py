"""공지에서 시험 찾기 (F5-R01·R02) — **2026-09-30 실측 공지**와 함정들.

아래 세 개는 실제로 수집된 공지의 본문이다(F6_Eclass_agent/data). 규칙을 고칠 때 이 세 개가 계속
맞는지 먼저 본다 — 시험 날짜를 틀리는 것이 이 기능의 가장 큰 실패다.
"""
from datetime import date

import pytest

from exams import notices

from conftest import make_eclass  # noqa: E402

# ── 실측 ① 소프트웨어공학론 중간고사 (2026-09-29 작성) ──
#    날짜가 시험말이 없는 '1. 일정:' 줄에 있고, 범위 줄에도 날짜가 있다.
SE_MIDTERM = """1. 일정: 10월 22일 목요일 오후 3시부터 4시까지
2. 위치: 박물관 시청각실 (위치는 개인적으로 미리 파악해두세요!)
3. 준비물: A4용지 한페이지 컨닝페이퍼 (양면 가능, 출력 가능), 그 외 전자제품 등은 모두 불가
4. 시험 범위: 10월 15일 까지 강의한 내용 전반
5. 문제 유형: 객관식, 주관식, 서술형 등 다양함"""

# ── 실측 ② 산학협력프로젝트 발표 일정 (2026-09-22 작성) ──
#    '발표 일정이 없습니다' 라는 부정문이 먼저 나온다.
CAPSTONE_PRESENT = """[산학협력프로젝트]
9월 23일, 9월 30일은 팀별 활동을 진행하시면 되고 따로 발표 일정이 없습니다.
다음 발표는
10월 7일 예정이며 기획서 발표이후 진행된 사항에 대해서 발표
하시면 되고
발표 주제가 바뀐 팀의 경우 내용에 대해서도 전반적으로 소개해주시면 됩니다.
발표는 5분 내외로 준비하시면 됩니다.
추석 잘 보내시길 바랍니다."""

# ── 실측 ③ 산학협력프로젝트 향후 일정 (2026-09-09 작성) ──
#    한 글에 발표가 둘, 제출 마감('9/15일까지')도 섞여 있다.
CAPSTONE_SCHEDULE = """안녕하세요.
캡스톤디자인 TA 나유경입니다.
사업단 연계 여부 제출 및 향후 일정 안내드립니다.
1. 사업단 연계 여부 제출 안내 (팀장 필수)
각
팀장
님들께서는 아래 예시 양식에 맞춰
9/15일까지
[팀명/사업단 연계 여부]를 조교에게 쪽지로 제출해 주시기 바랍니다.
2. 발표 진행 시간 안내
- 기획서 발표: 4분 이내
- 중간진도 점검 발표: 5분 이내
- 중간/기말 발표: 8분 이내
3. 주차별 수업 일정 안내 (10월 첫째주까지)
- 09월 16일: 기획서 발표 (발표 4분 이내)
- 09월 23일: 팀별 활동 (수업 없음)
- 09월 30일: 팀별 활동 (수업 없음)
- 10월 07일: 중간진도 점검 발표 (발표 5분 이내)"""


def found(title, body, posted="2026-09-29"):
    return notices.exams_in(title, body, date.fromisoformat(posted))


# ---------------------------------------------------------------- 실측

def test_real_midterm_notice():
    exams, hints = found("중간고사 장소 및 준비물 공지", SE_MIDTERM)
    assert len(exams) == 1
    e = exams[0]
    assert e["type"] == "midterm"
    assert e["date"] == "2026-10-22"                 # 실제로 목요일이다 (공지의 '목요일'과 맞는다)
    assert date.fromisoformat(e["date"]).weekday() == 3
    assert (e["time"], e["endTime"]) == ("15:00", "16:00")    # '오후 3시부터 4시까지'
    assert e["place"] == "박물관 시청각실"            # 괄호 안 잔소리는 떼어 낸다
    assert e["scopeNote"] == "10월 15일 까지 강의한 내용 전반"
    assert e["confidence"] >= 0.9 and e["status"] == "confirmed"
    assert "10월 22일" in e["quote"]
    assert not hints


def test_scope_line_date_is_not_the_exam_date():
    """'시험 범위: 10월 15일 까지' 의 날짜를 시험일로 쓰면 안 된다."""
    exams, _ = found("중간고사 공지", "1. 일정: 10월 22일 시험\n4. 시험 범위: 10월 15일 까지 강의한 내용")
    assert [e["date"] for e in exams] == ["2026-10-22"]


def test_real_presentation_notice_skips_negation():
    exams, _ = found("[산학협력프로젝트] 발표 일정 안내", CAPSTONE_PRESENT, posted="2026-09-22")
    assert [e["date"] for e in exams] == ["2026-10-07"]        # 9/23·9/30 은 '발표 일정이 없습니다'
    assert exams[0]["type"] == "presentation"
    assert exams[0]["title"] == "기획서 발표"


def test_real_schedule_notice_finds_two_presentations():
    exams, _ = found("사업단 연계 여부 제출 및 향후 일정 안내", CAPSTONE_SCHEDULE, posted="2026-09-09")
    assert [e["date"] for e in exams] == ["2026-09-16", "2026-10-07"]
    assert {e["type"] for e in exams} == {"presentation"}
    assert [e["title"] for e in exams] == ["기획서 발표", "중간진도 점검 발표"]
    # 제목에 시험말이 없어 유형을 본문에서 알았다 → 신뢰도를 깎고 '확인 필요'로 보낸다 (F5-R02)
    assert all(e["status"] == "review" for e in exams)


def test_submission_deadline_is_not_an_exam():
    """'9/15일까지 제출' 은 과제 마감(F6)이다 — 시험으로 만들지 않는다."""
    exams, _ = found("사업단 연계 여부 제출 및 향후 일정 안내", CAPSTONE_SCHEDULE, posted="2026-09-09")
    assert "2026-09-15" not in [e["date"] for e in exams]


# ---------------------------------------------------------------- 유형 · 시각 · 범위

@pytest.mark.parametrize("text,kind", [
    ("중간고사 안내", "midterm"),
    ("중간시험 일정", "midterm"),
    ("기말고사 공지", "final"),
    ("2주차 퀴즈 안내", "quiz"),
    ("쪽지시험 봅니다", "quiz"),
    ("발표 순서", "presentation"),
    ("시험 안내", "etc"),
    ("강의실 변경 안내", None),
])
def test_classify(text, kind):
    assert notices.classify(text) == kind


@pytest.mark.parametrize("line,expected", [
    ("일시: 오후 3시부터 4시까지", ("15:00", "16:00")),
    ("일시: 오전 10시 30분", ("10:30", "")),
    ("일시: 14:00 ~ 15:50", ("14:00", "15:50")),
    ("일시: 3시", ("15:00", "")),                    # 대학 공지의 '3시'는 오후다
    ("일시: 9시", ("09:00", "")),                    # 8시 이상은 그대로 (아침 수업)
    ("일시: 오후 12시", ("12:00", "")),
    ("일시: 오전 12시", ("00:00", "")),
    ("일시: 10월 22일 목요일", ("", "")),
])
def test_times_in(line, expected):
    assert notices.times_in(line) == expected


@pytest.mark.parametrize("line,expected", [
    ("2. 위치: 박물관 시청각실 (미리 파악해두세요)", "박물관 시청각실"),
    ("장소: 공7-223", "공7-223"),
    ("장소는 인문대 2호관 101호입니다", "인문대 2호관 101호"),
    ("중간고사 장소 및 준비물 공지", ""),             # 이름표 뒤에 ':' 나 '은/는' 이 없으면 값이 아니다
    ("시험은 공7-223 에서 봅니다", "공7-223"),
])
def test_place_in(line, expected):
    assert notices.place_in(line) == expected


def test_scope_weeks_expand():
    exams, _ = found("중간고사 안내", "일시: 10월 22일\n범위: 3~7주차 강의자료 전체")
    assert exams[0]["scopeWeeks"] == [3, 4, 5, 6, 7]
    assert "3~7주차" in exams[0]["scopeNote"]


def test_no_time_is_saved_without_time():
    """날짜만 있고 시각이 없으면 시각 없이 저장한다 (F5 8절)."""
    exams, _ = found("기말고사 안내", "기말고사는 12월 18일에 봅니다")
    assert exams[0]["date"] == "2026-12-18"
    assert exams[0]["time"] == ""
    assert exams[0]["confidence"] < 1.0              # 시각이 없으면 신뢰도를 깎는다


def test_relative_date_lowers_confidence():
    exams, _ = found("퀴즈 공지", "다음 주 화요일 퀴즈 봅니다", posted="2026-10-13")
    assert exams[0]["date"] == "2026-10-20"          # 작성일(화)의 다음 주 화요일
    assert exams[0]["status"] == "review"


def test_two_dates_for_midterm_picks_one_and_warns():
    """중간고사는 과목마다 하나다 — 후보가 여럿이면 하나만 남기고 확인을 받는다."""
    exams, hints = found("중간고사 공지", "중간고사 10월 22일\n예비일 중간고사 10월 29일")
    assert len(exams) == 1
    assert exams[0]["status"] == "review"
    assert hints and "후보가 여럿" in hints[0]


def test_exam_word_without_date_becomes_hint():
    """시험을 말하는데 날짜가 없으면 조용히 버리지 않고 '확인 필요'로 남긴다."""
    exams, hints = found("중간고사 준비물 안내", "컨닝페이퍼 1장만 가져오세요.")
    assert exams == []
    assert hints and "날짜를 찾지 못했습니다" in hints[0]


def test_far_dates_are_dropped():
    exams, _ = found("중간고사 공지", "작년 중간고사는 3월 2일이었습니다\n올해는 10월 22일입니다")
    assert [e["date"] for e in exams] == ["2026-10-22"]


# ---------------------------------------------------------------- 전체 읽기

def test_load_reads_manifest(db):
    make_eclass([
        ("74261", "2026-09-29 17:12", "중간고사 장소 및 준비물 공지", SE_MIDTERM),
        ("74245", "2026-09-6 21:30", "강의실 변경 안내", "공7-123 으로 바뀌었습니다"),
    ])
    out = notices.load(today=date(2026, 9, 30))
    assert out["available"] and out["posts"] == 1    # 시험말이 없는 글은 읽지도 않는다
    assert "74245" not in out["byCourse"]
    e = out["byCourse"]["74261"]["exams"][0]
    assert e["date"] == "2026-10-22" and e["courseId"] == "74261"
    assert e["evidence"][0]["url"].startswith("https://sel.jnu.ac.kr/")
    assert e["postedAt"] == "2026-09-29"


def test_load_handles_single_digit_dates(db):
    """manifest 의 작성일은 '2026-09-6' 처럼 **0 이 빠진 날짜**로 온다."""
    make_eclass([("74261", "2026-09-6 21:30", "퀴즈 공지", "9월 9일 퀴즈 봅니다")])
    out = notices.load(today=date(2026, 9, 30))
    assert out["byCourse"]["74261"]["exams"][0]["postedAt"] == "2026-09-06"


def test_load_without_manifest(db):
    from exams import config as C
    C.ECLASS_MANIFEST.unlink()
    notices._cache.update(key=None, value=None)
    out = notices.load(today=date(2026, 9, 30))
    assert out["available"] is False and out["byCourse"] == {}
