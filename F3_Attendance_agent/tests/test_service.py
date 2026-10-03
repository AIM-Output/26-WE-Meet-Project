"""사용자 조작 — 과목 동기화 · 시간표 저장/자동 반영 · 출결·휴강·보강 · 자동 휴강(학사일정·공지) · 누적 조정 · 경고 · 캘린더 · 이전."""
from datetime import timedelta

import pytest

from attendance import jobs, notices, service, store
from conftest import ECLASS, NOW, OS_MEETINGS, SE_MEETINGS, make_eclass


def setup(con, meetings=None):
    service.sync_courses(con, "2026-2", ECLASS)
    service.save_timetable(con, {"courses": [{"courseId": "74245", "meetings": meetings or OS_MEETINGS},
                                             {"courseId": "74261", "meetings": SE_MEETINGS}]},
                           semester="2026-2", now=NOW)


def view(con, cid="74245"):
    return service.course_view(con, "2026-2", cid, NOW)


def past_ids(con, cid="74245"):
    return [s["id"] for s in view(con, cid)["sessions"] if s["ended"] and s["state"] == "scheduled" and s["kind"] == "regular"]


def test_overview_current_semester_and_sync(db):
    o = service.overview(db, eclass=ECLASS, now=NOW)
    assert o["current"] == "2026-2" and o["semester"]["start"] == "2026-09-01"
    assert [c["short"] for c in o["courses"]] == ["운영체제", "소프트웨어공학론"]
    assert o["totals"]["needsTimetable"] == ["운영체제", "소프트웨어공학론"]
    assert o["courses"][0]["summary"]["level"] is None and o["periods"]["mwf"]["5"] == ["13:00", "13:50"]
    assert o["labels"]["attendance"] == {"present": "출석", "absent": "결석", "late": "지각", "excused": "공결", "none": "미입력"}
    service.sync_courses(db, "2026-2", [{**ECLASS[0], "short": "운영체제론"}])      # 이름이 바뀌어도 id 로
    assert view(db)["short"] == "운영체제론"


def test_save_timetable_generates_by_day(db):
    service.sync_courses(db, "2026-2", ECLASS)
    res = service.save_timetable(db, {"courses": [{"courseId": "74245", "meetings": OS_MEETINGS}]}, semester="2026-2", now=NOW)
    g = res["generated"][0]
    # 월 16 + 수 16 = 32회 + 학교 보강 1, 10/5 휴업(자동 휴강) → 총 32 − 1 + 1 = 32
    assert (g["sessions"], g["total"], g["text"]) == (33, 32, "월 5·6교시 · 수 5교시")
    assert view(db)["timetable"]["filledBy"] == "user"
    assert view(db)["summary"]["allowed"] == 8


def test_import_fills_auto_but_keeps_user_edits(db):
    service.sync_courses(db, "2026-2", ECLASS)
    found = {"status": "found", "meetings": OS_MEETINGS, "message": "", "raw": {"times": "월5월6수5"}}
    r = service.apply_import(db, "2026-2", [{"courseId": "74245", **found},
                                            {"courseId": "74261", "status": "not_found", "message": "없음"}])
    assert [f["name"] for f in r["filled"]] == ["운영체제"] and r["missing"][0]["name"] == "소프트웨어공학론"
    tt = view(db)["timetable"]
    assert tt["filledBy"] == "auto" and tt["autoText"] == "월 5·6교시 · 수 5교시" and tt["raw"]["times"] == "월5월6수5"
    service.save_timetable(db, {"courses": [{"courseId": "74245", "meetings": [{"weekday": 4, "periods": [1]}]}]},
                           semester="2026-2", now=NOW)
    r = service.apply_import(db, "2026-2", [{"courseId": "74245", **found}])
    assert r["kept"] and view(db)["timetable"]["text"] == "금 1교시"
    service.revert_timetable(db, "74245", semester="2026-2", now=NOW)
    assert view(db)["timetable"]["filledBy"] == "auto"


