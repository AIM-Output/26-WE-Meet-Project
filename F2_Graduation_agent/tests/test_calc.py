"""계산기 회귀 테스트 — 요구사항정의서 F2 5절 ①~⑩, 9절 '모의 이수 내역으로 영역별 결과를 고정'.

기준: 저장소의 인공지능학부 2021~2022 룰셋(140학점 · 교필 18 · 교선 18 · 전필 15 · 전선 33) +
      교육과정 스냅숏(학부 30001265 + 인공지능전공 30001267, 2021학년도 — 전필 5과목 · 교필 6과목).
"""
import time

import pytest

from conftest import PROFILE_2021, course
from graduation import calc, rules


def ruleset_for(profile, level_expected=None):
    m = rules.match(profile["deptCode"], profile.get("majorCode"), profile["admissionYear"], profile.get("track", "single"))
    if level_expected:
        assert m["level"] == level_expected
    return rules.resolve(m["ruleset"], profile), m["level"]


@pytest.fixture(scope="module")
def rs():
    return ruleset_for(PROFILE_2021)[0]


def area(res, key):
    return next(a for a in res["areas"] if a["key"] == key)


def required_courses(rs, key):
    return next(a for a in rs["areas"] if a["key"] == key)["courses"]


def graduate(rs):
    """140학점을 영역별로 다 채운 모의 이수 내역."""
    out = [course(c["name"], c["credits"], "교필", code=c["code"], year=2021) for c in required_courses(rs, "ge_required")]
    out += [course(c["name"], c["credits"], "전필", code=c["code"], year=2022) for c in required_courses(rs, "major_required")]
    out += [course(f"교양선택{i}", 3, "교선", code=f"GE{i:03d}", year=2021, sem="2") for i in range(6)]
    out += [course(f"전공선택{i}", 3, "전선", code=f"MJ{i:03d}", year=2023) for i in range(11)]
    out += [course(f"일반선택{i}", 3, "일선", code=f"FR{i:03d}", year=2024) for i in range(19)]
    return out


DONE = {"thesis": {"state": "done"}, "foreign_language": {"state": "done"}}
GPA = {"value": 3.42, "scale": 4.5}


# ① ~ ⑩ 모의 이수 내역 10건 ──────────────────────────────────

def test_1_empty_freshman(rs):
    res = calc.calculate([], rs, {}, GPA)
    assert res["total"] == {"required": 140, "earned": 0, "short": 140, "remaining": 140, "areaShort": 84}
    assert len(area(res, "major_required")["missingCourses"]) == 5          # 학부 전필 4 + 인공지능캡스톤디자인
    assert len(area(res, "ge_required")["missingCourses"]) == 6
    assert res["verdict"] == "부족"


def test_2_fail_np_w_and_dropped_excluded(rs):
    cs = [course("자료구조", 3, "전필", "F", code="CIS3001"), course("대학글쓰기", 2, "교선", "NP"),
          course("알고리즘", 3, "전필", "W", code="CIS3016"), course("데이터마이닝", 3, "전선", "A0", status="수강포기"),
          course("딥러닝", 3, "전선", "B+")]
    res = calc.calculate(cs, rs)
    assert res["total"]["earned"] == 3
    reasons = {c["name"]: c["excludedReason"] for c in res["courses"] if c["excluded"]}
    assert set(reasons) == {"자료구조", "대학글쓰기", "알고리즘", "데이터마이닝"}
    assert "F" in reasons["자료구조"] and "포기" in reasons["데이터마이닝"]
    assert any(m["code"] == "CIS3001" for m in area(res, "major_required")["missingCourses"])   # F 는 이수로 안 친다


def test_3_retake_counts_once_best_grade(rs):
    cs = [course("자료구조", 3, "전필", "C+", code="CIS3001", year=2022, sem="1"),
          course("자료구조", 3, "전필", "A0", code="CIS3001", year=2023, sem="1", id="retake")]
    res = calc.calculate(cs, rs)
    assert res["total"]["earned"] == 3
    kept = [c for c in res["courses"] if not c["excluded"]]
    assert [c["id"] for c in kept] == ["retake"]
    dropped = next(c for c in res["courses"] if c["excluded"])
    assert dropped["excludedReason"].startswith("재수강")


def test_4_same_term_manual_duplicate_counts_once(rs):
    cs = [course("인공지능", 3, "전필", "A+", code="CIS3003"),
          course("인공지능", 3, None, "A+", code="CIS3003", source="manual", id="m1", areaOverride="major_required")]
    res = calc.calculate(cs, rs)
    assert res["total"]["earned"] == 3
    dup = next(c for c in res["courses"] if c["excluded"])
    assert dup["id"] == "m1" and "두 번" in dup["excludedReason"]           # 학사시스템 것이 남는다


