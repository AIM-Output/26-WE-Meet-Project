"""저녁 시간대(계획 전용) · 공부 캘린더 차례 배치 · F8 공강 공부 섞기 · 공강 공부 대상 (2026-10-07)."""
import pytest

from exams import service

from conftest import TODAY, add_exam, courses  # noqa: E402


def plan_for(con, exam_id, **options):
    o = {"totalPages": 120, "studyDays": 3, "reviewDays": 1}
    o.update(options)
    return service.create_plan(con, exam_id, o, TODAY, courses)


def day_blocks(db, d, **kw):
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY, **kw)
    return next((x for x in cal["days"] if x["date"] == d), {"blocks": []})["blocks"], cal


def test_evening_default_and_saving(db):
    v = service.evening_view(db)
    assert (v["start"], v["end"], v["changed"]) == ("19:00", "24:00", False)
    v = service.set_evening(db, {"start": "20:00"})
    assert (v["start"], v["end"], v["changed"]) == ("20:00", "24:00", True)
    assert service.set_evening(db, {"start": None})["changed"] is False       # null = 기본값 (저장하지 않는다)


@pytest.mark.parametrize("body", [{"start": "16:00"}, {"start": "23:45"}, {"end": "24:30"}, {"start": "7pm"}, {"x": 1}])
def test_evening_invalid(db, body):
    with pytest.raises(service.Invalid):
        service.set_evening(db, body)


def test_plan_blocks_line_up_in_the_evening(db):
    """같은 날 두 과목 — 시험이 가까운 과목부터 19:00 에 이어서 놓인다 (모두 19:00 에 겹치지 않게)."""
    a = add_exam(db, when="2026-10-20", course="74261")
    b = add_exam(db, when="2026-10-23", course="74245")
    plan_for(db, a["id"])
    plan_for(db, b["id"], studyDays=None, studyDates=["2026-10-15", "2026-10-17", "2026-10-18"])
    blocks, cal = day_blocks(db, "2026-10-17")                 # 두 계획이 겹치는 날
    assert cal["evening"] == {"start": "19:00", "end": "24:00"}
    assert [b["time"] for b in blocks][0] == "19:00"
    first, second = blocks
    assert first["examDate"] <= second["examDate"]
    assert second["time"] == first["endTime"]


def test_evening_setting_moves_blocks(db):
    e = add_exam(db)
    plan_for(db, e["id"])
    service.set_evening(db, {"start": "20:30"})
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)
    assert {b["time"] for d in cal["days"] for b in d["blocks"]} == {"20:30"}


def test_long_day_is_cut_at_midnight_without_warning(db):
    e = add_exam(db)
    plan_for(db, e["id"], totalPages=900, studyDays=1)
    blocks, _ = day_blocks(db, "2026-10-21")
    assert blocks[0]["time"] == "19:00" and blocks[0]["endTime"] == "24:00" and blocks[0]["late"] is True


def test_f8_gap_blocks_are_merged_by_time(db):
    """F8 공강 공부(09~18시)가 같은 날 칸에 시각 순으로 — 합계에도 들어간다."""
    e = add_exam(db)
    plan_for(db, e["id"])

    def extra(start, end):
        return [{"blockId": "pb:7", "date": "2026-10-21", "time": "10:00", "endTime": "11:00", "minutes": 60,
                 "examId": e["id"], "course": "운영체제", "color": "#111", "examType": "중간고사",
                 "examDate": "2026-10-23", "done": False, "editable": True, "deletable": True, "text": "운영체제 공강 공부"}]

    blocks, _ = day_blocks(db, "2026-10-21", extra=extra)
    assert [b["kind"] for b in blocks] == ["gap", "study"]
    assert blocks[0]["source"] == "gap" and blocks[0]["pages"] == 0
    cal = service.study_calendar(db, "2026-10-21", "2026-10-21", courses, TODAY, extra=extra)
    assert cal["days"][0]["totalMinutes"] == sum(b["minutes"] for b in blocks)


def test_extra_failure_keeps_plan_blocks(db):
    e = add_exam(db)
    plan_for(db, e["id"])

    def broken(start, end):
        raise RuntimeError("F8 없음")

    blocks, _ = day_blocks(db, "2026-10-21", extra=broken)
    assert blocks and all(b["source"] == "plan" for b in blocks)


def test_study_targets(db):
    """공강 공부 대상 — 30일 안의 시험, 발표는 빼고, 남은 진도율 재료(percent)를 준다."""
    near = add_exam(db, when="2026-10-23", course="74261")
    add_exam(db, when="2026-10-20", course="74245", etype="presentation")
    add_exam(db, when="2026-12-15", course="74261", etype="final")
    t = service.study_targets(db, courses, TODAY)
    ids = [x["examId"] for x in t if x["courseName"]]
    assert near["id"] in ids
    assert all(x["type"] != "presentation" for x in t)
    assert all(x["date"] <= "2026-11-12" for x in t)
    one = next(x for x in t if x["examId"] == near["id"])
    assert one["percent"] == 0 and one["dday"] == 10 and one["href"] == f"/exams?exam={near['id']}"
    assert service.study_targets(db, courses, TODAY, with_progress=False)[0]["percent"] is None
