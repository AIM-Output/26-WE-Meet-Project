"""미리보기 · 등록 · 캘린더 · 충돌 · 옮기기 · 지우기 · 공부 캘린더 연동 — F8-R20~R34 (2026-10-07 개정)."""
import sqlite3
from datetime import datetime

import pytest

from conftest import NOW, THU, TUE, WED, cls, ev, exam, task, todo, tuesday_classes
from placement import config as C
from placement import service, settings as S, store

FRI = "2026-10-02"


def inputs():
    events = tuesday_classes() + tuesday_classes(WED) + [todo(5, WED, "서류 내기")]
    items = [task("dl:4", "품질 보고서", f"{THU}T18:00:00", 3, slack=40)]
    exams = [exam("ex:os", "운영체제", "2026-10-08", percent=20), exam("ex:se", "소프트웨어공학론", FRI, percent=60)]
    return events, exams, items


def pv(con, now=NOW, **kw):
    ev_, ex, pr = inputs()
    return service.preview(con, ev_, ex, pr, now=now, **kw)


def reg(con, p, now=NOW, **kw):
    ev_, ex, pr = inputs()
    return service.register(con, ev_, ex, pr, p["signature"], p["at"], now=now, **kw)


def test_preview_writes_nothing(con):
    p = pv(con)
    assert p["blocks"] and store.rows(con) == []
    assert p["range"] == {"start": TUE, "end": "2026-10-05", "days": 7}
    assert p["state"] == {"timetable": True, "tasks": 2, "study": 2, "fillStudy": True, "allUnplaced": False}
    assert p["days"][0]["classes"][0] == {"start": "09:00", "end": "10:50", "title": "운영체제", "canceled": False}
    kinds = {b["taskType"] for b in p["blocks"]}
    assert kinds == {"assignment", "todo", "study"}
    assert all("09:00" <= b["start"] and b["end"] <= "18:00" for b in p["blocks"])      # 낮 공강만
    assert p["studyMinutes"] == sum(b["minutes"] for b in p["blocks"] if b["taskType"] == "study")
    # 고르는 순서 — 남은 진도율 ÷ 남은 날수: 소공 0.4÷3 = 0.133 > 운영체제 0.8÷9 = 0.089
    assert [t["examId"] for t in p["studyTargets"]] == ["ex:se", "ex:os"]


def test_study_comes_after_tasks(con):
    """과제·할 일이 먼저 자리를 잡고, 공부는 남은 공강에만 — 같은 날 과제 블록보다 앞선 공부 블록이 없다."""
    p = pv(con)
    first_task = min((b["date"], b["start"]) for b in p["blocks"] if b["taskType"] != "study")
    assert first_task == (TUE, "11:00")


def test_fill_study_setting(con):
    S.save({"fillStudy": False})
    p = pv(con)
    assert not [b for b in p["blocks"] if b["taskType"] == "study"] and p["state"]["fillStudy"] is False


def test_register_makes_calendar_study_blocks(con):
    """R21 · R24 — 등록하면 과제·할 일은 kind=study, placedBy=auto 로 전체 캘린더에. 공부 블록은 공부 캘린더에만 (F5 D7)."""
    p = pv(con)
    out = reg(con, p)
    assert out["created"] == len(p["blocks"]) and out["removed"] == 0
    assert out["studyCreated"] == sum(1 for b in p["blocks"] if b["taskType"] == "study") > 0
    evs = service.calendar_events(con, TUE, "2026-10-05")
    assert len(evs) == sum(1 for b in p["blocks"] if b["taskType"] != "study")
    e = evs[0]
    assert e["id"].startswith("pb:") and e["extendedProps"]["kind"] == "study"
    assert e["extendedProps"]["placedBy"] == "auto" and e["extendedProps"]["auto"] is True
    assert {x["extendedProps"]["taskType"] for x in evs} == {"assignment", "todo"}           # 공부는 없다
    assert len(service.study_blocks(con, TUE, "2026-10-05")) == out["studyCreated"]


