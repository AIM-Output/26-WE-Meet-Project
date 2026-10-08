"""공강 계산 — F8 5절 ① · F8-R01~R08 (2026-10-07: 낮 09:00~18:00)."""
from datetime import date, datetime

from conftest import TUE, cls, ev, spec, todo, tuesday_classes
from placement import config as C
from placement import service, slots


def day(d, events, settings, now=None):
    classes, busy = service.split_events(events)
    return [(s["start"], s["end"]) for s in
            slots.day_slots(date.fromisoformat(d), classes.get(d, []), busy.get(d, []), settings, now)]


def hm(x):
    return int(x[:2]) * 60 + int(x[3:])


def test_example_tuesday():
    """수업 뒤 10분 여유 → 11:00, 점심 전까지 · 마지막 수업 뒤 15:00~18:00 도 공강이다 (09~18 안은 전부)."""
    assert day(TUE, tuesday_classes(), spec()) == [(hm("11:00"), hm("12:00")), (hm("15:00"), hm("18:00"))]


def test_defaults_are_daytime_only():
    """2026-10-07 사용자 요청 — 배치 범위 09:00~18:00, 저녁은 F5 시험 공부 계획 몫. 하루 상한 없음."""
    d = C.DEFAULTS
    assert (d["dayStart"], d["dayEnd"]) == ("09:00", "18:00")
    assert "eveningStart" not in d and "dailyMaxHours" not in d and d["fillStudy"] is True
    assert max(e for _, e in day(TUE, [], C.default_settings())) == hm("18:00")


def test_day_without_classes_is_a_free_day():
    """수업 없는 날(공강 날)은 낮 전체 — 점심만 빼고."""
    assert day(TUE, [], spec()) == [(hm("09:00"), hm("12:00")), (hm("13:00"), hm("18:00"))]


def test_weekend_is_off_by_default():
    sat = "2026-10-03"
    assert day(sat, [], spec()) == []
    assert day(sat, [], spec(useWeekend=True)) == [(hm("09:00"), hm("12:00")), (hm("13:00"), hm("18:00"))]


def test_canceled_class_frees_time():
    """R08 — 휴강으로 빈 시간은 공강이 된다."""
    evs = [cls(TUE, "09:00", "10:15", "A"), cls(TUE, "10:30", "11:45", "B"), cls(TUE, "13:00", "14:15", "C"),
           cls(TUE, "14:30", "17:45", "D")]
    assert day(TUE, evs, spec()) == []                       # 틈이 다 30분 미만
    evs[1] = cls(TUE, "10:30", "11:45", "B", canceled=True)
    assert (hm("10:25"), hm("12:00")) in day(TUE, evs, spec())


def test_busy_events_are_subtracted():
    """R03 — 내 일정이 차지한 구간을 뺀다."""
    got = day(TUE, tuesday_classes() + [ev(TUE, "16:00", "17:00", "스터디")], spec())
    assert got == [(hm("11:00"), hm("12:00")), (hm("15:00"), hm("16:00")), (hm("17:00"), hm("18:00"))]


def test_timed_todo_and_exam_are_busy_but_deadlines_and_dated_todos_are_not():
    evs = [ev(TUE, "09:00", "10:00", "시험", kind="exam"), ev(TUE, "10:30", "11:00", "스터디"),
           ev(TUE, "15:00", "15:30", "시각 있는 할 일", isTodo=True), todo(1, TUE),
           {"id": "dl:1", "title": "과제", "start": f"{TUE}T16:30:00", "end": None, "allDay": False,
            "extendedProps": {"kind": "deadline"}}]
    got = day(TUE, evs, spec(lunchBreak=False))
    assert got == [(hm("10:00"), hm("10:30")), (hm("11:00"), hm("15:00")), (hm("15:30"), hm("18:00"))]


def test_academic_events_are_ignored_but_my_copies_count():
    """2026-10-07 — 학사 일정은 보지 않는다. 학사 일정에서 '내 일정에 넣기'로 만든 내 일정(user, origin ac:…)만 차지한다."""
    academic = ev(TUE, "10:00", "12:00", "수강 정정", kind="academic")
    assert day(TUE, [academic], spec(lunchBreak=False)) == [(hm("09:00"), hm("18:00"))]
    mine = ev(TUE, "10:00", "12:00", "수강 정정", origin="ac:jnu_calendar:1")
    assert day(TUE, [academic, mine], spec(lunchBreak=False)) == [(hm("09:00"), hm("10:00")), (hm("12:00"), hm("18:00"))]


def test_event_without_end_takes_an_hour():
    assert day(TUE, [ev(TUE, "13:00", None, "모임")], spec())[1] == (hm("14:00"), hm("18:00"))


def test_lunch_can_be_turned_off():
    """R05 — 점심은 기본 제외, 끄면 그 시간도 쓴다."""
    assert day(TUE, tuesday_classes(), spec(lunchBreak=False))[0] == (hm("11:00"), hm("12:50"))


def test_short_slots_are_dropped():
    """R06 — 30분 미만은 버린다."""
    evs = [cls(TUE, "09:00", "10:00"), cls(TUE, "10:45", "11:45"), cls(TUE, "13:00", "18:00")]
    assert day(TUE, evs, spec()) == []                       # 10:10~10:35 = 25분 · 11:55~12:00 = 5분


def test_buffer_setting():
    """R04 — 여유 0분이면 수업 끝나자마자 시작."""
    assert day(TUE, tuesday_classes(), spec(bufferMinutes=0, lunchBreak=False))[0] == (hm("10:50"), hm("13:00"))


def test_day_window_setting():
    assert day(TUE, [], spec(dayStart="08:00", dayEnd="19:00", lunchBreak=False)) == [(hm("08:00"), hm("19:00"))]


def test_today_starts_from_now_rounded_up():
    now = datetime(2026, 9, 29, 15, 43)
    assert day(TUE, [], spec(), now) == [(hm("15:50"), hm("18:00"))]
    assert slots.round_up(datetime(2026, 9, 29, 15, 40)) == hm("15:40")
    assert slots.round_up(datetime(2026, 9, 29, 15, 40, 5)) == hm("15:50")


def test_past_day_has_no_slots():
    assert day(TUE, [], spec(), datetime(2026, 9, 30, 8, 0)) == []


def test_event_crossing_midnight_is_split():
    evs = [{"id": "u:1", "title": "밤샘", "start": f"{TUE}T22:00:00", "end": "2026-09-30T01:00:00", "allDay": False,
            "extendedProps": {"kind": "user"}}]
    _, busy = service.split_events(evs)
    assert busy[TUE][0]["end"] == 24 * 60 and (busy["2026-09-30"][0]["start"], busy["2026-09-30"][0]["end"]) == (0, 60)
