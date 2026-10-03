"""범위 → 분량 (F5-R10·R11) — F4 자료를 세는 규칙."""
from exams import scope


def test_all_materials_when_scope_not_given(db, materials):
    out = scope.measure("74261")
    assert out["pages"] == 145                       # 30+40+50+25 (쪽수 못 센 것·중복·없는 파일 제외)
    assert out["files"] == 5 and out["counted"] == 4 and out["noPages"] == 1
    assert out["weeks"] == [1, 2, 3, 4, 5]
    assert "쪽수를 세지 못한 1개는 빠졌습니다" in out["note"]


def test_weeks_narrow_the_scope(db, materials):
    out = scope.measure("74261", scope_weeks=[3, 4, 5])
    assert out["pages"] == 75                        # 50 + (4주는 쪽수 없음) + 25
    assert [m["week"] for m in out["materials"]] == [3, 4, 5]


def test_material_ids_win_over_weeks(db, materials):
    out = scope.measure("74261", scope_weeks=[1], material_ids=["mt:c"])
    assert out["pages"] == 50 and out["files"] == 1


def test_duplicate_and_missing_are_not_counted(db, materials):
    out = scope.measure("74261", scope_weeks=[1, 6])
    assert out["pages"] == 30                        # 사본(mt:f)도, 사라진 파일(mt:g)도 세지 않는다
    assert [m["id"] for m in out["materials"]] == ["mt:a"]


def test_empty_scope_tells_user_to_type_pages(db, materials):
    out = scope.measure("74261", scope_weeks=[12])
    assert out["pages"] == 0 and out["files"] == 0
    assert "직접 입력" in out["note"]


def test_unknown_course_is_empty(db, materials):
    out = scope.measure("74245")
    assert out["pages"] == 0 and out["materials"] == []


def test_without_f4_folder(db):
    """F4 가 없어도 F5 는 돌아간다 — 사용자가 분량을 직접 넣는다 (F5-R11)."""
    assert scope.available() is False
    assert "F4_Textbook_agent 가 없습니다" in (scope.error() or "")
    out = scope.measure("74261")
    assert out["pages"] == 0 and out["available"] is False
    assert "직접 입력" in out["note"]