def test_study_block_conflict_shows_on_study_calendar(con):
    """공부 블록은 전체 캘린더에 없으므로 충돌(겹침)은 공부 캘린더 블록에 싣는다."""
    reg(con, pv(con))
    b = next(r for r in store.rows(con) if r["task_type"] == "study")
    evs = [cls(b["date"], b["start"], b["end"], "보강")]
    sb = service.study_blocks(con, TUE, "2026-10-05", evs, None, now=NOW)
    hit = next(x for x in sb if x["blockId"] == f"pb:{b['id']}")
    assert hit["conflict"] == "보강 수업과 겹칩니다"
    assert all(e["id"] != f"pb:{b['id']}" for e in service.calendar_events(con, TUE, "2026-10-05", evs, None, now=NOW))


def test_study_blocks_for_f5_calendar(con):
    """공부 캘린더(F5)에 섞을 공강 공부 — 시험 날짜·유형이 블록에 저장돼 있다."""
    reg(con, pv(con))
    sb = service.study_blocks(con, TUE, "2026-10-05")
    assert sb and all(b["blockId"].startswith("pb:") for b in sb)
    one = next(b for b in sb if b["examId"] == "ex:se")
    assert one["examDate"] == FRI and one["examType"] == "중간고사" and one["editable"] and one["deletable"]
    assert len(sb) == sum(1 for r in store.rows(con) if r["task_type"] == "study")


def test_register_rejects_changed_data(con):
    """8절 — 미리보기 뒤 데이터가 바뀌면 다시 계산하라고 한다."""
    p = pv(con)
    ev_, ex, pr = inputs()
    with pytest.raises(service.Stale):
        service.register(con, ev_ + [ev(TUE, "11:00", "12:00", "면담")], ex, pr, p["signature"], p["at"], now=NOW)
    assert store.rows(con) == []


def test_register_uses_preview_time(con):
    """미리보기 몇 분 뒤에 눌러도(지금이 10분 단위를 넘어도) 같은 결과로 등록된다."""
    p = pv(con, now=datetime(2026, 9, 29, 10, 58))
    out = reg(con, p, now=datetime(2026, 9, 29, 11, 3))
    assert out["created"] == len(p["blocks"])


def test_register_rejects_old_preview(con):
    p = pv(con)
    with pytest.raises(service.Stale):
        reg(con, p, now=datetime(2026, 9, 29, 9, 0))


def test_reregister_replaces_only_auto_blocks(con):
    """R30 · R33 — 다시 배치하면 자동 배치분만 바뀐다. 내가 옮긴 블록·완료한 블록은 그대로."""
    reg(con, pv(con))
    rows = store.rows(con)
    moved, done = rows[0], rows[1]
    service.patch_block(con, f"pb:{moved['id']}", {"date": WED, "start": "16:00", "end": "17:00"})
    service.patch_block(con, f"pb:{done['id']}", {"done": True})
    p2 = pv(con)
    assert p2["existing"] == len(rows) - 2
    reg(con, p2)
    after = {r["id"]: r for r in store.rows(con)}
    assert after[moved["id"]]["placed_by"] == "user" and after[moved["id"]]["start"] == "16:00"
    assert after[done["id"]]["done"] == 1


def test_fixed_block_counts_and_is_busy(con):
    """고정한 블록은 다른 블록이 겹쳐 들어오지 않고, 그 작업 길이에서 빠진다."""
    reg(con, pv(con))
    todo_row = next(r for r in store.rows(con) if r["ref_id"] == "todo:5")
    service.patch_block(con, f"pb:{todo_row['id']}", {"date": TUE, "start": "16:00", "end": "16:30"})
    p2 = pv(con)
    assert all(b["refId"] != "todo:5" for b in p2["blocks"])                 # 30분 다 고정해 둠
    assert all(not (b["date"] == TUE and b["start"] < "16:30" and b["end"] > "16:00") for b in p2["blocks"])
    assert p2["kept"][0]["placedBy"] == "user"


def test_fixed_block_counts_toward_two_per_day(con):
    """R16 — 고정해 둔 같은 작업 블록도 하루 2블록에 센다."""
    reg(con, pv(con))
    rows = [r for r in store.rows(con) if r["ref_id"] == "dl:4"]
    for i, r in enumerate(rows[:2]):
        service.patch_block(con, f"pb:{r['id']}", {"date": TUE, "start": f"{15 + i}:00", "end": f"{15 + i}:30"})
    p2 = pv(con)
    assert not [b for b in p2["blocks"] if b["refId"] == "dl:4" and b["date"] == TUE]