def test_5_unknown_category_goes_unmapped_and_lowers_verdict(rs):
    cs = graduate(rs) + [course("교직실무", 2, "교직", "A0", code="EDU0001")]
    res = calc.calculate(cs, rs, DONE, GPA)
    assert [c["name"] for c in res["unmapped"]] == ["교직실무"]
    assert res["total"]["earned"] == 143                                     # 미분류도 총 학점에는 들어간다 (⑦)
    assert res["verdict"] == "확인 필요"
    assert any("분류하지 못한" in d for d in res["reasons"]["doubts"])


def test_6_overflow_once_not_chained(rs):
    cs = [course(f"교필{i}", 3, "교필", code=f"G{i}") for i in range(8)]          # 교필 24 → 초과 6 을 교선으로
    cs += [course(f"교선{i}", 3, "교선", code=f"S{i}") for i in range(6)]         # 교선 자체 18 → 초과 없음
    res = calc.calculate(cs, rs)
    ger, gee, free = area(res, "ge_required"), area(res, "ge_elective"), area(res, "free")
    assert (ger["own"], ger["outflow"], ger["earned"]) == (24, 6, 18)
    assert (gee["own"], gee["inflow"], gee["earned"]) == (18, 6, 24)
    assert gee["outflow"] == 0 and free["inflow"] == 0                       # 넘겨받은 6학점이 다시 일반선택으로 가지 않는다


def test_7_total_short_even_when_areas_full(rs):
    cs = graduate(rs)[:-10]                                                  # 일반선택 10과목(30학점) 빼기
    res = calc.calculate(cs, rs, DONE, GPA)
    assert all(a["ok"] for a in res["areas"])
    assert res["total"]["short"] == 29 and res["total"]["remaining"] == 29   # 111/140
    assert res["verdict"] == "부족"
    assert res["headline"] == "영역은 채움 · 총 학점만 남음"


def test_8_user_area_override_beats_category_map(rs):
    cs = [course("창의적사고", 3, "교선", code="X1", areaOverride="free")]
    res = calc.calculate(cs, rs)
    c = res["courses"][0]
    assert (c["area"], c["areaSetBy"]) == ("free", "user")
    assert area(res, "ge_elective")["own"] == 0


def test_9_zero_credit_course_listed_not_summed(rs):
    cs = [course("신입생세미나", 0, "교선", "P", code="Z0"), course("수학1", 3, "교필", "B0", code="CLT0082")]
    res = calc.calculate(cs, rs)
    assert res["total"]["earned"] == 3
    assert [c["name"] for c in area(res, "ge_elective")["courses"]] == ["신입생세미나"]


def test_10_full_graduate_verdicts(rs):
    cs = graduate(rs)
    assert calc.calculate(cs, rs, DONE, GPA)["verdict"] == "충족"
    res = calc.calculate(cs, rs, {"thesis": {"state": "done"}}, GPA)          # 외국어 영역 모름
    assert res["verdict"] == "확인 필요" and "외국어 영역 확인" in res["reasons"]["unknowns"]
    res = calc.calculate(cs, rs, {**DONE, "thesis": {"state": "todo"}}, GPA)
    assert res["verdict"] == "부족"                                           # 학점을 다 채워도 인증 미충족이면 '졸업 가능' 아님 (F2-R43)


# 그 밖의 규칙 ────────────────────────────────────────────────

def test_major_required_checked_by_course_even_under_other_category(rs):
    cs = [course("알고리즘", 3, "전선", code="CIS3016")]                        # 전필 과목을 전선으로 들었다
    res = calc.calculate(cs, rs)
    assert all(m["code"] != "CIS3016" for m in area(res, "major_required")["missingCourses"])
    assert area(res, "major_elective")["own"] == 3


def test_gpa_compare_only_same_scale(rs):
    r = dict(rs, minGpa={"value": 2.0, "scale": 4.5})
    assert calc.calculate(graduate(rs), r, DONE, {"value": 1.9, "scale": 4.5})["gpa"]["ok"] is False
    res = calc.calculate(graduate(rs), r, DONE, {"value": 3.0, "scale": 4.3})
    assert res["gpa"]["ok"] is None and "척도" in res["gpa"]["note"] and res["verdict"] == "확인 필요"
    assert calc.calculate(graduate(rs), rs, DONE, None)["gpa"]["ok"] is None   # 기준 없음 → 판정에 걸리지 않는다
    assert calc.calculate(graduate(rs), rs, DONE, None)["verdict"] == "충족"


