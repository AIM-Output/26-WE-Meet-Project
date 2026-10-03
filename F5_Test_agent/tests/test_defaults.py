"""과목마다 중간·기말 — 임의 시험 일정 (2026-10-01 사용자 요청, exams/defaults.py).

  - 모든 과목은 중간·기말 2회. 시험이 없는 과목은 과목별로 끈다
  - 일정이 없으면 학사일정 '중간 수업평가' 기간 안에서 그 과목의 수업 회차로 잡는다(시험 주간의 첫 수업)
  - 공지에서 진짜 일정이 나오면 그 자리가 바뀐다 · 직접 고칠 수도 있다
  - 그 과목의 중간고사가 지나면 기말고사가 생긴다
"""
from datetime import date

import pytest

from exams import academic, defaults, service, store

from conftest import F1_ITEMS, add_exam, courses, make_eclass, make_f1  # noqa: E402

OCT1 = date(2026, 10, 1)
OS, SE = "74245", "74261"          # 운영체제(월·수 13:00) · 소프트웨어공학론(화·목 15:00)


def mid(con, cid):
    return store.exam(con, service.exam_id(cid, "midterm", ""))


def fin(con, cid):
    return store.exam(con, service.exam_id(cid, "final", ""))


# ---------------------------------------------------------------- 학사일정 읽기

def test_periods_from_academic_calendar(db):
    make_f1()
    p = academic.periods("2026-2")
    assert (p["start"], p["end"]) == (date(2026, 9, 1), date(2026, 12, 21))
    assert p["midterm"]["evaluation"] == (date(2026, 10, 12), date(2026, 10, 23))
    assert p["midterm"]["exam"] == (date(2026, 10, 19), date(2026, 10, 23))   # 학과 공지 '시험기간 … 열람' 행은 거른다
    assert p["final"]["evaluation"] == (date(2026, 12, 15), date(2026, 12, 31))
    assert p["final"]["window"] == (date(2026, 12, 15), date(2026, 12, 21))   # 종강까지로 자른다


def test_second_semester_evaluation_spilling_into_january(db):
    make_f1([("제2학기 종강", "2025-12-22", None), ("제2학기 최종 수업평가", "2025-12-16", "2026-01-05")])
    p = academic.periods("2025-2")
    assert p["final"]["evaluation"] == (date(2025, 12, 16), date(2026, 1, 5))
    assert p["final"]["window"] == (date(2025, 12, 16), date(2025, 12, 22))
    assert academic.periods("2026-2")["final"]["evaluation"] is None


def test_no_academic_calendar_means_no_guessing(db):
    out = defaults.ensure(db, OCT1, courses)
    assert out["created"] == []
    assert any("학사일정" in h for h in out["hints"])
    assert mid(db, OS) is None


# ---------------------------------------------------------------- 자리 고르기

def test_place_picks_first_class_of_exam_week(semester):
    p = academic.periods("2026-2")
    os_ = defaults.place("midterm", p["midterm"], semester[OS], OCT1)
    se_ = defaults.place("midterm", p["midterm"], semester[SE], OCT1)
    assert (os_["date"], os_["time"], os_["endTime"]) == ("2026-10-19", "13:00", "14:50")    # 월
    assert (se_["date"], se_["time"]) == ("2026-10-20", "15:00")                             # 화
    assert "중간 수업평가" in se_["note"] and "화 15:00" in se_["note"]


def test_place_without_timetable_uses_first_weekday_without_time(semester):
    p = academic.periods("2026-2")
    spot = defaults.place("midterm", p["midterm"], None, OCT1)
    assert (spot["date"], spot["time"]) == ("2026-10-19", "")
    assert "시간표가 없어" in spot["note"] and "시각 미정" in spot["note"]


def test_place_never_in_the_past(semester):
    p = academic.periods("2026-2")
    # 10/20 에 처음 계산하면 그 주의 남은 첫 수업
    spot = defaults.place("midterm", p["midterm"], semester[OS], date(2026, 10, 20))
    assert spot["date"] == "2026-10-21"
    # 기간이 다 지났으면 잡지 않는다
    assert defaults.place("midterm", p["midterm"], semester[OS], date(2026, 10, 24)) is None


# ---------------------------------------------------------------- 만들기

