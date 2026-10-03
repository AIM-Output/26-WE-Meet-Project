"""학과 마스터 — 교육과정검색 select 읽기 · 계층 되살리기 · 펼친 목록 · 옛 코드 보존."""
import copy

from conftest import MASTER

from student import master
from student.master_crawl import build_departments, parse_selects

PAGE = """<select name="x" id="ctl00_ctl00_ContentPlaceHolder1_PageContent_ddl_sch_COLL">
<option value="">선택하세요</option><option selected value="30001229">AI융합대학</option>
<option value="20000150">[광주]일반대학원 석사과정</option></select>
<select id="ctl00_ctl00_ContentPlaceHolder1_PageContent_ddl_sch_DEPT"><option value="">선택하세요</option>
<option value="30001231">로봇공학융합전공 로봇공학융합전공</option><option value="30001230">로봇공학융합전공</option>
<option value="30001265">인공지능학부</option><option value="30001266">인공지능학부 소프트웨어전공</option>
<option value="30001267">인공지능학부  인공지능전공</option><option value="30001264">빅데이터융합학과</option></select>"""


def test_parse_and_build():
    sel = parse_selects(PAGE)
    assert sel["COLL"] == [("30001229", "AI융합대학"), ("20000150", "[광주]일반대학원 석사과정")]
    depts = {d["name"]: d for d in build_departments(sel["DEPT"])}
    assert [m["name"] for m in depts["인공지능학부"]["majors"]] == ["소프트웨어전공", "인공지능전공"]
    assert depts["로봇공학융합전공"]["majors"] == [{"code": "30001231", "name": "로봇공학융합전공"}]
    assert depts["빅데이터융합학과"]["majors"] == []


def test_entries_and_find(db):
    paths = [e["path"] for e in master.entries()]
    assert "AI융합대학 › 인공지능학부" in paths                       # 전공 배정 전
    assert "AI융합대학 › 인공지능학부 › 인공지능전공" in paths
    assert "AI융합대학 › 로봇공학융합전공" in paths                   # 같은 이름 전공은 한 번만
    assert "AI융합대학 › 로봇공학융합전공 › 로봇공학융합전공" not in paths
    assert master.find("30001265", "30001267")["major"] == "인공지능전공"
    assert master.find("30001265")["majorCode"] is None
    assert master.find("30001230")["majorCode"] == "30001231"       # 전공 하나뿐 → 그 줄
    assert master.find("99999999") is None
    assert master.find_by_names("AI융합대학", "인공지능학부")["deptCode"] == "30001265"
    assert master.find_by_names(None, "컴퓨터공학과")["collegeCode"] == "30000088"


def test_merge_retired_keeps_old_codes():
    new = copy.deepcopy(MASTER)
    new["colleges"][0]["departments"][0]["majors"].pop()            # 인공지능전공이 사라짐
    new["colleges"].pop()                                            # 공과대학이 사라짐
    merged = master.merge_retired(new, MASTER)
    ai = merged["colleges"][0]["departments"][0]
    assert {"code": "30001267", "name": "인공지능전공", "retired": True} in ai["majors"]
    assert merged["colleges"][-1]["code"] == "30000088" and merged["colleges"][-1]["retired"]
