"""프로필 자동 채움 (선택) — 학사정보시스템에서 학년·학적·전공·평점·이수학점을 읽어 data/profile.json 에 병합.

    python -m scripts.profile_from_hakstd            # 기존 profile.json 이 있으면 학사 항목만 갱신 (관심사·소득구간 등은 유지)
    python -m scripts.profile_from_hakstd --show     # 저장하지 않고 화면에만
    python -m scripts.profile_from_hakstd --interactive   # SSO 세션이 없으면 창을 띄워 로그인

읽는 곳 (references/site-structure.md §4)
    /Home/DashBoard        div.infotext  "이름 | 학번 | N 학년 | 재학 | 성별 | 주전공 : <단과대> / <학부>"
                           #Score        "성적(비교) | 3.xx | / 4.5"
    /web/Sung/Sung010      [조회] 후 table#…gvData (년도·학기·교과구분·교과목명·성적·학점·교과목상태)
                           → 취득학점 합계, 이수 학기 수, 직전학기 학점
이름·학번은 **읽지도 저장하지도 않는다** (기능명세서 4장 개인정보 최소 수집).
수치가 학교 공식 성적증명과 다를 수 있으니(재이수·F 처리 방식) 장학 신청 전에는 성적증명서로 확인할 것.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict

from bs4 import BeautifulSoup

from . import config as C
from .schemas import GPA, Profile

FAIL_GRADES = {"F", "NP", "U", "W"}      # 취득학점에 넣지 않는 성적


def parse_dashboard(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    out: dict = {}
    info = soup.select_one("div.infotext")
    if info is not None:
        txt = info.get_text(" | ", strip=True)
        m = re.search(r"(\d)\s*학년", txt)
        if m:
            out["grade"] = int(m.group(1))
        m = re.search(r"\|\s*(재학|휴학|졸업|수료|제적)\s*\|", txt)
        if m:
            out["enrollment_status"] = m.group(1)
        m = re.search(r"주전공\s*[:：]\s*([^/|]+?)\s*/\s*([^|]+)", txt)
        if m:
            out["college"] = m.group(1).strip()
            out["department"] = m.group(2).strip()
    score = soup.select_one("#Score")
    if score is not None:
        txt = score.get_text(" ", strip=True)
        m = re.search(r"(\d\.\d{1,2})\s*/\s*(4\.5|4\.3|4\.0)", txt)
        if m:
            out["gpa"] = {"value": float(m.group(1)), "scale": float(m.group(2)), "basis": "전체"}
    return out


def parse_grades(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    table = soup.select_one("table[id$=gvData]")
    if table is None:
        return {}
    heads = [th.get_text(" ", strip=True) for th in table.select("th")]
    idx = {h: i for i, h in enumerate(heads)}
    need = ("년도", "학기", "성적", "학점")
    if not all(k in idx for k in need):
        return {}
    per_term: dict[tuple[str, str], int] = defaultdict(int)
    total = 0
    for tr in table.select("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if len(tds) < len(heads):
            continue
        year, term_name = tds[idx["년도"]].strip(), tds[idx["학기"]].strip()
        if not re.fullmatch(r"\d{4}", year):        # '학기 평점' 같은 학기별 합계 행은 건너뛴다 (실측: 이 행 때문에 학점이 2배로 잡혔다)
            continue
        grade, credit = tds[idx["성적"]].strip().upper(), tds[idx["학점"]].strip()
        status = tds[idx["교과목상태"]] if "교과목상태" in idx else ""
        if not re.fullmatch(r"\d+(\.\d+)?", credit):
            continue
        if grade in FAIL_GRADES or "포기" in status or "취소" in status:
            continue
        c = int(float(credit))
        per_term[(year, term_name)] += c
        total += c
    if not per_term:
        return {}
    terms = sorted(per_term)
    # 정규 학기는 학기 칸이 '1' / '2' (계절학기는 '하계 계절' / '동계 계절')
    regular = [t for t in terms if re.fullmatch(r"[12]\s*(?:학기)?", t[1])]
    last = regular[-1] if regular else terms[-1]
    return {"earned_credits": total, "semesters_completed": len(regular) or len(terms),
            "last_semester_credits": per_term[last]}


def fetch(interactive: bool = False) -> dict:
    from . import sso_session as S
    data: dict = {}
    with S.hakstd_page(interactive=interactive) as page:
        data.update(parse_dashboard(page.content()))
        if S.goto(page, C.HAKSTD_GRADES):
            try:
                page.click("input[id$=ibtnSearch]", timeout=10_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            data.update(parse_grades(page.content()))
    return data


def merge_profile(fetched: dict) -> Profile:
    base = {}
    if C.PROFILE_FILE.exists():
        base = json.loads(C.PROFILE_FILE.read_text(encoding="utf-8"))
    base.update({k: v for k, v in fetched.items() if v is not None})
    base.setdefault("field_group", "공학계열" if re.search(r"공학|인공지능|컴퓨터|소프트웨어", base.get("department", "") or "") else None)
    return Profile.model_validate(base)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--interactive", action="store_true")
    a = ap.parse_args(argv)
    C.ensure_dirs()
    fetched = fetch(a.interactive)
    if not fetched:
        print("학사정보시스템에서 읽은 항목이 없습니다. 페이지 구조가 바뀌었는지 references/site-structure.md 와 비교하세요.")
        return 1
    prof = merge_profile(fetched)
    print("읽어온 항목:", ", ".join(f"{k}={v}" for k, v in fetched.items()))
    if a.show:
        print(prof.model_dump_json(indent=2, exclude_none=True))
        return 0
    C.PROFILE_FILE.write_text(prof.model_dump_json(indent=2, exclude_none=True), encoding="utf-8")
    print(f"저장: {C.PROFILE_FILE}  (소득구간·관심사·초안용 정보는 파일을 열어 직접 채우세요)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