def test_exclude_block(con):
    """R23 · S04 — 블록 하나를 빼면 그 시간만 미배치로 가고 나머지 배치는 그대로. 공부 블록은 미배치로 적지 않는다."""
    p = pv(con)
    victim = next(b for b in p["blocks"] if b["taskType"] == "assignment")
    p2 = pv(con, exclude=[victim["key"]])
    assert [b["key"] for b in p2["blocks"]] == [b["key"] for b in p["blocks"] if b["key"] != victim["key"]]
    u = [x for x in p2["unplaced"] if x["reasonKey"] == "excluded"]
    assert u and u[0]["remainingMinutes"] == victim["minutes"]
    study = next(b for b in p["blocks"] if b["taskType"] == "study")
    p3 = pv(con, exclude=[study["key"]])
    assert not [x for x in p3["unplaced"] if x["reasonKey"] == "excluded"]
    out = reg(con, p2, exclude=[victim["key"]])
    assert out["created"] == len(p["blocks"]) - 1


def test_states(con):
    """7절 상태별 화면 — 시간표 없음 · 배치할 작업 없음."""
    p = service.preview(con, [], [], [], now=NOW)
    assert p["state"] == {"timetable": False, "tasks": 0, "study": 0, "fillStudy": True, "allUnplaced": False}
    assert p["blocks"] == [] and p["adjustments"] == []


def test_todo_tasks(con):
    """종일 미완료 할 일만 — 시각이 있는 할 일은 차지된 시간, 끝낸 것·2주 넘게 지난 것은 뺀다."""
    evs = [todo(1, TUE), todo(2, TUE, done=True), ev(TUE, "15:00", "15:30", "시각 할 일", isTodo=True),
           todo(3, "2026-09-01", "아주 옛날")]
    t = service.todo_tasks(evs, [], NOW, S.load(), TUE, "2026-10-05")
    assert [x["key"] for x in t] == ["todo:1"] and t[0]["minutes"] == C.TODO_MINUTES and t[0]["href"] == "/?event=1"


def test_conflict_detected_on_calendar(con):
    """R31 · S08 — 수업이 바뀌어 겹치면 경고 한 줄."""
    reg(con, pv(con))
    b = next(r for r in store.rows(con) if r["task_type"] != "study")
    evs = [cls(b["date"], b["start"], b["end"], "보강")]
    out = service.calendar_events(con, TUE, THU, evs, None, now=NOW)
    hit = [e for e in out if e["id"] == f"pb:{b['id']}"][0]
    assert hit["extendedProps"]["conflict"] == "보강 수업과 겹칩니다"
    assert service.conflicts(con, evs, None, now=NOW)["count"] == 1


def test_academic_event_is_not_a_conflict(con):
    """학사 일정과 겹쳐도 충돌이 아니다 — 내 일정에 넣은 것과 겹치면 충돌 (2026-10-07)."""
    reg(con, pv(con))
    b = store.rows(con)[0]
    academic = ev(b["date"], b["start"], b["end"], "학사", kind="academic")
    assert service.conflicts_of(store.rows(con), [academic], None, NOW) == {}
    mine = ev(b["date"], b["start"], b["end"], "학사", origin="ac:x")
    assert service.conflicts_of(store.rows(con), [mine], None, NOW)[b["id"]] == "'학사' 일정과 겹칩니다"


def test_conflict_task_finished_and_after_due(con):
    reg(con, pv(con))
    rows = store.rows(con)
    ev_, ex, pr = inputs()
    refs = service.open_refs_of(ex, [], ev_)                                  # 과제를 끝냈다(목록에 없다)
    flags = service.conflicts_of(rows, [], refs, NOW)
    assert any(v.startswith("끝낸 과제") for v in flags.values())
    done_todo = service.open_refs_of(ex, pr, [todo(5, WED, done=True)])       # 할 일을 끝냈다
    assert any(v.startswith("끝낸 할 일") for v in service.conflicts_of(rows, [], done_todo, NOW).values())
    full = [{**x, "percent": 100} for x in ex]                                # 진도를 다 채웠다
    assert any(v.startswith("시험이 지났거나") for v in
               service.conflicts_of(rows, [], service.open_refs_of(full, pr, ev_), NOW).values())
    early = [{**x, "date": TUE, "time": "09:00"} for x in ex]                 # 시험이 앞당겨졌다
    assert any(v == "시험 뒤에 있습니다" for v in
               service.conflicts_of(rows, [], service.open_refs_of(early, pr, ev_), NOW).values())


