"""발표는 '준비 완료'만 (2026-10-06 사용자 요청) — 공부 계획·자료 체크·진도 그래프 없이 버튼 하나."""
import pytest

from exams import service, store

from conftest import TODAY, add_exam, courses  # noqa: E402


def presentation(con):
    return add_exam(con, when="2026-10-20", etype="presentation", title="기획서 발표", time="16:00")


def test_presentation_is_prep_only(db, materials):
    e = presentation(db)
    assert e["prepOnly"] is True and e["ready"] is False and e["readyAt"] is None
    card = next(x for x in service.overview(db, courses, today=TODAY)["exams"] if x["id"] == e["id"])
    assert card["prepOnly"] and "study" not in card                 # 진도 그래프가 없다
    mid = add_exam(db)
    assert mid["prepOnly"] is False


def test_ready_toggle(db):
    e = presentation(db)
    before = dict(store.exam(db, e["id"]))
    out = service.set_ready(db, e["id"], {"ready": True}, courses, TODAY)
    assert out["ready"] is True and out["readyAt"]
    after = dict(store.exam(db, e["id"]))
    # 날짜를 고친 게 아니다 — edited·source 를 건드리지 않아 공지가 계속 갱신한다
    assert {k: v for k, v in after.items() if k != "ready_at"} == {k: v for k, v in before.items() if k != "ready_at"}
    out = service.set_ready(db, e["id"], {"ready": False}, courses, TODAY)
    assert out["ready"] is False and out["readyAt"] is None


def test_ready_survives_notice_update(db):
    """공지에서 발표 날짜·장소가 바뀌어도 준비 완료는 그대로."""
    e = presentation(db)
    service.set_ready(db, e["id"], {"ready": True}, courses, TODAY)
    store.upsert_exam(db, {"id": e["id"], "place": "공학관 101호", "time": "15:00"})
    assert store.exam(db, e["id"])["ready_at"]


def test_no_study_features_for_presentation(db, materials):
    e = presentation(db)
    with pytest.raises(service.Invalid, match="준비 완료"):
        service.preview(db, e["id"], {"totalPages": 10}, TODAY, courses)
    with pytest.raises(service.Invalid):
        service.create_plan(db, e["id"], {"totalPages": 10}, TODAY, courses)
    with pytest.raises(service.Invalid):
        service.study_materials(db, e["id"], courses, TODAY)
    with pytest.raises(service.Invalid):
        service.set_study_materials(db, e["id"], {"ids": ["mt:a"], "done": True}, courses, TODAY)


def test_ready_is_only_for_presentations(db):
    mid = add_exam(db)
    with pytest.raises(service.Invalid, match="발표에만"):
        service.set_ready(db, mid["id"], {"ready": True}, courses, TODAY)
    e = presentation(db)
    with pytest.raises(service.Invalid):
        service.set_ready(db, e["id"], {"ready": "yes"}, courses, TODAY)


def test_study_calendar_marks_ready(db):
    e = presentation(db)
    service.set_ready(db, e["id"], {"ready": True}, courses, TODAY)
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)
    x = next(x for d in cal["days"] for x in d["exams"] if x["examId"] == e["id"])
    assert x["prepOnly"] and x["ready"]