def test_every_course_gets_a_midterm(db, semester):
    out = defaults.ensure(db, OCT1, courses)
    assert {(x["course"], x["type"]) for x in out["created"]} == {("운영체제", "midterm"), ("소프트웨어공학론", "midterm")}
    m = mid(db, OS)
    assert (m["date"], m["time"], m["source"], m["status"]) == ("2026-10-19", "13:00", "auto", "confirmed")
    assert m["note"]
    assert fin(db, OS) is None                                  # 기말은 중간고사가 끝난 뒤에
    # 다시 불러도 같은 것을 또 만들지 않는다
    again = defaults.ensure(db, OCT1, courses)
    assert again["skipped"] or again["created"] == []
    assert len(store.exam_rows(db)) == 2


def test_auto_exam_shows_in_overview_and_calendar(db, semester):
    o = service.overview(db, courses, today=OCT1)
    autos = [e for e in o["exams"] if e["isAuto"]]
    assert len(autos) == 2
    assert autos[0]["sourceLabel"] == "임의 일정" and autos[0]["note"]
    assert o["defaults"]["periods"]["midterm"]["window"] == ["2026-10-12", "2026-10-23"]
    assert {c["courseId"]: (c["midterm"], c["final"]) for c in o["courseSettings"]} == {OS: (True, True), SE: (True, True)}
    # 날짜가 확정되지 않은 임의 일정은 전체 캘린더에 넣지 않는다 (2026-10-01)
    ev = [x for x in service.calendar_events(db, None, None, courses, OCT1) if x["extendedProps"]["kind"] == "exam"]
    assert ev == []
    # 공부 캘린더에는 '임의' 표시를 달아 보여 준다
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, OCT1)
    exams = [x for d in cal["days"] for x in d["exams"]]
    assert len(exams) == 2 and all(x["isAuto"] for x in exams) and exams[0]["time"] == "13:00"


def test_study_plan_can_be_made_for_auto_exam(db, semester):
    defaults.ensure(db, OCT1, courses)
    out = service.create_plan(db, mid(db, SE)["id"], {"totalPages": 100}, OCT1, courses)
    assert out["plan"]["state"] == "active"
    assert out["plan"]["days"][-1]["date"] < "2026-10-20"


def test_existing_real_midterm_is_kept(db, semester):
    add_exam(db, when="2026-10-22", etype="midterm", course=SE, time="15:00")
    defaults.ensure(db, OCT1, courses)
    m = mid(db, SE)
    assert (m["source"], m["date"]) == ("manual", "2026-10-22")


def test_midterm_window_already_over_makes_no_midterm(db, semester):
    out = defaults.ensure(db, date(2026, 10, 25), courses)
    assert not [x for x in out["created"] if x["type"] == "midterm"]


# ---------------------------------------------------------------- 시험 유무 (과목별)

def test_turning_off_removes_auto_and_turning_on_brings_it_back(db, semester):
    defaults.ensure(db, OCT1, courses)
    out = service.set_course_exams(db, OS, {"midterm": False}, courses, OCT1)
    assert out["setting"]["midterm"] is False and out["course"]["midtermExam"] is None
    assert mid(db, OS) is None and out["removed"]
    out = service.set_course_exams(db, OS, {"midterm": True}, courses, OCT1)
    assert mid(db, OS)["source"] == "auto"


def test_course_without_exams_gets_nothing(db, semester):
    store.set_course_setting(db, OS, midterm=False, final=False)
    defaults.ensure(db, OCT1, courses, force=True)
    defaults.ensure(db, date(2026, 10, 30), courses, force=True)
    assert mid(db, OS) is None and fin(db, OS) is None


def test_turning_off_keeps_real_exams(db, semester):
    add_exam(db, when="2026-10-22", etype="midterm", course=SE)
    service.set_course_exams(db, SE, {"midterm": False}, courses, OCT1)
    assert mid(db, SE) is not None                              # 직접 넣은 시험은 진짜 정보라 남긴다


def test_deleting_auto_exam_turns_the_course_setting_off(db, semester):
    defaults.ensure(db, OCT1, courses)
    out = service.delete_exam(db, mid(db, OS)["id"])
    assert "다시 켤 수 있습니다" in out["note"]
    assert store.course_setting(db, OS)["midterm"] is False
    defaults.ensure(db, OCT1, courses, force=True)
    assert mid(db, OS) is None                                  # 다시 생기지 않는다


