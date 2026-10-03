"""강의시간 파서 · 시간표 조회 응답 파싱 · 과목 매칭 (F3 2절). 네트워크 없음."""
import pytest

from attendance import sessions, timetable as T
from conftest import FIXTURES


def test_parse_two_days():
    ms = T.parse_times("화5목5", ["공7-223", "공7-223"])
    assert ms == [{"weekday": 1, "periods": [5], "room": "공7-223"}, {"weekday": 3, "periods": [5], "room": "공7-223"}]
    assert T.meetings_text(ms) == "화 5교시 · 목 5교시"


def test_parse_consecutive_periods_and_rooms():
    ms = T.parse_times("월5월6수5", ["공2-100", "공2-100", "공2-101"])
    assert [(m["weekday"], m["periods"], m["room"]) for m in ms] == [(0, [5, 6], "공2-100"), (2, [5], "공2-101")]


def test_parse_unsorted_tokens_are_sorted():
    # 2026-09-28 실측: 산학협력프로젝트(캡스톤디자인) '수10수11수8수9'
    ms = T.parse_times("수10수11수8수9")
    assert ms == [{"weekday": 2, "periods": [8, 9, 10, 11], "room": ""}]


def test_parse_split_same_day():
    ms = T.parse_times("월1월3")
    assert [m["periods"] for m in ms] == [[1], [3]]


@pytest.mark.parametrize("raw", ["TBA", "월5 온라인", "월99", "x"])
def test_parse_unknown_format_raises(raw):
    with pytest.raises(T.ParseError):
        T.parse_times(raw)


def test_parse_empty_is_empty():
    assert T.parse_times("") == []


def test_period_times_follow_school_module():
    pm = sessions.default_period_map()
    assert sessions.period_span(0, [5, 6], pm) == ("13:00", "14:50")       # 월 50분 × 2
    assert sessions.period_span(1, [5], pm) == ("15:00", "16:15")          # 화 75분
    assert sessions.period_span(3, [1, 2], pm) == ("09:00", "11:45")
    assert sessions.period_span(2, [8, 9, 10, 11], pm) == ("16:00", "19:50")
    assert sessions.period_span(1, [11], pm) == ("19:00", "19:50")         # 화·목 표에 없는 교시는 월수금 표로


def test_normalize_meetings():
    ms = T.normalize_meetings([{"weekday": "수", "periods": [5]}, {"weekday": 0, "periods": ["6", 5], "room": " 공2 "}])
    assert ms == [{"weekday": 0, "periods": [5, 6], "room": "공2"}, {"weekday": 2, "periods": [5], "room": ""}]
    with pytest.raises(T.ParseError):
        T.normalize_meetings([{"weekday": 1, "periods": [11]}])             # 화·목은 10교시까지
    with pytest.raises(T.ParseError):
        T.normalize_meetings([{"weekday": 0, "periods": [1]}, {"weekday": 0, "periods": [1]}])
    with pytest.raises(T.ParseError):
        T.normalize_meetings([{"weekday": 9, "periods": [1]}])
    with pytest.raises(T.ParseError):
        T.normalize_meetings([{"weekday": 0, "periods": []}])


def test_parse_page_fixture():
    rows, hidden, total = T.parse_page((FIXTURES / "suup053c_os.html").read_text(encoding="utf-8"))
    assert total == 2 and len(rows) == 2
    assert hidden["__VIEWSTATE"] == "test-__viewstate"
    r = rows[1]
    assert (r["name"], r["code"], r["section"], r["times"]) == ("운영체제", "CIS2001", "2", "월5월6수5")
    assert r["rooms"] == ["공2-100", "공2-100", "공2-100"]
    assert T.pick_row(rows, "cis2001", "02")["times"] == "월5월6수5"
    assert T.pick_row(rows, "CIS2001", "3") is None


def test_search_names():
    assert T.search_names("산학협력프로젝트(캡스톤디자인)") == ["산학협력프로젝트(캡스톤디자인)", "산학협력프로젝트"]
    assert T.search_names("운영체제") == ["운영체제"]


class FakeSearch:
    def __init__(self, table):
        self.table, self.calls = table, []

    def search(self, name):
        self.calls.append(name)
        if name == "boom":
            raise ConnectionError("down")
        return self.table.get(name, [])


def _row(code, sec, times, rooms=()):
    return {"name": "", "code": code, "section": sec, "times": times, "rooms": list(rooms), "professor": "",
            "campus": "광주", "credits": "3", "category": "전선"}


def test_lookup_statuses():
    fake = FakeSearch({
        "운영체제": [_row("CIS2001", "1", "화5목5"), _row("CIS2001", "2", "월5월6수5")],
        "캡스톤": [],
        "캡스톤디자인": [],
        "원격": [_row("CLT0001", "1", "")],
        "이상": [_row("CLT0002", "1", "월5 온라인")],
        "산학협력프로젝트": [_row("SAI0029", "1", "수10수11수8수9")],
    })
    courses = [
        {"id": "a", "short": "운영체제", "code": "CIS2001", "section": "2"},
        {"id": "b", "short": "캡스톤", "code": "X1", "section": "1"},
        {"id": "c", "short": "원격", "code": "CLT0001", "section": "1"},
        {"id": "d", "short": "이상", "code": "CLT0002", "section": "1"},
        {"id": "e", "short": "무코드", "code": "", "section": ""},
        {"id": "f", "short": "boom", "code": "Z1", "section": "1"},
        {"id": "g", "short": "산학협력프로젝트(캡스톤디자인)", "code": "SAI0029", "section": "1"},
        {"id": "h", "short": "운영체제", "code": "CIS2001", "section": "9"},
    ]
    res = {r["courseId"]: r for r in T.lookup(courses, 2026, "2", search=fake)}
    assert res["a"]["status"] == "found" and T.meetings_text(res["a"]["meetings"]) == "월 5·6교시 · 수 5교시"
    assert res["b"]["status"] == "not_found"
    assert res["c"]["status"] == "no_time"
    assert res["d"]["status"] == "parse_error"
    assert res["e"]["status"] == "no_code"
    assert res["f"]["status"] == "error"
    assert res["g"]["status"] == "found" and res["g"]["meetings"][0]["periods"] == [8, 9, 10, 11]
    assert res["h"]["status"] == "not_found"
    # 같은 이름은 한 번만 검색, 괄호 이름은 0건일 때만 괄호 앞으로 다시
    assert fake.calls.count("운영체제") == 1
    assert fake.calls[-2:] == ["산학협력프로젝트(캡스톤디자인)", "산학협력프로젝트"]
