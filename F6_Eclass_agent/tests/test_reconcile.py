"""수집 결과 → 원장 반영 (F6 5절 · R22 · R23 · R32 · R34)."""
from datetime import datetime, timedelta

from conftest import NOW, assign, cal, write_data

from eclass import reconcile, service


def rows(con):
    return {r["id"]: r for r in con.execute("SELECT * FROM items")}


def changes(con, kind=None):
    q = "SELECT * FROM changes" + (" WHERE kind = ?" if kind else "") + " ORDER BY seq"
    return con.execute(q, (kind,) if kind else ()).fetchall()


def test_first_import_is_baseline_not_new(db):
    write_data([assign(1461455, "2026-10-01 23:59"), assign(1461456, "2026-10-05 18:00")])
    r = reconcile.apply(db, now=NOW)
    assert r["new"] == 2
    assert set(rows(db)) == {"dl:1461455", "dl:1461456"}
    assert all(c["notified"] == 1 for c in changes(db, "new"))       # 처음 들여온 과제는 '새 과제'로 알리지 않는다
    assert all(r["baseline"] == 1 for r in rows(db).values())


def test_same_stamp_is_skipped_unless_forced(db):
    write_data([assign(1, "2026-10-01 23:59")])
    reconcile.apply(db, now=NOW)
    assert reconcile.apply(db, now=NOW)["skipped"] is True
    assert reconcile.apply(db, now=NOW, force=True)["skipped"] is False
    assert reconcile.stale(db) is False


def test_new_item_after_baseline_is_announced(db):
    write_data([assign(1, "2026-10-01 23:59")], stamp="a")
    reconcile.apply(db, now=NOW)
    write_data([assign(1, "2026-10-01 23:59"), assign(2, "2026-10-03 23:59")], stamp="b")
    r = reconcile.apply(db, now=NOW)
    assert r["new"] == 1
    news = [c for c in changes(db, "new") if c["item_id"] == "dl:2"]
    assert news[0]["notified"] == 0
    assert rows(db)["dl:2"]["baseline"] == 0


def test_due_change_keeps_previous_and_user_values(db):
    write_data([assign(1, "2026-09-30 23:59")], stamp="a")
    reconcile.apply(db, now=NOW)
    service.patch(db, "dl:1", user_done=True, estimate_hours=2)
    write_data([assign(1, "2026-10-02 23:59")], stamp="b")
    r = reconcile.apply(db, now=NOW)
    assert r["changed"] == 1
    row = rows(db)["dl:1"]
    assert (row["due"], row["prev_due"]) == ("2026-10-02 23:59", "2026-09-30 23:59")
    assert row["changed_at"]
    assert row["user_done"] == 1 and row["estimate_hours"] == 2      # 수집이 사용자 값을 지우지 않는다 (R34)
    ch = changes(db, "due")[-1]
    assert ch["notified"] == 0
    a = service.view(row, {}, NOW)
    assert a["changed"]["before"] == "2026-09-30T23:59:00"


def test_user_check_is_promoted_when_eclass_confirms(db):
    write_data([assign(1, "2026-09-30 23:59")], stamp="a")
    reconcile.apply(db, now=NOW)
    service.patch(db, "dl:1", user_done=True)
    write_data([assign(1, "2026-09-30 23:59", submitted="제출 완료")], stamp="b")
    r = reconcile.apply(db, now=NOW)
    assert r["promoted"] == 1
    a = service.view(rows(db)["dl:1"], {}, NOW)
    assert a["submitted"] and a["promoted"]
    assert a["userDone"] is False                     # 두 표시가 겹치지 않는다 (R32)


def test_removed_assignment_is_kept_as_record(db):
    write_data([assign(1, "2026-10-01 23:59"), assign(2, "2026-10-02 23:59")], stamp="a")
    reconcile.apply(db, now=NOW)
    write_data([assign(1, "2026-10-01 23:59")], stamp="b")
    assert reconcile.apply(db, now=NOW, full=False)["removed"] == 0     # 부분 수집이면 판정하지 않는다
    write_data([assign(1, "2026-10-01 23:59")], stamp="c")
    assert reconcile.apply(db, now=NOW)["removed"] == 1
    row = rows(db)["dl:2"]
    assert row["removed_at"]                          # 지우지 않고 기록을 남긴다 (R23)
    assert "dl:2" not in {e["id"] for e in service.calendar_events(db, NOW)}
    write_data([assign(1, "2026-10-01 23:59"), assign(2, "2026-10-02 23:59")], stamp="d")
    assert reconcile.apply(db, now=NOW)["restored"] == 1
    assert rows(db)["dl:2"]["removed_at"] is None