def test_whatif_adds_assumed_credits_and_courses(rs):
    cs = graduate(rs)
    cs = [c for c in cs if c["code"] not in ("CIS3016", "SAI0008")]           # 알고리즘·캡스톤 안 들음 → 전필 2과목
    now = calc.calculate(cs, rs, DONE, GPA)
    assert len(area(now, "major_required")["missingCourses"]) == 2
    after = calc.calculate(cs, rs, DONE, GPA, {"courses": ["CIS3016", "SAI0008"]})
    assert area(after, "major_required")["missingCourses"] == []
    assert after["total"]["earned"] == now["total"]["earned"] + 6
    assert all(c["source"] != "whatif" for c in after["courses"])            # 가정 과목은 이수 과목 목록에 섞이지 않는다
    cmp = calc.compare(now, after)
    assert cmp["current"]["total"]["remaining"] > cmp["assumed"]["total"]["remaining"]


def test_whatif_ignores_unknown_area_keys(rs):
    res = calc.calculate([], rs, assumptions={"areas": {"nope": 9, "major_elective": 6}})
    assert res["total"]["earned"] == 6


def test_no_ruleset_still_sums():
    res = calc.calculate([course("자료구조", 3, "전필", code="CIS3001")], None)
    assert res["total"]["earned"] == 3 and res["total"]["required"] is None
    assert res["verdict"] == "확인 필요"


def test_200_courses_under_100ms(rs):
    cs = [course(f"과목{i}", 3, "전선", code=f"C{i:04d}", year=2020 + i % 6) for i in range(200)]
    t = time.perf_counter()
    calc.calculate(cs, rs, DONE, GPA)
    assert time.perf_counter() - t < 0.1


# 2023 이후 입학 — 인접 연도 기준 + 대학 공통 교양 영역 조건 ──────────────

@pytest.fixture(scope="module")
def rs2024():
    return ruleset_for(dict(PROFILE_2021, admissionYear=2024), "nearest")[0]


def test_nearest_year_ruleset_lowers_verdict(rs2024):
    cs = [dict(c, geArea="기초교양(기초SW)") for c in graduate(rs2024)]
    res = calc.calculate(cs, rs2024, DONE, GPA, level="nearest")
    assert res["verdict"] == "확인 필요"
    assert rs2024["curriculum"]["year"] == 2024                              # 과목 목록은 입학년도 교육과정


def test_ge_checks_count_by_ge_area(rs2024):
    keys = [c["key"] for c in rs2024["checks"]]
    assert "ge_creative" in keys and "ge_humanities" in keys
    cs = [course("글쓰기", 3, "교선", geArea="균형교양(표현과소통)"), course("코딩기초", 3, "교선", geArea="기초교양(기초SW)"),
          course("창의설계", 3, "교선", geArea="역량교양(창의)")]
    res = calc.calculate(cs, rs2024)
    st = {c["key"]: c for c in res["checks"]}
    assert st["ge_expression"]["state"] == "ok" and st["ge_basic_sw"]["state"] == "ok"
    assert st["ge_emotion"]["state"] == "short" and st["ge_emotion"]["short"] == 3
    assert st["ge_humanities"]["earned"] == 6 and st["ge_humanities"]["state"] == "short"


def test_ge_checks_unknown_without_ge_area(rs2024):
    res = calc.calculate([course("글쓰기", 3, "교선")], rs2024)
    assert {c["state"] for c in res["checks"]} == {"unknown"}               # 교양영역 칸을 못 읽으면 모자란지 모른다


def test_approximate_check_satisfied_stays_unknown(rs2024):
    cs = [course(f"인문{i}", 3, "교선", geArea="역량교양(감성)") for i in range(3)]
    st = {c["key"]: c for c in calc.calculate(cs, rs2024)["checks"]}
    assert st["ge_humanities"]["earned"] == 9 and st["ge_humanities"]["state"] == "unknown"


def test_2021_has_no_common_checks(rs):
    assert rs["checks"] == []


def test_foreign_language_hint_from_courses(rs):
    res = calc.calculate([course("생활영어1", 2, "교선")], rs)
    fl = next(c for c in res["certifications"] if c["key"] == "foreign_language")
    assert fl["hintFound"] == ["생활영어1"] and fl["state"] == "unknown"    # 힌트만 준다 — 체크는 사용자가
