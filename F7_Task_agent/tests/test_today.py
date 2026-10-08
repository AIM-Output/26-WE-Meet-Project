"""오늘 남은 시간 (F7-R21 · 5절) — 취침 − 지금 − 수업·일정(겹침 한 번) − 학습 분량."""
from datetime import datetime

from tasks import config as C
from tasks import today as T


def ev(kind, start, end=None, all_day=False, **props):
    return {"title": f"{kind} 일정", "start": start, "end": end, "allDay": all_day,
            "extendedProps": {"kind": kind, **props}}


def settings(bed="24:00"):
    s = C.default_settings()
    s["bedTime"] = bed
    return s


def test_bed_at_midnight_and_after_midnight():
    now = datetime(2026, 10, 6, 14, 0)
    assert T.bed_at(now, "24:00") == datetime(2026, 10, 7, 0, 0)
    assert T.bed_at(now, "23:00") == datetime(2026, 10, 6, 23, 0)
    assert T.bed_at(now, "01:30") == datetime(2026, 10, 7, 1, 30)


def test_small_hours_still_belong_to_last_night():
    """새벽 1시에 연 화면은 '어젯밤' 기준 — 24:00 취침이면 이미 지났다(0시간), 02:00 취침이면 1시간 남았다."""
    now = datetime(2026, 10, 7, 1, 0)
    assert T.budget(now, settings("24:00"))["leftHours"] == 0
    assert T.budget(now, settings("02:00"))["leftHours"] == 1


def test_busy_classes_and_events_are_subtracted_once():
    now = datetime(2026, 10, 6, 12, 0)
    events = [
        ev("class", "2026-10-06T13:30:00", "2026-10-06T14:45:00", state="scheduled"),
        ev("user", "2026-10-06T14:00:00", "2026-10-06T15:00:00"),          # 수업과 15분 겹침 → 한 번만
        ev("class", "2026-10-06T16:30:00", "2026-10-06T17:45:00", state="canceled"),   # 휴강은 빼지 않는다
        ev("user", "2026-10-06", "2026-10-07", all_day=True),              # 종일 일정은 시간을 차지하지 않는다
        ev("user", "2026-10-06T20:00:00", "2026-10-06T21:00:00", isTodo=True),   # 할 일은 빼지 않는다
        ev("deadline", "2026-10-06T23:30:00", "2026-10-07T00:00:00"),      # 과제 마감도 아니다
        ev("academic", "2026-10-06T09:00:00", "2026-10-06T18:00:00"),
        ev("class", "2026-10-06T09:00:00", "2026-10-06T10:15:00", state="scheduled"),  # 이미 지난 수업
    ]
    b = T.budget(now, settings(), events)
    assert b["untilBedHours"] == 12
    assert b["busyHours"] == 1.5                     # 13:30 ~ 15:00
    assert b["leftHours"] == 10.5
    assert [x["title"] for x in b["busy"]] == ["class 일정", "user 일정"]


def test_event_in_progress_counts_from_now():
    now = datetime(2026, 10, 6, 14, 0)
    b = T.budget(now, settings(), [ev("class", "2026-10-06T13:30:00", "2026-10-06T14:45:00")])
    assert b["busyHours"] == 0.75


def test_exam_without_end_is_one_hour():
    now = datetime(2026, 10, 6, 12, 0)
    b = T.budget(now, settings(), [ev("exam", "2026-10-06T15:00:00")])
    assert b["busyHours"] == 1


def test_event_after_bed_is_ignored_and_bed_after_midnight_counts_it():
    now = datetime(2026, 10, 6, 20, 0)
    late = [ev("user", "2026-10-07T00:30:00", "2026-10-07T01:00:00")]
    assert T.budget(now, settings("24:00"), late)["busyHours"] == 0
    assert T.budget(now, settings("02:00"), late)["busyHours"] == 0.5


def test_study_minutes_and_over_flag():
    now = datetime(2026, 10, 6, 20, 0)
    b = T.budget(now, settings(), [], study_minutes=90, need_hours=3)
    assert b["studyHours"] == 1.5 and b["leftHours"] == 2.5
    assert b["over"] is True
    b = T.budget(now, settings(), [], study_minutes=0, need_hours=3)
    assert b["over"] is False


def test_never_negative():
    now = datetime(2026, 10, 6, 22, 0)
    b = T.budget(now, settings(), [ev("user", "2026-10-06T21:00:00", "2026-10-06T23:30:00")], study_minutes=300)
    assert b["leftHours"] == 0 and b["busyHours"] + b["studyHours"] == b["untilBedHours"]
