"""사용자 조작 — 가져오기(내 지정 보존) · 직접 입력 · 구분 지정 · 룰셋 내 수정본 · 인증 · 계획."""
import pytest

from graduation import service

FETCHED = [
    {"year": 2021, "semester": "1", "rawCategory": "교필", "code": "CLT0082", "name": "수학1", "grade": "B+", "credits": 3},
    {"year": 2021, "semester": "2", "rawCategory": "전기", "code": "ENG1003", "name": "공학수학1", "grade": "A0", "credits": 3},
    {"year": 2022, "semester": "하계 계절", "rawCategory": "교선", "code": "CLT1234", "name": "생활영어1", "grade": "P",
     "credits": 2},
]


def ids(con):
    return {c["name"]: c["id"] for c in service.load_courses(con)}


def test_import_replaces_hakstd_rows_but_keeps_overrides_and_manual(db, profile):
    service.apply_import(db, FETCHED)
    keys = service.area_keys(db, profile)
    cid = ids(db)["공학수학1"]
    service.patch_course(db, cid, {"area": "major_elective"}, keys)
    service.patch_course(db, ids(db)["수학1"], {"excluded": True}, keys)
    service.add_manual(db, {"name": "교내 AI 캠프(학점인정)", "credits": 2, "year": 2023, "semester": "1", "area": "free"}, keys)
    res = service.apply_import(db, FETCHED + [{"year": 2023, "semester": "1", "rawCategory": "전필", "code": "CIS3001",
                                               "name": "자료구조", "grade": "A0", "credits": 3}])
    assert res["count"] == 4 and res["added"] == 1 and res["removed"] == 0
    s = service.status(db, profile)
    by = {c["name"]: c for c in s["courses"]}
    assert by["공학수학1"]["area"] == "major_elective" and by["공학수학1"]["areaSetBy"] == "user"
    assert by["수학1"]["excluded"] and by["수학1"]["excludedReason"] == "직접 제외함"
    assert by["교내 AI 캠프(학점인정)"]["source"] == "manual"
    assert by["생활영어1"]["semester"] == "여름"                              # '하계 계절' → 여름
    assert s["data"]["hakstdCount"] == 4 and s["data"]["manualCount"] == 1


def test_apply_to_category_maps_all_courses_with_that_raw(db, profile):
    service.apply_import(db, FETCHED + [{"year": 2022, "semester": "1", "rawCategory": "전기", "code": "MTH2010",
                                         "name": "이산수학", "grade": "B0", "credits": 3}])
    keys = service.area_keys(db, profile)
    assert len(service.status(db, profile)["unmapped"]) == 2
    res = service.patch_course(db, ids(db)["공학수학1"], {"area": "major_elective", "applyToCategory": True}, keys)
    assert res["mapped"] == {"raw": "전기", "area": "major_elective"}
    s = service.status(db, profile)
    assert s["unmapped"] == []
    assert {c["areaSetBy"] for c in s["courses"] if c["rawCategory"] == "전기"} == {"map"}
    rows = {r["raw"]: r for r in service.category_view(db, profile)["rows"]}
    assert rows["전기"]["mine"] == "major_elective" and rows["전기"]["courses"] == 2


def test_hakstd_course_cannot_be_deleted_or_edited(db, profile):
    service.apply_import(db, FETCHED)
    cid = ids(db)["수학1"]
    with pytest.raises(service.Conflict):
        service.delete_course(db, cid)
    with pytest.raises(service.Conflict):
        service.patch_course(db, cid, {"credits": 4}, service.area_keys(db, profile))


