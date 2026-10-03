"""프로필 저장 — 검사 · 소속(마스터 코드) · 자동/내가 입력 · 가져오기 · 민감정보 · 다른 기능용 모양 · 옛 데이터 옮기기."""
import pytest

from student import notice_bridge, service
from student.hakstd import parse_dashboard, parse_grades
from student.schema import Invalid

AFF = {"affiliation": {"deptCode": "30001265", "majorCode": "30001267"}}


def test_required_and_affiliation(db):
    doc = service.get(db)
    assert not doc["exists"] and doc["missing"] == ["deptCode", "admissionYear", "track"]
    service.patch(db, {**AFF, "admissionYear": 2024, "track": "single"})
    doc = service.get(db)
    p = doc["profile"]
    assert doc["complete"] and p["deptPath"] == "AI융합대학 › 인공지능학부 › 인공지능전공"
    assert (p["collegeCode"], p["department"], p["major"]) == ("30001229", "인공지능학부", "인공지능전공")
    assert doc["filledBy"]["deptCode"] == "user"


@pytest.mark.parametrize("bad", [
    {"name": "홍길동"}, {"studentId": "2024"},                         # 식별정보 (C2-D5)
    {"affiliation": {"deptCode": "12345678"}},                       # 마스터에 없는 코드 (C2-D1)
    {"affiliation": "인공지능학부"},                                   # 자유 입력 금지
    {"grade": 9}, {"track": "triple"}, {"enrollmentStatus": "재적"},
    {"gpa": {"value": 4.7, "scale": 4.5}}, {"residenceRegion": "경기도 수원"},
    {"flags": {"rich": True}}, {"unknownField": 1},
])
def test_rejects(db, bad):
    with pytest.raises(Invalid):
        service.patch(db, bad)
    assert not service.get(db)["exists"]


def test_auto_vs_user(db):
    service.patch(db, {"grade": 2}, by="user")
    res = service.patch(db, {"grade": 3, "earnedCredits": 98}, by="auto")       # 사용자 값은 덮지 않는다 (C2-R05)
    assert res == {"changed": ["earnedCredits"], "skipped": ["grade"]}
    service.patch(db, {"earnedCredits": 101}, by="user")                        # 자동값을 고치면 '수정함'
    doc = service.get(db)
    assert doc["profile"]["grade"] == 2 and doc["filledBy"]["earnedCredits"] == "user"
    assert "earnedCredits" in doc["edited"] and "grade" not in doc["edited"]
    service.patch(db, {"grade": None})                                          # null = 지우기
    assert service.get(db)["profile"]["grade"] is None


def test_apply_import(db):
    fetched = {"grade": 3, "enrollment_status": "재학", "college": "AI융합대학", "department": "인공지능학부",
               "gpa": {"value": 3.42, "scale": 4.5, "basis": "전체"}, "earned_credits": 98, "semesters_completed": 5,
               "last_semester_credits": 18}
    res = service.apply_import(db, fetched)
    doc = service.get(db)
    assert set(res["found"]) == {"grade", "enrollmentStatus", "gpa", "earnedCredits", "semestersCompleted", "lastSemesterCredits"}
    assert res["affiliationFound"] == "AI융합대학 › 인공지능학부"
    assert doc["filledBy"]["deptCode"] == "auto" and doc["profile"]["majorCode"] is None
    # 사용자가 전공을 고르고 다시 가져와도 소속은 그대로
    service.patch(db, AFF)
    res = service.apply_import(db, {**fetched, "grade": 4, "enrollment_status": "졸업"})
    doc = service.get(db)
    assert doc["profile"]["major"] == "인공지능전공" and "deptCode" in res["skipped"]
    assert doc["profile"]["grade"] == 4 and res["invalid"] == ["enrollmentStatus"]


def test_sensitive_and_matching_view(db):
    service.patch(db, {**AFF, "grade": 3, "enrollmentStatus": "재학", "incomeBracket": 4, "residenceRegion": "광주",
                       "flags": {"veteranFamily": True, "disability": False}})
    assert service.get(db)["profile"]["flags"] == {"veteranFamily": True}
    mv = service.matching_view(db)
    assert (mv["grade"], mv["enrollment"], mv["college"], mv["department"]) == (3, "재학", "AI융합대학", "인공지능학부")
    service.delete_sensitive(db)
    p = service.get(db)["profile"]
    assert p["incomeBracket"] is None and p["flags"] is None and p["grade"] == 3
    service.delete_all(db)
    assert service.matching_view(db) is None