@pytest.mark.parametrize("body", [{}, {"quiz": True}, {"midterm": "yes"}])
def test_bad_course_setting(db, semester, body):
    with pytest.raises(service.Invalid):
        service.set_course_exams(db, OS, body, courses, OCT1)


# ---------------------------------------------------------------- 진짜 일정이 나오면

SE_NOTICE = "1. 일정: 10월 22일 목요일 오후 3시부터 4시까지\n2. 위치: 박물관 시청각실\n4. 시험 범위: 10월 15일 까지 강의한 내용 전반"


def test_notice_replaces_auto_midterm(db, semester):
    defaults.ensure(db, OCT1, courses)
    before = mid(db, SE)
    make_eclass([(SE, "2026-10-02 17:12", "중간고사 장소 및 준비물 공지", SE_NOTICE)])
    sent = []
    out = service.sync_notices(db, OCT1, sent.append, courses)
    after = mid(db, SE)
    assert after["id"] == before["id"]                           # 같은 자리
    assert (after["source"], after["date"], after["time"], after["place"]) == ("notice", "2026-10-22", "15:00", "박물관 시청각실")
    assert after["note"] == ""
    assert store.jload(after["changed"], {})["kind"] == "confirmed"
    assert out["confirmed"] and out["confirmed"][0]["from"] == "2026-10-20"
    assert out["postponed"] == []                               # '연기'가 아니다 — 처음으로 나온 일정이다
    assert sent and "일정이 나왔습니다" in sent[0]["title"]


def test_notice_keeps_scope_user_set_on_auto_exam(db, semester):
    defaults.ensure(db, OCT1, courses)
    eid = mid(db, OS)["id"]
    service.patch_exam(db, eid, {"scopeWeeks": [1, 2, 3]}, courses, OCT1)
    assert mid(db, OS)["source"] == "auto"                       # 범위만 넣었다 — 날짜는 아직 추측
    make_eclass([(OS, "2026-10-02 10:00", "중간고사 안내", "중간고사는 10월 21일 오후 1시입니다")])
    service.sync_notices(db, OCT1, None, courses)
    m = mid(db, OS)
    assert (m["source"], m["date"]) == ("notice", "2026-10-21")
    assert store.jload(m["scope_weeks"], []) == [1, 2, 3]


def test_user_can_fix_the_date_of_auto_exam(db, semester):
    defaults.ensure(db, OCT1, courses)
    eid = mid(db, OS)["id"]
    out = service.patch_exam(db, eid, {"date": "2026-10-21", "time": "13:00"}, courses, OCT1)
    assert (out["source"], out["isAuto"], out["date"]) == ("manual", False, "2026-10-21")
    # 직접 고친 일정은 공지가 덮어쓰지 않는다
    make_eclass([(OS, "2026-10-02 10:00", "중간고사 안내", "중간고사는 10월 19일입니다")])
    service.sync_notices(db, OCT1, None, courses)
    assert mid(db, OS)["date"] == "2026-10-21"


def test_adding_midterm_takes_the_auto_slot(db, semester):
    defaults.ensure(db, OCT1, courses)
    eid = mid(db, OS)["id"]
    e = add_exam(db, when="2026-10-21", etype="midterm", course=OS, time="13:00")
    assert e["id"] == eid and e["source"] == "manual"
    assert len([r for r in store.exam_rows(db) if r["course_id"] == OS]) == 1
    with pytest.raises(service.Conflict):
        add_exam(db, when="2026-10-23", etype="midterm", course=OS)


def test_adding_turns_course_setting_back_on(db, semester):
    store.set_course_setting(db, OS, midterm=False)
    add_exam(db, when="2026-10-21", etype="midterm", course=OS)
    assert store.course_setting(db, OS)["midterm"] is True


# ---------------------------------------------------------------- 시간표가 바뀌면

def test_auto_exam_follows_timetable_change(db, semester):
    defaults.ensure(db, OCT1, courses)
    semester[OS] = [s for s in semester[OS] if s["weekday"] == 2]          # 수요일만 남았다
    out = defaults.ensure(db, OCT1, courses, force=True)
    assert out["moved"] and mid(db, OS)["date"] == "2026-10-21"