def test_attendance_alert_once_per_rise(db):
    setup(db)                                   # 운영체제 총 32회, 허용 8
    got = []
    ids = past_ids(db)                          # 9/2 · 9/7 · 9/9 · 9/14 · 9/16 · 9/21 · 9/23 · 9/28 · 9/30 · 10/7 · 10/12 · 10/14 · 10/19
    alerts = []
    for sid in ids[:4]:
        alerts += service.patch_session(db, sid, {"attendance": "absent"}, now=NOW, notify=got.append)["alerts"]
    assert [a["level"] for a in alerts] == ["caution"]            # 4 ≥ 4 → 주의, 한 번만
    assert got[0]["href"] == "/attendance?course=74245" and "4번 더 빠질 수 있습니다" in got[0]["body"]
    for sid in ids[4:7]:
        res = service.patch_session(db, sid, {"attendance": "absent"}, now=NOW, notify=got.append)
    assert res["alerts"] == [] and res["course"]["summary"]["level"] == "caution"     # 7, 여유 1 — 주의
    res = service.patch_session(db, ids[7], {"attendance": "absent"}, now=NOW, notify=got.append)   # 8, 여유 0
    assert [a["level"] for a in res["alerts"]] == ["danger"] and "한 번 더 빠지면 F" in res["alerts"][0]["title"]
    # 잘못 찍어 되돌렸다가 다시 찍어도 10분 안의 같은 단계는 다시 알리지 않는다
    service.patch_session(db, ids[7], {"attendance": None}, now=NOW, notify=got.append)
    res = service.patch_session(db, ids[7], {"attendance": "absent"}, now=NOW, notify=got.append)
    assert res["alerts"] == [] and len(got) == 2
    later = NOW + timedelta(minutes=30)
    service.patch_session(db, ids[7], {"attendance": "present"}, now=later)
    res = service.patch_session(db, ids[7], {"attendance": "absent"}, now=later, notify=got.append)
    assert [a["level"] for a in res["alerts"]] == ["danger"]
    res = service.patch_session(db, ids[8], {"attendance": "absent"}, now=later, notify=got.append)
    assert [a["level"] for a in res["alerts"]] == ["over"]
    assert [a["level"] for a in service.alert_history(db, "2026-2")] == ["over", "danger", "danger", "caution"]


def test_attendance_validation(db):
    setup(db)
    future = [s for s in view(db)["sessions"] if not s["started"]][0]["id"]
    with pytest.raises(service.Invalid):
        service.patch_session(db, future, {"attendance": "absent"}, now=NOW)
    service.patch_session(db, future, {"attendance": "excused", "memo": "예비군"}, now=NOW)   # 공결은 미리 적을 수 있다
    for bad in ("early", "skipped"):                                                        # 조퇴는 없다 (수정 ②)
        with pytest.raises(service.Invalid):
            service.patch_session(db, past_ids(db)[0], {"attendance": bad}, now=NOW)
    with pytest.raises(service.NotFound):
        service.patch_session(db, "cl:74245:2026-09-08", {"attendance": "absent"}, now=NOW)
    auto = [s for s in view(db)["sessions"] if s["state"] == "canceled"][0]["id"]
    with pytest.raises(service.Invalid):
        service.patch_session(db, auto, {"attendance": "absent"}, now=NOW)


def test_cancel_chip_and_attendance_in_one_step(db):
    setup(db)
    total = view(db)["summary"]["totalCount"]
    sid = past_ids(db)[1]
    service.patch_session(db, sid, {"attendance": "absent"}, now=NOW)
    res = service.patch_session(db, sid, {"state": "canceled"}, now=NOW)                  # 휴강 칩
    assert res["course"]["summary"]["totalCount"] == total - 1
    assert res["course"]["summary"]["absentCount"] == 0 and res["session"]["cancelSource"] == "user"
    res = service.patch_session(db, sid, {"state": "scheduled", "attendance": "late"}, now=NOW)   # 휴강 → 지각 칩
    assert res["session"]["state"] == "scheduled" and res["session"]["attendance"] == "late"
    # 자동 휴강(학사일정 휴업)을 풀면 수업함 — 학교 보강일 회차는 빠진다
    hol = [s for s in view(db)["sessions"] if s["cancelSource"] == "academic"][0]["id"]
    res = service.patch_session(db, hol, {"state": "scheduled"}, now=NOW)
    assert res["course"]["summary"]["makeupCount"] == 0 and res["course"]["summary"]["totalCount"] == total