def test_manual_course_validation_and_delete(db, profile):
    keys = service.area_keys(db, profile)
    with pytest.raises(service.Invalid):
        service.add_manual(db, {"name": "", "credits": 3}, keys)
    with pytest.raises(service.Invalid):
        service.add_manual(db, {"name": "x", "credits": 3, "area": "nope"}, keys)
    cid = service.add_manual(db, {"name": "편입 인정 학점", "credits": 30, "semester": "겨울", "area": "free"}, keys)
    service.patch_course(db, cid, {"credits": 27, "memo": "편입"}, keys)
    c = next(c for c in service.load_courses(db) if c["id"] == cid)
    assert c["credits"] == 27 and c["memo"] == "편입"
    service.delete_course(db, cid)
    assert service.load_courses(db) == []


def test_ruleset_user_copy_takes_priority_and_can_be_reset(db, profile):
    p = dict(profile, admissionYear=2024)
    v = service.ruleset_view(db, p)
    assert v["level"] == "nearest" and not v["edited"]
    doc = dict(v["editable"], totalCredits=130)
    saved = service.save_ruleset(db, p, {"ruleset": doc})
    assert saved["level"] == "user" and saved["edited"] and saved["ruleset"]["totalCredits"] == 130
    assert saved["base"]["id"] == "jnu:30001265:2021:single"
    s = service.status(db, p)
    assert s["ruleset"]["level"] == "user" and s["total"]["required"] == 130 and not s["ruleset"]["warnings"]
    # 과목 목록은 여전히 교육과정에서 (저장본에 coursesFrom 이 남아 있다)
    assert len(next(a for a in s["areas"] if a["key"] == "major_required")["requiredCourses"]) == 5
    back = service.reset_ruleset(db, p)
    assert back["level"] == "nearest" and not back["edited"]


def test_ruleset_save_needs_profile(db):
    with pytest.raises(service.Invalid, match="학과"):
        service.save_ruleset(db, None, {"ruleset": {"areas": [{"key": "a"}]}})


def test_no_ruleset_gives_template(db):
    p = {"deptCode": "30000150", "department": "컴퓨터공학과", "admissionYear": 2023, "track": "single"}
    v = service.ruleset_view(db, p)
    assert v["level"] == "none" and v["isTemplate"] and v["editable"]["deptCode"] == "30000150"
    assert v["similar"][0]["id"] == "jnu:30001265:2021:single"
    s = service.status(db, p)
    assert s["verdict"] == "확인 필요" and s["ruleset"]["areas"]                 # 룰셋이 없어도 멈추지 않는다


def test_certs_and_plans(db, profile):
    service.set_cert(db, "foreign_language", {"state": "done", "memo": "TOEIC 780 (2025-04)"})
    s = service.status(db, profile)
    fl = next(c for c in s["certifications"] if c["key"] == "foreign_language")
    assert fl["state"] == "done" and fl["memo"].startswith("TOEIC")
    with pytest.raises(service.Invalid):
        service.set_cert(db, "thesis", {"state": "maybe"})
    plan = service.save_plan(db, {"name": "2학기", "assumptions": {"areas": {"major_elective": 6}}})
    assert service.plans(db)[0]["id"] == plan["id"]
    service.delete_plan(db, plan["id"])
    assert service.plans(db) == []


def test_simulate_returns_current_and_assumed(db, profile):
    service.apply_import(db, FETCHED)
    r = service.simulate(db, profile, None, {"areas": {"major_elective": 6}})
    assert r["assumed"]["total"]["earned"] == r["current"]["total"]["earned"] + 6
    with pytest.raises(service.Invalid):
        service.simulate(db, profile, None, {"areas": {"major_elective": 999}})


def test_summary_for_tile(db, profile):
    service.apply_import(db, FETCHED)
    s = service.summary(db, profile)
    assert s["hasData"] and s["required"] == 140 and s["remaining"] == 132
    assert s["unmapped"] == 1                                                 # '전기'


def test_clear_all(db, profile):
    service.apply_import(db, FETCHED)
    service.set_cert(db, "thesis", {"state": "done"})
    service.clear_all(db)
    assert service.load_courses(db) == [] and service.cert_states(db) == {}