def test_auto_exam_with_plan_does_not_move(db, semester):
    defaults.ensure(db, OCT1, courses)
    service.create_plan(db, mid(db, OS)["id"], {"totalPages": 50}, OCT1, courses)
    semester[OS] = [s for s in semester[OS] if s["weekday"] == 2]
    out = defaults.ensure(db, OCT1, courses, force=True)
    assert out["moved"] == [] and mid(db, OS)["date"] == "2026-10-19"   # 등록한 블록이 엇나가지 않게


# ---------------------------------------------------------------- 기말고사

def test_final_comes_after_that_courses_midterm(db, semester):
    defaults.ensure(db, OCT1, courses)                          # OS 10/19 · SE 10/20
    defaults.ensure(db, date(2026, 10, 20), courses)            # OS 중간이 지났다, SE 는 오늘이다
    assert fin(db, OS) is not None and fin(db, SE) is None
    f = fin(db, OS)
    assert (f["date"], f["time"], f["source"]) == ("2026-12-16", "13:00", "auto")    # 기말 주간(12/15~)의 첫 수업(수)
    assert "최종 수업평가" in f["note"]
    defaults.ensure(db, date(2026, 10, 21), courses)
    assert fin(db, SE)["date"] == "2026-12-15"                   # 화 15:00


def test_final_without_midterm_waits_for_midterm_period_to_end(db, semester):
    store.set_course_setting(db, OS, midterm=False)
    defaults.ensure(db, date(2026, 10, 23), courses, force=True)
    assert fin(db, OS) is None
    defaults.ensure(db, date(2026, 10, 24), courses, force=True)
    assert fin(db, OS) is not None


def test_final_follows_real_midterm_date(db, semester):
    add_exam(db, when="2026-10-22", etype="midterm", course=SE)
    defaults.ensure(db, date(2026, 10, 22), courses)
    assert fin(db, SE) is None
    defaults.ensure(db, date(2026, 10, 23), courses)
    assert fin(db, SE) is not None


def test_status_creates_finals_and_notifies_once(db, semester):
    defaults.ensure(db, OCT1, courses)
    sent = []
    service.status_summary(db, courses, date(2026, 10, 24), notify=sent.append)
    assert fin(db, OS) and fin(db, SE)
    finals = [a for a in sent if "기말고사" in a["title"]]
    assert len(finals) == 1 and "2과목" in finals[0]["title"]
    service.status_summary(db, courses, date(2026, 10, 24), notify=sent.append)
    assert len([a for a in sent if "기말고사" in a["title"]]) == 1


def test_final_period_missing_is_reported(db, semester):
    make_f1([x for x in F1_ITEMS if "기말" not in x[0] and "최종" not in x[0]])
    defaults.ensure(db, OCT1, courses)
    out = defaults.ensure(db, date(2026, 10, 24), courses, force=True)
    assert fin(db, OS) is None and out["created"] == []
    assert any("최종 수업평가" in h for h in out["hints"])


# ---------------------------------------------------------------- 확정 여부 · 시각 미정 → 수업 시간 (2026-10-01)

def test_review_notice_exam_is_not_on_main_calendar(db, semester):
    make_eclass([(SE, "2026-10-02 10:00", "수업 안내", "10월 22일: 기획서 발표")])
    service.sync_notices(db, OCT1, None, courses)
    row = store.exam_rows(db)[0]
    assert row["status"] == "review"
    assert service.calendar_events(db, None, None, courses, OCT1) == []
    service.patch_exam(db, row["id"], {"status": "confirmed"}, courses, OCT1)
    assert len(service.calendar_events(db, None, None, courses, OCT1)) == 1      # 확인하면 들어간다


def test_missing_time_becomes_class_time(db, semester):
    """발표·시험의 시각 미정은 그 과목 수업 시간으로 채운다."""
    make_eclass([(SE, "2026-10-02 10:00", "[수업] 발표 일정 안내", "10월 22일 예정이며 기획서 발표")])
    service.sync_notices(db, OCT1, None, courses)
    defaults.ensure(db, OCT1, courses, force=True)
    pres = [r for r in store.exam_rows(db) if r["type"] == "presentation"][0]
    assert (pres["time"], pres["end_time"], pres["time_auto"]) == ("15:00", "16:15", 1)      # 목 15:00 수업
    # 공지를 다시 읽어도 비우지 않는다
    make_eclass([(SE, "2026-10-02 10:00", "[수업] 발표 일정 안내", "10월 22일 예정이며 기획서 발표"),
                 (SE, "2026-10-03 10:00", "발표 안내 2", "10월 22일 기획서 발표 순서 공지")])
    service.sync_notices(db, OCT1, None, courses)
    assert store.exam(db, pres["id"])["time"] == "15:00"
    view = service.exam_view(store.exam(db, pres["id"]), service.course_map(courses), OCT1)
    assert view["timeFromClass"] is True