def test_calendar_item_that_passed_is_not_removed(db):
    """캘린더 '다가오는 일정'은 지난 일정을 보여 주지 않는다 → 빠졌다고 삭제로 보지 않는다."""
    write_data([], deadlines=[cal(900, "2026-09-27 23:59"), cal(901, "2026-10-02 23:59")], stamp="a")
    reconcile.apply(db, now=datetime(2026, 9, 26, 12, 0))
    write_data([], deadlines=[], stamp="b")
    r = reconcile.apply(db, now=NOW)
    assert r["removed"] == 1                          # 901 은 가까운 미래인데 빠졌다 → 삭제
    assert rows(db)["dl:900"]["removed_at"] is None   # 900 은 이미 지났다 → 그대로


def test_dropped_course_removes_its_items(db):
    write_data([assign(1, "2026-10-01 23:59", course=0), assign(2, "2026-10-01 23:59", course=1)], stamp="a")
    reconcile.apply(db, now=NOW)
    from conftest import COURSES
    write_data([assign(2, "2026-10-01 23:59", course=1)], stamp="b", courses=[COURSES[1]])
    assert reconcile.apply(db, now=NOW)["removed"] == 1
    assert rows(db)["dl:1"]["removed_at"]


def test_assignment_without_due_listed_but_not_on_calendar(db):
    write_data([assign(1, ""), assign(2, "2026-10-01 23:59")])
    reconcile.apply(db, now=NOW)
    assert {e["id"] for e in service.calendar_events(db, NOW)} == {"dl:2"}
    assert {a["id"] for a in service.list_assignments(db, now=NOW)["items"]} == {"dl:1", "dl:2"}


def test_calendar_and_assign_merge_into_one(db):
    a = assign(5, "2026-10-01 23:59", desc="실습 안내", attachments=["data\\x\\과제\\안내.pdf"])
    c = {**cal(5, "2026-10-01 23:59", mod="assign", course=1), "type": "과제"}
    write_data([a], deadlines=[c])
    reconcile.apply(db, now=NOW)
    r = rows(db)
    assert list(r) == ["dl:5"]
    assert r["dl:5"]["description"] == "실습 안내"
    v = service.view(r["dl:5"], {}, NOW)
    assert v["attachments"] == [{"name": "안내.pdf", "path": "data\\x\\과제\\안내.pdf"}]


def test_old_json_is_normalized(db):
    """예전 수집기가 남긴 '2026-10-5 00:00' · 줄인 과목 이름도 원장에는 정식 값으로 들어간다."""
    a = assign(7, "2026-10-5 00:00")
    c = {**cal(7, "2026-10-5 00:00", mod="assign", course=1), "course": "산학협력프로젝트(캡스톤디자인)", "course_id": ""}
    write_data([a], deadlines=[c])
    reconcile.apply(db, now=NOW)
    r = rows(db)["dl:7"]
    assert (r["due"], r["course"], r["course_id"], r["source"]) == ("2026-10-05 00:00", a["course"], a["course_id"], "assign")


def test_types_and_ids():
    assert reconcile.type_of("vod", "", "calendar") == "동영상"
    assert reconcile.type_of("quiz", "", "calendar") == "퀴즈"
    assert reconcile.type_of("", "과제", "assign") == "과제"
    assert reconcile.item_id({"url": "https://sel.jnu.ac.kr/mod/quiz/view.php?id=77"}) == "dl:77"
    assert reconcile.item_id({"url": "https://sel.jnu.ac.kr/calendar/view.php?view=day#e1", "course": "a", "name": "b"}).startswith("dl:e")
    assert reconcile.is_submitted("제출 완료") and not reconcile.is_submitted("제출 안 함")
    assert not reconcile.is_submitted("미제출") and not reconcile.is_submitted("")


def test_legacy_id_matches_old_dashboard():
    """예전 eclass_data._deadline_id 와 같은 값 — 브라우저에 남은 체크를 옮길 수 있어야 한다."""
    import hashlib
    url, course, name, due = "https://sel.jnu.ac.kr/mod/assign/view.php?id=1", "과목", "과제", "2026-09-16 16:00"
    old = "dl:" + hashlib.sha1(f"{url}|{course}|{name}|{due}".encode("utf-8")).hexdigest()[:10]
    assert reconcile.legacy_id(url, course, name, due) == old


def test_migrate_legacy_values(db):
    a = assign(1, "2026-10-01 23:59")
    write_data([a, assign(2, "2026-10-02 23:59")])
    reconcile.apply(db, now=NOW)
    old = reconcile.legacy_id(a["url"], a["course"], a["name"], a["due"])
    out = service.migrate_legacy(db, {old: True, "dl:zzz": True}, {"dl:2": 3, old: 1.5})
    assert out == {"userDone": 1, "estimates": 2, "unmatched": 1}
    r = rows(db)
    assert r["dl:1"]["user_done"] == 1 and r["dl:1"]["estimate_hours"] == 1.5 and r["dl:2"]["estimate_hours"] == 3
    out2 = service.migrate_legacy(db, {}, {"dl:2": 8})
    assert out2["estimates"] == 0                     # 서버에 이미 값이 있으면 서버가 이긴다


