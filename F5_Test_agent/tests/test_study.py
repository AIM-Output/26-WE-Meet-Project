"""공부 완료 체크 (2026-10-06 사용자 요청) — 서비스 밖에서 공부한 강의자료를 체크하면
과목 카드의 진도 그래프에 들어가고, 계획 만들기의 남은 분량에서 빠진다.

conftest 의 `materials` = 소프트웨어공학론(74261) 1~5강: 30 · 40 · 50 · (못 셈) · 25쪽 = 145쪽
"""
import pytest

from exams import scope, service, store

from conftest import TODAY, _m, add_exam, courses  # noqa: E402


def check(con, exam_id, ids, done=True):
    return service.set_study_materials(con, exam_id, {"ids": ids, "done": done}, courses, TODAY)


# ---------------------------------------------------------------- 범위 (scope)

def test_checked_pages_leave_the_remaining_amount(db, materials):
    out = scope.measure("74261", done={"mt:a": "2026-10-10T20:00:00", "mt:c": "2026-10-11T20:00:00"})
    assert out["scopePages"] == 145 and out["donePages"] == 80 and out["pages"] == 65
    assert out["doneFiles"] == 2
    assert [m["done"] for m in out["materials"]] == [True, False, True, False, False]
    assert "공부 완료 2개 80쪽 빼고 65쪽" in out["note"]


def test_no_scope_means_all_lecture_materials(db, materials):
    """공지에 범위가 없는 시험 = 지금까지 e클래스에 올라온 강의자료 전체."""
    out = scope.measure("74261")
    assert out["basis"] == "all" and out["label"] == "e클래스 강의자료 전체"
    assert scope.measure("74261", scope_weeks=[3, 4, 5])["label"] == "3~5주차"
    assert scope.measure("74261", scope_weeks=[1, 3])["label"] == "1·3주차"
    assert scope.measure("74261", material_ids=["mt:a"])["label"] == "고른 자료 1개"


def test_assignment_attachments_are_not_study_material(db, materials):
    """과제 첨부(제출 양식·샘플)는 범위에 넣지 않는다 — 실측: 산학협력 제안서 양식."""
    materials.append({**_m("mt:x", "프로젝트 제안서 양식.docx", week=None, pages=3), "kind": "assignment"})
    out = scope.measure("74261")
    assert "mt:x" not in [m["id"] for m in out["materials"]]
    assert out["pages"] == 145
    assert "mt:x" not in [m["id"] for m in scope.materials("74261")]


# ---------------------------------------------------------------- 체크 → 카드 · 계획

def test_check_shows_on_card_and_shrinks_plan_amount(db, materials):
    e = add_exam(db)
    before = service.default_options(db, store.exam(db, e["id"]), TODAY)
    assert before["totalPages"] == 145

    out = check(db, e["id"], ["mt:a", "mt:b"])
    assert out["changed"] == 2
    st = out["exam"]["study"]
    assert st == {"unit": "pages", "total": 145, "checked": 70, "planned": 0, "done": 70, "remaining": 75,
                  "percent": 48, "files": 5, "doneFiles": 2}
    assert out["exam"]["scope"]["label"] == "e클래스 강의자료 전체"
    assert [m["id"] for m in out["materials"] if m["done"]] == ["mt:a", "mt:b"]

    # 계획 만들기: 남은 분량 = 145 − 70
    after = service.default_options(db, store.exam(db, e["id"]), TODAY)
    assert after["totalPages"] == 75
    prev = service.preview(db, e["id"], {"totalPages": 0}, TODAY, courses)
    assert prev["totalPages"] == 75 and prev["scope"]["donePages"] == 70

    # 목록(/api/exams)의 카드에도 같은 값
    card = next(x for x in service.overview(db, courses, today=TODAY)["exams"] if x["id"] == e["id"])
    assert card["study"]["percent"] == 48 and card["pages"] == 75


def test_uncheck_restores(db, materials):
    e = add_exam(db)
    check(db, e["id"], ["mt:a"])
    out = check(db, e["id"], ["mt:a"], done=False)
    assert out["changed"] == 1 and out["exam"]["study"]["checked"] == 0
    assert service.default_options(db, store.exam(db, e["id"]), TODAY)["totalPages"] == 145
    assert check(db, e["id"], ["mt:a"], done=False)["changed"] == 0      # 이미 풀린 것은 그대로


def test_checks_belong_to_the_course(db, materials):
    """같은 자료를 중간·기말에서 따로 체크하지 않는다 — 과목에 한 번."""
    mid = add_exam(db)
    quiz = add_exam(db, when="2026-10-29", etype="quiz", scopeWeeks=[1, 2])
    check(db, mid["id"], ["mt:a"])
    out = service.study_materials(db, quiz["id"], courses, TODAY)
    assert out["exam"]["study"]["checked"] == 30 and out["exam"]["study"]["total"] == 70
    # 범위 밖 자료도 같이 보여 준다 (범위를 좁힌 시험에서도 체크할 수 있게)
    assert [m["id"] for m in out["others"]] == ["mt:c", "mt:d", "mt:e"]