def test_missing_time_on_non_class_day_uses_weekday_or_first_class(db, semester):
    e = add_exam(db, when="2026-10-24", etype="quiz", course=SE)        # 토요일 — 수업이 없다
    defaults.ensure(db, OCT1, courses, force=True)
    assert store.exam(db, e["id"])["time"] == "15:00"                   # 그 과목 첫 수업 시간
    assert defaults.class_time(semester[OS], "2026-12-28")["start"] == "13:00"   # 월요일 — 같은 요일 수업 시간


def test_study_calendar_shows_subject_time_amount(db, semester):
    defaults.ensure(db, OCT1, courses)
    service.create_plan(db, mid(db, OS)["id"], {"totalPages": 60, "studyDays": 3}, OCT1, courses)
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, OCT1)
    blocks = [b for d in cal["days"] for b in d["blocks"]]
    study = [b for b in blocks if b["kind"] == "study"]
    assert [b["pages"] for b in study] == [20, 20, 20]
    # 기본 난이도 '보통' = 쪽당 1.5분 (2026-10-02) → 20쪽 30분
    assert study[0]["course"] == "운영체제" and study[0]["time"] == "19:00" and study[0]["minutes"] == 30
    days = {d["date"]: d for d in cal["days"]}
    assert days["2026-10-19"]["exams"][0]["isAuto"] is True
    with pytest.raises(service.Invalid):
        service.study_calendar(db, "2026-10-01", "2027-03-01", courses, OCT1)


def test_plan_options_keep_registered_dates(db, semester):
    defaults.ensure(db, OCT1, courses)
    eid = mid(db, OS)["id"]
    service.create_plan(db, eid, {"totalPages": 60, "studyDates": ["2026-10-05", "2026-10-07", "2026-10-09"]}, OCT1, courses)
    o = service.default_options(db, store.exam(db, eid), OCT1)
    assert o["studyDates"] == ["2026-10-05", "2026-10-07", "2026-10-09"]


def test_rule_change_is_not_skipped_by_old_stamp(db, semester, monkeypatch):
    """규칙이 바뀌면 같은 날·같은 데이터여도 다시 계산한다 (2026-10-01 실제로 생긴 일의 회귀 시험).

    시각 채우기가 없던 버전이 저장한 도장 때문에 산학협력 발표 10/7 이 계속 '시각 미정'이었다."""
    make_eclass([(SE, "2026-10-02 10:00", "[수업] 발표 일정 안내", "10월 22일 예정이며 기획서 발표")])
    service.sync_notices(db, OCT1, None, courses)
    # 옛 규칙 버전으로 한 번 돈 상태를 만든다 — 그때는 시각을 채우지 않았다
    current = defaults.RULES_VERSION
    monkeypatch.setattr(defaults, "RULES_VERSION", current - 1)
    defaults.ensure(db, OCT1, courses, force=True)
    pres = [r for r in store.exam_rows(db) if r["type"] == "presentation"][0]
    store.update_exam(db, pres["id"], {"time": "", "end_time": "", "time_auto": 0})
    defaults.ensure(db, OCT1, courses, force=True)                 # 도장을 '지금 데이터'로 맞춰 둔다
    store.update_exam(db, pres["id"], {"time": "", "end_time": "", "time_auto": 0})
    monkeypatch.setattr(defaults, "RULES_VERSION", current)   # undo() 는 픽스처의 가짜 시간표까지 되돌린다 — 버전만 돌린다
    # 새 규칙으로 처음 부를 때 — 강제하지 않아도 돌아야 한다
    out = defaults.ensure(db, OCT1, courses)
    assert out["skipped"] is False
    assert store.exam(db, pres["id"])["time"] == "15:00"
