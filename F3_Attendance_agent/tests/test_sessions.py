"""학사일정 읽기(F1) · 회차 만들기 — 날 단위 회차 · 자동 휴강(학사일정·공지) · 학교 지정 보강일 · 시간표 판 · 기록 덧씌우기."""
from datetime import date

from attendance import academic_calendar as AC, sessions as S
from conftest import F1_ROWS, OS_MEETINGS, SE_MEETINGS, make_f1

START, END = date(2026, 9, 1), date(2026, 12, 21)


def cal():
    return AC.load()


def test_load_reads_semester_holidays_makeups(f1):
    c = cal()
    assert c["available"]
    assert c["semesters"]["2026-2"] == {"start": "2026-09-01", "end": "2026-12-21"}
    assert c["holidays"]["2026-09-24"] == "추석연휴" and c["holidays"]["2026-09-25"] == "추석연휴"
    assert c["holidays"]["2026-10-05"] == "개천절 대체휴일"
    assert {m["date"]: m["original"] for m in c["makeups"]} == {
        "2026-12-09": "2026-10-05", "2026-12-10": "2026-09-24", "2026-12-11": "2026-09-25", "2026-12-14": "2026-10-09"}
    assert "2026-12-08" not in {m["date"] for m in c["makeups"]}          # 자체 보강일은 자동으로 넣지 않는다


def test_removed_rows_are_ignored_and_missing_db():
    make_f1(removed=("한글날 (휴업)",))
    assert "2026-10-09" not in cal()["holidays"]
    from attendance import config as C
    C.F1_DB.unlink()
    assert cal() == {"available": False, "semesters": {}, "holidays": {}, "makeups": []}


def test_second_semester_closing_in_january():
    make_f1([("제2학기 개강", "vacation", "2027-09-01", None), ("제2학기 종강", "vacation", "2028-01-05", None)])
    assert cal()["semesters"]["2027-2"] == {"start": "2027-09-01", "end": "2028-01-05"}
    make_f1(F1_ROWS)


def test_fixed_holidays_and_semester_guess():
    assert AC.fixed_holidays(START, END) == {"2026-10-03": "개천절", "2026-10-09": "한글날"}
    assert AC.semester_of(date(2026, 10, 1)) == "2026-2"
    assert AC.semester_of(date(2027, 1, 20)) == "2026-2"
    assert AC.semester_of(date(2026, 4, 1)) == "2026-1"


def _build(versions, marks=None, user_makeups=(), notice=None):
    c = cal()
    return S.build("74245", versions, START, END, holidays=c["holidays"], school_makeups=c["makeups"],
                   user_makeups=list(user_makeups), marks=marks or {}, notice_cancels=notice)


def test_one_session_per_day_and_auto_cancel_from_academic(f1):
    ss, orphans = _build([{"validFrom": "", "meetings": OS_MEETINGS}])
    regular = [s for s in ss if s["kind"] == "regular"]
    assert len(regular) == 32                                   # 월 16 + 수 16 (9/1 화 개강 ~ 12/21 월 종강)
    hol = [s for s in regular if s["state"] == "canceled"]
    assert [(s["date"], s["cancelSource"], s["autoCancel"]["reason"]) for s in hol] == [("2026-10-05", "academic", "개천절 대체휴일")]
    mk = [s for s in ss if s["kind"] == "makeup"]
    assert len(mk) == 1 and mk[0]["date"] == "2026-12-09" and mk[0]["periods"] == [5, 6]
    assert mk[0]["origin"] == "school" and mk[0]["makeupFor"] == "2026-10-05" and mk[0]["id"] == "cl:74245:2026-12-09:mk"
    assert ss[0]["id"] == "cl:74245:2026-09-02" and (ss[0]["start"], ss[0]["end"]) == ("13:00", "13:50") and orphans == []


def test_two_blocks_same_day_are_one_session(f1):
    ss, _ = _build([{"validFrom": "", "meetings": [{"weekday": 0, "periods": [1]}, {"weekday": 0, "periods": [3]}]}])
    first = ss[0]
    assert first["date"] == "2026-09-07" and first["periods"] == [1, 3] and (first["start"], first["end"]) == ("09:00", "11:50")
    assert len([s for s in ss if s["date"] == "2026-09-07"]) == 1