def test_migrate_legacy(db):
    legacy = {"deptCode": "30001267", "admissionYear": 2024, "track": "single", "grade": 3, "enrollment": "재학",
              "gpa": 3.42, "credits": 98, "semesters": 5, "auto": ["grade", "gpa", "credits"], "edited": ["credits"],
              "sensitive": {"income": "4", "region": "광주", "school": "서울특별시"}, "onboardingSkipped": False,
              "college": "AI융합대학", "department": "인공지능학부"}
    res = service.migrate_legacy(db, legacy)
    doc = service.get(db)
    assert res["migrated"] and doc["complete"]
    assert doc["filledBy"]["grade"] == "auto" and doc["filledBy"]["earnedCredits"] == "user"
    assert doc["profile"]["incomeBracket"] == 4 and doc["profile"]["highSchoolRegion"] is None   # 목록 밖 지역은 버린다
    assert service.migrate_legacy(db, legacy) == {"migrated": False}                              # 이미 있으면 안 옮긴다
    assert doc["profile"]["deptPath"] == "AI융합대학 › 인공지능학부 › 인공지능전공"                # 옛 화면은 전공 코드를 deptCode 에 넣었다


def test_import_problem_without_c3(monkeypatch, tmp_path):
    from student import config as C, jobs
    monkeypatch.setattr(C, "C3_PYTHON", tmp_path / "none" / "python.exe")
    assert "C3_Login_agent" in jobs.import_problem(False)
    monkeypatch.setattr(C, "C3_PYTHON", tmp_path / "python.exe")
    monkeypatch.setattr(C, "C3_BROWSERS", tmp_path)
    (tmp_path / "python.exe").write_text("")
    for attr in ("C3_STATE", "C3_CRED", "HAKSTD_STATE"):
        monkeypatch.setattr(C, attr, tmp_path / f"{attr}.missing")
    assert "로그인" in jobs.import_problem(False)          # 로그인 기록 없음 → 409 needLogin
    assert jobs.import_problem(True) is None               # 로그인 창을 여는 경우는 시작해도 된다


DASH = """<div class="infotext"><span>홍길동</span> | <span>2024123456</span> | <span>3 학년</span> | <span>재학</span> |
<span>남</span> | <span>주전공 : AI융합대학 / 인공지능학부</span></div><div id="Score">성적(비교) | 3.42 | / 4.5</div>"""
GRADES = """<table id="ctl00_gvData"><tr><th>년도</th><th>학기</th><th>교과구분</th><th>교과목명</th><th>성적</th><th>학점</th><th>교과목상태</th></tr>
<tr><td>2025</td><td>1</td><td>전필</td><td>A</td><td>A+</td><td>3</td><td></td></tr>
<tr><td>2025</td><td>1</td><td>전선</td><td>B</td><td>F</td><td>3</td><td></td></tr>
<tr><td>2025</td><td>하계 계절</td><td>교선</td><td>C</td><td>B0</td><td>2</td><td></td></tr>
<tr><td>2025</td><td>2</td><td>전필</td><td>D</td><td>A0</td><td>3</td><td></td></tr>
<tr><td>학기 평점</td><td></td><td></td><td></td><td></td><td>6</td><td></td></tr></table>"""


def test_hakstd_parsers_never_read_name():
    d = parse_dashboard(DASH)
    assert d == {"grade": 3, "enrollment_status": "재학", "college": "AI융합대학", "department": "인공지능학부",
                 "gpa": {"value": 3.42, "scale": 4.5, "basis": "전체"}}
    assert "홍길동" not in str(d) and "2024123456" not in str(d)
    assert parse_grades(GRADES) == {"earned_credits": 8, "semesters_completed": 2, "last_semester_credits": 3}


def test_notice_bridge():
    out = notice_bridge.to_notice({"grade": 3, "department": "인공지능학부", "flags": {"veteranFamily": True},
                                   "draftContext": {"careerGoal": "연구원"}, "incomeBracket": None})
    assert out == {"grade": 3, "department": "인공지능학부", "flags": {"veteran_family": True},
                   "draft_context": {"career_goal": "연구원"}, "field_group": "공학계열"}