def test_eclass_notice_auto_cancel(db):
    make_eclass([("74245", "2026-09-16 07:44", "오늘 수업 휴강(9/16)", "오늘 수업은 부득이 휴강 합니다."),
                 ("74245", "2026-09-20 10:00", "공지", "사정상 휴강합니다"),
                 ("74245", "2026-09-10 10:00", "9월 17일 휴강", "")])      # 목요일 — 운영체제는 수업 없음
    setup(db)
    v = view(db)
    s = [x for x in v["sessions"] if x["date"] == "2026-09-16"][0]
    assert s["state"] == "canceled" and s["cancelSource"] == "eclass" and s["autoCancel"]["reason"] == "오늘 수업 휴강(9/16)"
    assert v["summary"]["autoCanceled"] == {"academic": 1, "eclass": 1}
    assert [h["reason"] for h in v["noticeHints"]] == ["공지", "9월 17일 휴강"]
    assert "수업일이 아닙니다" in v["noticeHints"][1]["why"]
    res = service.patch_session(db, s["id"], {"state": "scheduled", "attendance": "present"}, now=NOW)   # 사실 수업함
    assert res["session"]["state"] == "scheduled" and res["session"]["autoCancel"]["source"] == "eclass"
    # 공지가 바뀌면(eclass 동기화) 도장이 바뀌어 화면이 다시 부른다
    stamp = service.data_stamp(db)
    make_eclass([])
    assert service.data_stamp(db) != stamp and view(db)["summary"]["autoCanceled"]["eclass"] == 0


def test_bulk_present_skips_future(db):
    setup(db)
    ids = past_ids(db)[:3]
    future = [s for s in view(db)["sessions"] if not s["started"]][0]["id"]
    res = service.bulk_attendance(db, [{"id": i, "attendance": "present"} for i in ids + [future]], now=NOW)
    assert res["updated"] == 3 and len(res["skipped"]) == 1 and res["courses"][0]["summary"]["presentCount"] == 3


def test_user_makeup_add_delete(db):
    setup(db)
    total = view(db)["summary"]["totalCount"]
    res = service.add_makeup(db, {"courseId": "74245", "date": "2026-10-17", "periods": [1, 2], "memo": "토요 보강"}, now=NOW)
    assert res["id"] == "cl:74245:2026-10-17:mk" and res["course"]["summary"]["totalCount"] == total + 1
    with pytest.raises(service.Conflict):
        service.add_makeup(db, {"courseId": "74245", "date": "2026-10-17", "periods": [3]}, now=NOW)
    with pytest.raises(service.Conflict):                                   # 학교 보강일과 같은 날
        service.add_makeup(db, {"courseId": "74245", "date": "2026-12-09", "periods": [3]}, now=NOW)
    with pytest.raises(service.Invalid):
        service.add_makeup(db, {"courseId": "74245", "date": "2026-10-24", "periods": [1, 3]}, now=NOW)
    service.patch_session(db, res["id"], {"attendance": "absent"}, now=NOW)
    service.delete_makeup(db, res["id"], now=NOW)
    assert view(db)["summary"]["totalCount"] == total and view(db)["summary"]["absentCount"] == 0
    school = [s for s in view(db)["sessions"] if s["origin"] == "school"][0]["id"]
    with pytest.raises(service.NotFound):
        service.delete_makeup(db, school)


def test_patch_course_settings_and_adjust(db):
    setup(db)
    res = service.patch_course(db, "74245", {"adjust": {"absent": 4, "late": 0}}, semester="2026-2", now=NOW)
    assert res["course"]["summary"]["effectiveAbsent"] == 4 and [a["level"] for a in res["alerts"]] == ["caution"]
    res = service.patch_course(db, "74245", {"limitRatio": 1 / 3, "lateToAbsence": 2}, semester="2026-2", now=NOW)
    assert res["course"]["settings"] == {"limitRatio": 1 / 3, "lateToAbsence": 2}
    assert res["course"]["summary"]["allowed"] == round(32 / 3, 2)
    for bad in ({"limitRatio": 0.9}, {"lateToAbsence": 1.5}, {"adjust": {"absent": "2"}}, {"name": "바꿈"}, {},
                {"countEarlyLeaveAsLate": True}):
        with pytest.raises(service.Invalid):
            service.patch_course(db, "74245", bad, semester="2026-2", now=NOW)
    res = service.patch_course(db, "74245", {"excluded": True}, semester="2026-2", now=NOW)
    assert res["course"]["excluded"] and service.overview(db, "2026-2", now=NOW)["totals"]["courses"] == 1