def test_plan_progress_adds_to_checked(db, materials):
    """진도 그래프 = 체크한 자료 + 계획에서 완료한 블록 (계획은 체크하고 남은 분량으로 만든다)."""
    e = add_exam(db)
    check(db, e["id"], ["mt:a"])                                         # 30쪽
    made = service.create_plan(db, e["id"], {"totalPages": 0, "reviewDays": 1, "studyDays": 3}, TODAY, courses)
    assert made["plan"]["totalPages"] == 115
    first = made["plan"]["days"][0]
    service.patch_day(db, made["plan"]["planId"], first["date"], {"done": True}, TODAY, courses)
    st = service.study_materials(db, e["id"], courses, TODAY)["exam"]["study"]
    assert st["checked"] == 30 and st["planned"] == first["pages"]
    assert st["done"] == 30 + first["pages"] and st["total"] == 145


def test_check_after_plan_suggests_replanning(db, materials):
    """등록된 계획은 저절로 바뀌지 않는다 — 남은 분량이 달라졌다고 알리고, 다시 만들면 새 분량으로."""
    e = add_exam(db)
    made = service.create_plan(db, e["id"], {"totalPages": 0, "reviewDays": 1}, TODAY, courses)
    assert made["plan"]["totalPages"] == 145
    out = check(db, e["id"], ["mt:c"])
    assert out["planStale"] and "145쪽 → 95쪽" in out["planStale"]["message"]
    assert store.active_plan(db, e["id"])["total_pages"] == 145
    assert service.default_options(db, store.exam(db, e["id"]), TODAY)["totalPages"] == 95


def test_typed_amount_is_kept_on_replan(db, materials):
    """사용자가 쪽수를 직접 넣은 계획은 체크해도 그 값을 그대로 물려준다."""
    e = add_exam(db)
    service.create_plan(db, e["id"], {"totalPages": 60, "reviewDays": 1}, TODAY, courses)
    check(db, e["id"], ["mt:c"])
    assert service.default_options(db, store.exam(db, e["id"]), TODAY)["totalPages"] == 60


def test_files_when_pages_unknown(db, monkeypatch):
    """쪽수를 하나도 못 센 과목(.ppt 뿐) — 자료 개수로 잰다 (실측: 컴퓨터그래픽스)."""
    rows = [_m("pp:1", "Week2.ppt", week=2, pages=None), _m("pp:2", "Week3.ppt", week=3, pages=None)]
    monkeypatch.setattr(scope, "_rows", lambda cid: list(rows) if cid == "74261" else [])
    monkeypatch.setattr(scope, "available", lambda: True)
    e = add_exam(db)
    st = check(db, e["id"], ["pp:1"])["exam"]["study"]
    assert st["unit"] == "files" and st["total"] == 2 and st["done"] == 1 and st["percent"] == 50


def test_bad_requests(db, materials):
    e = add_exam(db)
    with pytest.raises(service.NotFound):
        check(db, e["id"], ["mt:zz"])                                    # 이 과목 자료가 아니다
    with pytest.raises(service.NotFound):
        check(db, e["id"], ["mt:f"])                                     # 중복 자료는 체크 대상이 아니다
    with pytest.raises(service.Invalid):
        service.set_study_materials(db, e["id"], {"ids": [], "done": True}, courses, TODAY)
    with pytest.raises(service.Invalid):
        service.set_study_materials(db, e["id"], {"ids": ["mt:a"], "done": "yes"}, courses, TODAY)
    with pytest.raises(service.NotFound):
        service.study_materials(db, "ex:nope:1", courses, TODAY)


def test_files_when_most_pages_unknown(db, monkeypatch):
    """쪽수를 못 센 자료가 절반 이상이면 자료 개수로 — 실측: 컴퓨터그래픽스 .pptx 1개(9쪽) + .ppt 6개."""
    rows = [_m("cg:1", "Week1.pptx", week=1, pages=9)] + [_m(f"cg:{i}", f"Week{i}.ppt", week=i, pages=None)
                                                        for i in range(2, 5)]
    monkeypatch.setattr(scope, "_rows", lambda cid: list(rows) if cid == "74261" else [])
    monkeypatch.setattr(scope, "available", lambda: True)
    e = add_exam(db)
    st = check(db, e["id"], ["cg:2", "cg:3"])["exam"]["study"]
    assert st["unit"] == "files" and st["total"] == 4 and st["done"] == 2 and st["percent"] == 50
