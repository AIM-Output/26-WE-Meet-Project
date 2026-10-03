"""룰셋 자동 매칭(C2 6절) · 검사 · 교육과정 표 파싱 · 기이수성적 표 파싱."""
import pytest

from conftest import FIXTURES
from graduation import curriculum, hakstd, rules


# ── 자동 매칭 ──────────────────────────────────────────────

def test_match_dept_ruleset_exact_for_dept_only_student():
    m = rules.match("30001265", None, 2022, "single")
    assert m["level"] == "exact" and m["ruleset"]["id"] == "jnu:30001265:2021:single" and not m["warnings"]


def test_match_dept_level_when_major_has_no_own_ruleset():
    m = rules.match("30001265", "30001267", 2021, "single")
    assert m["level"] == "dept"


def test_match_nearest_earlier_year_warns():
    m = rules.match("30001265", "30001267", 2024, "single")
    assert m["level"] == "nearest" and "2021~2022" in m["warnings"][0]


def test_match_no_earlier_year_is_none():
    assert rules.match("30001265", None, 2019, "single")["level"] == "none"


def test_match_track_fallback_to_single():
    m = rules.match("30001265", None, 2021, "double")
    assert m["level"] == "track" and "복수전공" in m["warnings"][0]


def test_match_other_department_none():
    assert rules.match("30000150", None, 2023, "single")["level"] == "none"


def test_user_ruleset_wins():
    mine = {"id": "user:x", "areas": []}
    assert rules.match("30001265", None, 2024, "single", user=mine) == {"ruleset": mine, "level": "user", "warnings": []}


def test_resolve_fills_courses_from_curriculum_and_user_map():
    m = rules.match("30001265", "30001267", 2021, "single")
    r = rules.resolve(m["ruleset"], {"deptCode": "30001265", "majorCode": "30001267", "admissionYear": 2021},
                      {"교직": "free", "전선": None})
    req = next(a for a in r["areas"] if a["key"] == "major_required")
    assert {c["code"] for c in req["courses"]} == {"CIS3001", "STT3019", "CIS3003", "CIS3016", "SAI0008"}
    assert sum(c["credits"] for c in req["courses"]) == 15                  # 룰셋 전필 15학점과 맞는다
    assert r["categoryMap"]["교직"] == "free" and "전선" not in r["categoryMap"]
    assert [s["code"] for s in r["curriculum"]["sources"]] == ["30001265", "30001267"]


def test_resolve_missing_curriculum_is_reported():
    m = rules.match("30001265", "30001267", 2021, "single")
    r = rules.resolve(m["ruleset"], {"deptCode": "30001265", "majorCode": "39999999", "admissionYear": 2021})
    assert r["curriculum"]["missing"] == ["39999999"]


def test_template_has_jnu_areas():
    t = rules.template({"deptCode": "1", "admissionYear": 2024})
    assert [a["key"] for a in t["areas"]] == ["ge_required", "ge_elective", "major_required", "major_elective", "free"]
    assert t["categoryMap"]["전필"] == "major_required" and t["totalCredits"] is None


# ── 검사 ────────────────────────────────────────────────────

def test_validate_roundtrip_bundled():
    doc = rules.by_id("jnu:30001265:2021:single")
    v = rules.validate(doc)
    assert v["totalCredits"] == 140 and len(v["areas"]) == 5 and v["certifications"][1]["hintCourses"] == ["생활영어1", "생활영어2"]
    assert next(a for a in v["areas"] if a["key"] == "major_required")["coursesFrom"] == "전필"