def test_manual_course(db):
    service.sync_courses(db, "2026-2", ECLASS)
    r = service.add_manual_course(db, {"name": "집중 세미나", "meetings": [{"weekday": 5, "periods": [1, 2, 3]}]},
                                  semester="2026-2", now=NOW)
    assert r["id"].startswith("mc:") and r["course"]["source"] == "manual"
    assert r["course"]["timetable"]["text"] == "토 1·2·3교시"
    sid = [s["id"] for s in r["course"]["sessions"] if s["ended"]][0]
    service.patch_session(db, sid, {"attendance": "late"}, now=NOW)        # 과목 id 에 ':' 가 있어도 찾는다
    service.patch_course(db, r["id"], {"name": "세미나"}, semester="2026-2", now=NOW)
    with pytest.raises(service.Conflict):
        service.add_manual_course(db, {"name": "집중 세미나"}, semester="2026-2")
    with pytest.raises(service.Conflict):
        service.delete_course(db, "74245", semester="2026-2")
    service.delete_course(db, r["id"], semester="2026-2")
    assert not db.execute("SELECT 1 FROM marks WHERE course_id = ?", (r["id"],)).fetchone()


def test_timetable_change_keeps_records(db):
    setup(db)
    past = past_ids(db)[:2]                                                # 9/2(수) · 9/7(월)
    for sid in past:
        service.patch_session(db, sid, {"attendance": "absent"}, now=NOW)
    # 교시만 바뀌면(월 5·6 → 월 5·6·7) 날짜가 같아 기록이 그대로 따라간다
    service.save_timetable(db, {"courses": [{"courseId": "74245", "meetings": [{"weekday": 0, "periods": [5, 6, 7]},
                                                                              {"weekday": 2, "periods": [5]}]}]},
                           semester="2026-2", now=NOW)
    assert view(db)["summary"]["absentCount"] == 2
    # 학기 중에 요일이 바뀌면 '그날부터' 새 판 — 지난 기록은 그대로
    res = service.save_timetable(db, {"courses": [{"courseId": "74245", "meetings": [{"weekday": 1, "periods": [1]}]}],
                                      "validFrom": "2026-10-19"}, semester="2026-2", now=NOW)
    v = view(db)
    assert len(v["timetable"]["versions"]) == 2 and v["summary"]["absentCount"] == 2 and res["generated"][0]["orphans"] == 0
    assert {s["weekday"] for s in v["sessions"] if s["date"] >= "2026-10-19" and s["kind"] == "regular"} == {1}


def test_semester_override_and_missing_f1(db):
    from attendance import config as C
    C.F1_DB.unlink()
    o = service.overview(db, "2026-2", eclass=ECLASS, now=NOW)
    assert o["semester"]["start"] is None and o["semester"]["warnings"]
    service.set_semester(db, "2026-2", {"start": "2026-09-01", "end": "2026-12-18",
                                        "holidays": [{"date": "2026-10-05", "name": "대체휴일"}]})
    service.save_timetable(db, {"courses": [{"courseId": "74245", "meetings": OS_MEETINGS}]}, semester="2026-2", now=NOW)
    sem = service.overview(db, "2026-2", now=NOW)["semester"]
    assert sem["startSource"] == "user" and any("양력 고정" in w for w in sem["warnings"])
    assert {h["date"]: h["source"] for h in sem["holidays"]} == {"2026-10-03": "fixed", "2026-10-05": "user",
                                                                 "2026-10-09": "fixed"}
    with pytest.raises(service.Invalid):
        service.set_semester(db, "2026-2", {"start": "2026-12-01", "end": "2026-09-01"})


def test_period_map_edit_changes_times(db):
    setup(db)
    service.set_period_map(db, {"mwf": {"5": ["13:10", "14:00"]}})
    s = [x for x in view(db)["sessions"] if x["weekday"] == 2][0]
    assert (s["start"], s["end"]) == ("13:10", "14:00")
    assert service.period_view(db)["edited"]
    with pytest.raises(service.Invalid):
        service.set_period_map(db, {"tt": {"1": ["10:00", "09:00"]}})
    service.set_period_map(db, None)
    assert not service.period_view(db)["edited"]


