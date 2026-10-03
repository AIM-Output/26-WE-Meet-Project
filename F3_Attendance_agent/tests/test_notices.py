"""e클래스 공지에서 휴강 찾기 (2026-09-29 수정 ③). 앞의 4건은 2026-09-28 실제 과목 공지의 제목·문장 그대로다."""
from datetime import date

import pytest

from attendance import notices as N
from conftest import make_eclass


def d(s):
    return date.fromisoformat(s)


@pytest.mark.parametrize("title, body, posted, want", [
    # 실제 공지 (소프트웨어공학론 · 오픈소스소프트웨어 · 운영체제 · 컴퓨터네트워크)
    ("9월 17일 목요일 휴강", "해당일 수업은 휴강할 예정입니다.\n보강 일정은 차후 말씀드리겠습니다.", "2026-09-14", ["2026-09-17"]),
    ("9월 17일 휴강 공지", "금일 수업은 휴강하겠습니다.", "2026-09-17", ["2026-09-17"]),
    ("오늘 수업 휴강(9/16)", "오늘 수업은 부득이 휴강 합니다.", "2026-09-16", ["2026-09-16"]),
    # 상대 표현 · 기간 · 보강 구절 · 해 넘김
    ("휴강 안내", "다음 주 화요일은 휴강합니다. 보강은 10월 20일(화)입니다.", "2026-10-08", ["2026-10-13"]),
    ("공지", "9월 16일~18일 휴강, 보강은 9월 24일", "2026-09-10", ["2026-09-16", "2026-09-17", "2026-09-18"]),
    ("이번 주 목요일 휴강", "", "2026-10-12", ["2026-10-15"]),
    ("내일 휴강", "", "2026-10-12", ["2026-10-13"]),
    ("1월 5일 휴강", "", "2026-12-28", ["2027-01-05"]),
    ("휴강 공지", "10/7, 10/9 휴강합니다", "2026-10-01", ["2026-10-07", "2026-10-09"]),
])
def test_cancel_dates(title, body, posted, want):
    got, mentioned = N.cancel_dates(title, body, d(posted))
    assert mentioned and [x.isoformat() for x in got] == want


def test_whole_week():
    got, _ = N.cancel_dates("이번 주 수업 휴강", "", d("2026-10-14"))
    assert [x.isoformat() for x in got] == [f"2026-10-{n}" for n in range(12, 19)]


@pytest.mark.parametrize("title, body", [
    ("수업 안내", "이번 주는 휴강 없이 정상 수업합니다"),
    ("휴강 취소", "10월 7일 휴강은 취소되었습니다. 휴강하지 않습니다."),
    ("강의실 변경 안내", "9월 3일부터 공7-223 에서 수업합니다"),
])
def test_not_a_cancel(title, body):
    got, _ = N.cancel_dates(title, body, d("2026-10-01"))
    assert got == []


def test_mention_without_date_is_hint():
    got, mentioned = N.cancel_dates("휴강", "사정상 휴강합니다. 3.5학점 과목입니다", d("2026-09-10"))
    assert got == [] and mentioned


def test_load_from_eclass_manifest_and_cache():
    make_eclass([
        ("74245", "2026-09-16 07:44", "오늘 수업 휴강(9/16)", "오늘 수업은 부득이 휴강 합니다."),
        ("74261", "2026-09-14 11:02", "9월 17일 목요일 휴강", "해당일 수업은 휴강할 예정입니다."),
        ("74261", "2026-09-20 10:00", "공지", "사정상 휴강합니다"),
        ("74245", "2026-09-03 09:00", "강의실 변경 안내", "공7-223"),
    ])
    n = N.load()
    assert n["available"] and n["stamp"]
    assert n["byCourse"]["74245"]["cancels"]["2026-09-16"]["reason"] == "오늘 수업 휴강(9/16)"
    assert list(n["byCourse"]["74261"]["cancels"]) == ["2026-09-17"]
    assert [h["reason"] for h in n["byCourse"]["74261"]["hints"]] == ["공지"]
    assert N.load() is n                                     # manifest 가 그대로면 다시 읽지 않는다


def test_missing_manifest():
    from attendance import config as C
    C.ECLASS_MANIFEST.unlink(missing_ok=True)
    N._cache.update(key=None, value=None)
    assert N.load() == {"available": False, "stamp": None, "byCourse": {}}