@pytest.mark.parametrize("bad, msg", [
    ({"areas": []}, "1~20"),
    ({"areas": [{"key": "A", "label": "x"}]}, "key"),
    ({"areas": [{"key": "a", "minCredits": -1}]}, "0~200"),
    ({"areas": [{"key": "a", "overflowTo": "b"}]}, "넘길 영역"),
    ({"areas": [{"key": "a"}], "categoryMap": {"전필": "zz"}}, "없는 영역"),
    ({"areas": [{"key": "a"}], "minGpa": {"value": 5, "scale": 4.5}}, "최저 평점"),
    ({"areas": [{"key": "a"}], "totalCredits": 0}, "졸업 학점"),
])
def test_validate_rejects(bad, msg):
    with pytest.raises(rules.Invalid, match=msg):
        rules.validate(bad)


def test_validate_explicit_course_list_replaces_courses_from():
    v = rules.validate({"areas": [{"key": "major_required", "coursesFrom": "전필",
                                   "courses": [{"code": "ab1", "name": "과목", "credits": 3}]}]})
    a = v["areas"][0]
    assert a["courses"] == [{"code": "AB1", "name": "과목", "credits": 3}] and "coursesFrom" not in a


# ── 교육과정검색 표 (2026-09-28 실측 HTML 일부) ─────────────────

def test_parse_curriculum_rows_and_last_page():
    html = (FIXTURES / "curriculum_30001267_2024_p1.html").read_text(encoding="utf-8")
    rows = curriculum.parse_rows(html)
    assert len(rows) == 10
    assert rows[0] == {"grade": 3, "term": "1", "category": "전선", "name": "인공지능설계프로젝트", "code": "AIC0012",
                       "credits": 3.0}
    assert curriculum.last_page(html) == 3


def test_courses_for_merges_dept_and_major_without_duplicates():
    lst, meta = curriculum.courses_for("30001265", "30001267", 2021, "전필")
    assert len(lst) == 5 and meta["missing"] == []


# ── 기이수성적 표 (구조: notice_agent/references/site-structure.md §4) ──

SUNG010 = """
<table id="ctl00_ContentPlaceHolder1_gvData">
 <tr><th>년도</th><th>학기</th><th>교과구분</th><th>교과목번호</th><th>교과목명</th><th>성적</th><th>학점</th>
     <th>교과목상태</th><th>재이수</th><th>교양영역</th></tr>
 <tr><td>2023</td><td>1</td><td>교필</td><td>CLT0082</td><td>수학1</td><td>B+</td><td>3</td><td></td><td></td><td>기초교양(기초과학)</td></tr>
 <tr><td>2023</td><td>1</td><td>전선</td><td>cis9017</td><td>C프로그래밍및실습</td><td>A0</td><td>3.0</td><td></td><td></td><td></td></tr>
 <tr><td>학기 평점</td><td></td><td></td><td></td><td></td><td>3.75</td><td>6</td><td></td><td></td><td></td></tr>
 <tr><td>2023</td><td>하계 계절</td><td>교선</td><td>CLT1234</td><td>생활영어1</td><td>P</td><td>2</td><td></td><td></td><td>균형교양(표현과소통)</td></tr>
 <tr><td>2024</td><td>2</td><td>전필</td><td>CIS3001</td><td>자료구조</td><td>F</td><td>3</td><td>수강포기</td><td>Y</td><td></td></tr>
</table>"""


def test_parse_sung010_courses_skips_total_rows():
    cs = hakstd.parse_courses(SUNG010)
    assert [c["name"] for c in cs] == ["수학1", "C프로그래밍및실습", "생활영어1", "자료구조"]
    assert cs[1]["code"] == "CIS9017" and cs[1]["credits"] == 3.0
    assert cs[2]["semester"] == "하계 계절" and cs[2]["geArea"] == "균형교양(표현과소통)"
    assert cs[3] | {} == {**cs[3], "status": "수강포기", "retake": "Y", "grade": "F"}


def test_parse_sung010_missing_headers_returns_empty():
    assert hakstd.parse_courses("<table id='x_gvData'><tr><th>년도</th><th>과목</th></tr></table>") == []
    assert hakstd.parse_courses("<html>로그인</html>") == []