def test_calendar_events_and_today(db):
    setup(db)
    evs = service.calendar_events(db, "2026-10-01", "2026-10-11", now=NOW)
    assert all(e["extendedProps"]["kind"] == "class" for e in evs)
    mon = [e for e in evs if e["start"].startswith("2026-10-05")][0]                     # 휴강도 싣는다 (취소선)
    assert mon["extendedProps"]["state"] == "canceled" and mon["extendedProps"]["cancelSource"] == "academic"
    tue = [e for e in evs if e["start"].startswith("2026-10-06")][0]
    assert (tue["start"], tue["end"]) == ("2026-10-06T15:00:00", "2026-10-06T16:15:00") and tue["id"] == "cl:74261:2026-10-06"
    t = service.today(db, now=NOW)
    assert [c["name"] for c in t["classes"]] == ["소프트웨어공학론"]              # 10/20 화


def test_status_summary_and_warning(db):
    setup(db)
    for sid in past_ids(db)[:8]:
        service.patch_session(db, sid, {"attendance": "absent"}, now=NOW)
    st = service.status_summary(db, now=NOW)
    assert st["semester"] == "2026-2" and st["risky"][0]["name"] == "운영체제" and st["risky"][0]["level"] == "danger"
    w = service.academic_warning(db, {"lastSemesterGpa": {"value": 1.6, "scale": 4.5}})
    assert w["below"] is True and "1.75" in w["message"]
    assert service.academic_warning(db, {"lastSemesterGpa": {"value": 3.1, "scale": 4.5}})["below"] is False
    assert service.academic_warning(db, None)["below"] is None


def test_migration_from_period_ids(db):
    """v1(교시 단위 회차) 기록을 날 단위 id 로 옮기고 조퇴는 지각으로."""
    db.execute("DELETE FROM meta WHERE key = 'schema'")
    rows = [("cl:74245:2026-09-07:5-6", "absent"), ("cl:74245:2026-09-09:5", "early"),
            ("cl:mc:ab12:2026-09-12:1-2", "present"), ("cl:74245:2026-09-14", "late")]
    for i, a in rows:
        db.execute("INSERT INTO marks(id, semester, course_id, date, attendance, updated_at) VALUES (?, '2026-2', 'x', '', ?, '')",
                   (i, a))
    db.execute("INSERT INTO makeups(id, semester, course_id, date, periods, created_at) VALUES "
               "('cl:74245:2026-10-17:1-2:mk', '2026-2', '74245', '2026-10-17', '[1,2]', '')")
    store._migrate(db)
    got = dict(db.execute("SELECT id, attendance FROM marks").fetchall())
    assert got == {"cl:74245:2026-09-07": "absent", "cl:74245:2026-09-09": "late", "cl:mc:ab12:2026-09-12": "present",
                   "cl:74245:2026-09-14": "late"}
    assert [r[0] for r in db.execute("SELECT id FROM makeups")] == ["cl:74245:2026-10-17:mk"]


class FakeSearch:
    def search(self, name):
        return [{"name": name, "code": "CIS2001", "section": "2", "times": "월5월6수5", "rooms": ["공2-100"] * 3,
                 "professor": "", "campus": "광주", "credits": "3", "category": "전선"}]


def test_import_job_pipeline(db):
    service.sync_courses(db, "2026-2", ECLASS)
    targets = service.import_targets(db, "2026-2")
    db.commit()                                   # 작업은 자기 연결로 쓴다 (백엔드 스레드와 같다)
    changed = []
    jobs.on_change = lambda: changed.append(1)
    try:
        st = jobs.start_import("2026-2", targets, 3, search=FakeSearch(), background=False)
    finally:
        jobs.on_change = None
    assert st["ok"] and st["result"]["found"] == 1 and st["result"]["total"] == 2 and changed
    assert st["result"]["missing"][0]["name"] == "소프트웨어공학론"
    assert service.course_view(db, "2026-2", "74245", NOW)["timetable"]["filledBy"] == "auto"
    assert jobs.start_import("2026-2", [])["error"]
    assert notices.load()["available"]