def test_tabs_and_patch_validation(db):
    write_data([assign(1, "2026-09-27 23:59"), assign(2, "2026-10-02 23:59"), assign(3, "2026-10-03 23:59", submitted="제출 완료")])
    reconcile.apply(db, now=NOW)
    out = service.list_assignments(db, now=NOW)
    assert out["counts"] == {"open": 1, "done": 1, "past": 1}
    service.patch(db, "dl:1", user_done=True)
    assert service.list_assignments(db, now=NOW)["counts"] == {"open": 1, "done": 2, "past": 0}
    service.patch(db, "dl:1", user_done=False)        # 언제든 해제 (R33)
    assert service.list_assignments(db, "past", now=NOW)["items"][0]["id"] == "dl:1"
    import pytest
    with pytest.raises(service.Invalid):
        service.patch(db, "dl:2", estimate_hours=0)
    with pytest.raises(service.NotFound):
        service.patch(db, "dl:nope", user_done=True)
    assert service.patch(db, "dl:2", estimate_hours=None)["estimateHours"] is None


def test_is_new_flag(db):
    write_data([assign(1, "2026-10-01 23:59")], stamp="a")
    reconcile.apply(db, now=NOW - timedelta(days=2))
    write_data([assign(1, "2026-10-01 23:59"), assign(2, "2026-10-02 23:59")], stamp="b")
    reconcile.apply(db, now=NOW)
    items = {a["id"]: a for a in service.list_assignments(db, now=NOW + timedelta(hours=1))["items"]}
    assert items["dl:2"]["isNew"] and not items["dl:1"]["isNew"]


def test_midnight_deadline_drawn_on_previous_day(db):
    """'10월 4일 자정까지'(= 10/5 00:00) 는 캘린더에서 10/4 칸 — 23:30~24:00 로 그린다. 실제 마감 값은 그대로.
    23:59 마감도 끝을 정해 준다 — 끝이 없으면 FullCalendar 가 1시간을 붙여 다음 날 00:59 까지 막대가 걸쳤다(2026-10-08)."""
    write_data([assign(1, "2026-10-05 00:00"), assign(2, "2026-10-05 23:59"), assign(3, "2026-10-06 00:10")])
    reconcile.apply(db, now=NOW)
    ev = {e["id"]: e for e in service.calendar_events(db, NOW)}
    assert (ev["dl:1"]["start"], ev["dl:1"]["end"]) == ("2026-10-04T23:30:00", "2026-10-05T00:00:00")
    assert ev["dl:1"]["extendedProps"]["due"] == "2026-10-05T00:00:00"
    assert (ev["dl:2"]["start"], ev["dl:2"]["end"]) == ("2026-10-05T23:29:00", "2026-10-05T23:59:00")
    assert (ev["dl:3"]["start"], ev["dl:3"]["end"]) == ("2026-10-06T00:00:00", "2026-10-06T00:10:00")   # 전날 칸에 걸치지 않게
    for e in ev.values():                                   # 어떤 마감도 끝이 비거나 다음 날로 넘어가지 않는다
        assert e["end"] and e["end"][:10] in (e["start"][:10], e["extendedProps"]["due"][:10])


def test_video_deadline_and_watched(db):
    """동영상은 출석인정 마감만 (시작 없음), 시청 완료면 과제의 제출 완료처럼 완료로 (2026-10-02 요청)."""
    v = {**cal(1445823, "2026-10-04 23:59", mod="vod", course=0), "source": "vod", "status": "미시청 · 진도율 36%",
         "description": "출석인정 요구시간 12:17 / 콘텐츠 길이 13:40 · 진도율 36%"}
    write_data([], deadlines=[v], stamp="a")
    reconcile.apply(db, now=NOW)
    ev = {e["id"]: e for e in service.calendar_events(db, NOW)}["dl:1445823"]
    assert (ev["start"], ev["end"], ev["extendedProps"]["type"], ev["extendedProps"]["submitted"]) == (
        "2026-10-04T23:29:00", "2026-10-04T23:59:00", "동영상", False)
    assert "요구시간" in ev["extendedProps"]["description"]
    write_data([], deadlines=[{**v, "status": "시청 완료"}], stamp="b")
    assert reconcile.apply(db, now=NOW)["submitted"] == 1
    assert service.list_assignments(db, now=NOW)["counts"]["done"] == 1
    write_data([], deadlines=[], stamp="c")
    assert reconcile.apply(db, now=NOW)["removed"] == 1                 # 과목 화면에서 사라진 동영상