def test_done_blocks_are_not_flagged(con):
    reg(con, pv(con))
    b = store.rows(con)[0]
    service.patch_block(con, f"pb:{b['id']}", {"done": True})
    flags = service.conflicts_of(store.rows(con), [cls(b["date"], b["start"], b["end"])], None, NOW)
    assert b["id"] not in flags


def test_move_by_calendar_drag_and_midnight(con):
    """끌어 옮기기(ISO) — 고정된다. 24:00 끝은 다음 날 00:00 으로 받는다. 자정을 넘기면 거절."""
    reg(con, pv(con))
    b = store.rows(con)[0]
    out = service.patch_block(con, f"pb:{b['id']}", {"start": f"{WED}T23:00:00", "end": f"{THU}T00:00:00"})
    assert out["fixed"] and out["block"]["end"] == "24:00" and out["block"]["minutes"] == 60
    assert out["event"]["end"] == f"{THU}T00:00:00"
    with pytest.raises(service.Invalid):
        service.patch_block(con, f"pb:{b['id']}", {"start": f"{WED}T23:00:00", "end": f"{THU}T00:30:00"})
    with pytest.raises(service.Invalid):
        service.patch_block(con, f"pb:{b['id']}", {"start": WED, "end": THU, "allDay": True})


def test_unfix_block(con):
    reg(con, pv(con))
    b = store.rows(con)[0]
    service.patch_block(con, f"pb:{b['id']}", {"date": WED, "start": "16:00", "end": "17:00"})
    assert service.patch_block(con, f"pb:{b['id']}", {"fixed": False})["fixed"] is False


def test_delete_auto_keeps_fixed_and_done(con):
    """R34 · S10 — 자동 배치 블록만 지운다."""
    reg(con, pv(con))
    rows = store.rows(con)
    service.patch_block(con, f"pb:{rows[0]['id']}", {"date": WED, "start": "16:00", "end": "17:00"})
    service.patch_block(con, f"pb:{rows[1]['id']}", {"done": True})
    out = service.delete_auto(con, TUE, "2026-10-05", now=NOW)
    assert out["deleted"] == len(rows) - 2 and out["kept"] == 2


def test_delete_one_and_not_found(con):
    reg(con, pv(con))
    b = store.rows(con)[0]
    assert service.delete_block(con, f"pb:{b['id']}") == {"deleted": 1}
    with pytest.raises(service.NotFound):
        service.delete_block(con, f"pb:{b['id']}")
    with pytest.raises(service.NotFound):
        service.patch_block(con, "abc", {"done": True})


def test_today_and_status(con):
    reg(con, pv(con))
    t = service.today(con, NOW)
    assert t["date"] == TUE and t["blocks"] and t["text"].startswith("11:00 ")
    s = service.status_summary(con, NOW)
    assert s["available"] and s["upcoming"] == len(store.rows(con)) and s["auto"] == s["upcoming"]
    assert s["updatedAt"]


def test_old_db_gets_extra_column():
    """2026-10-06 판 DB(extra 칸 없음)는 열릴 때 칸이 더해진다."""
    C.ensure_dirs()
    old = "\n".join(line for line in store.SCHEMA.splitlines() if not line.strip().startswith("extra "))
    assert "extra" not in old
    raw = sqlite3.connect(str(C.DB_PATH))
    raw.executescript(old)
    raw.close()
    with store.connect() as c2:
        assert "extra" in {r["name"] for r in c2.execute("PRAGMA table_info(blocks)")}


def test_range_validation(con):
    with pytest.raises(service.Invalid):
        service.preview(con, [], [], [], now=NOW, range_days=3)
    assert service.preview(con, [], [], [], now=NOW, range_days=14)["range"]["days"] == 14


def test_event_prefix():
    assert C.EVENT_PREFIX == "pb:" and service.parse_id("pb:12") == 12