def test_tuesday_thursday_times_and_makeup(f1):
    ss, _ = S.build("74261", [{"validFrom": "", "meetings": SE_MEETINGS}], START, END, holidays=cal()["holidays"],
                    school_makeups=cal()["makeups"], user_makeups=[], marks={})
    thu = [s for s in ss if s["date"] == "2026-09-24"][0]
    assert thu["state"] == "canceled" and (thu["start"], thu["end"]) == ("15:00", "16:15")
    assert [(s["date"], s["makeupFor"]) for s in ss if s["kind"] == "makeup"] == [("2026-12-10", "2026-09-24")]


def test_notice_cancel_only_on_class_days(f1):
    notice = {"2026-09-16": {"reason": "오늘 수업 휴강(9/16)", "url": "u", "posted": "2026-09-16"},
              "2026-09-17": {"reason": "목요일 휴강", "url": "u2", "posted": "2026-09-14"}}   # 목요일은 운영체제 수업 없음
    ss, _ = _build([{"validFrom": "", "meetings": OS_MEETINGS}], notice=notice)
    by = {s["date"]: s for s in ss}
    assert by["2026-09-16"]["state"] == "canceled" and by["2026-09-16"]["cancelSource"] == "eclass"
    assert by["2026-09-16"]["autoCancel"]["url"] == "u" and "2026-09-17" not in by
    assert not [s for s in ss if s["kind"] == "makeup" and s["makeupFor"] == "2026-09-16"]   # 공지 휴강엔 학교 보강 없음


def test_restored_auto_cancel_and_no_school_makeup(f1):
    marks = {"cl:74245:2026-10-05": {"state": "scheduled", "attendance": "present", "memo": None}}
    ss, _ = _build([{"validFrom": "", "meetings": OS_MEETINGS}], marks)
    s = [x for x in ss if x["date"] == "2026-10-05"][0]
    assert s["state"] == "scheduled" and s["attendance"] == "present" and s["cancelSource"] is None
    assert s["autoCancel"]["source"] == "academic"               # 근거는 남는다 (되돌렸다는 표시용)
    assert not [x for x in ss if x["kind"] == "makeup"]


def test_marks_cancel_and_orphans(f1):
    marks = {
        "cl:74245:2026-09-07": {"state": "canceled", "attendance": "absent", "memo": None},
        "cl:74245:2026-09-09": {"state": None, "attendance": "late", "memo": "버스"},
        "cl:74245:2026-09-08": {"state": None, "attendance": "absent", "memo": None},    # 화요일 — 맞는 회차 없음
    }
    ss, orphans = _build([{"validFrom": "", "meetings": OS_MEETINGS}], marks)
    by = {s["id"]: s for s in ss}
    c = by["cl:74245:2026-09-07"]
    assert c["state"] == "canceled" and c["cancelSource"] == "user" and c["attendance"] is None and c["recorded"] == "absent"
    assert by["cl:74245:2026-09-09"]["attendance"] == "late" and by["cl:74245:2026-09-09"]["memo"] == "버스"
    assert [o["id"] for o in orphans] == ["cl:74245:2026-09-08"]


def test_versions_change_mid_semester(f1):
    later = [{"weekday": 1, "periods": [3]}]
    ss, _ = _build([{"validFrom": "", "meetings": OS_MEETINGS}, {"validFrom": "2026-10-12", "meetings": later}])
    before = [s for s in ss if s["date"] < "2026-10-12" and s["kind"] == "regular"]
    after = [s for s in ss if s["date"] >= "2026-10-12" and s["kind"] == "regular"]
    assert {s["weekday"] for s in before} == {0, 2} and {s["weekday"] for s in after} == {1}
    assert [s["periods"] for s in ss if s["kind"] == "makeup"] == [[5, 6]]      # 10/5 휴업 회차는 옛 시간표 교시로 보강


def test_user_makeup(f1):
    um = [{"id": "cl:74245:2026-10-17:mk", "date": "2026-10-17", "periods": [1, 2], "memo": "토 보강"}]
    ss, _ = _build([{"validFrom": "", "meetings": OS_MEETINGS}], user_makeups=um)
    s = [x for x in ss if x["origin"] == "user"][0]
    assert (s["start"], s["end"], s["memo"]) == ("09:00", "10:50", "토 보강")


def test_no_timetable_no_sessions(f1):
    assert _build([]) == ([], [])
