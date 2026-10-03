"""학사정보시스템 기이수성적 수집 (F2-R01·R02·R03) — 과목마다 년도·학기·교과구분·학수번호·과목명·성적·학점·상태·재이수·교양영역.

**C3_Login_agent 의 .venv 로 실행한다** (playwright 와 SSO 로그인 세션이 거기 있다):
    ..\\C3_Login_agent\\.venv\\Scripts\\python -m graduation.hakstd --out state\\import.json [--interactive]
대시보드의 '이수 내역 가져오기' 버튼은 jobs.py 가 이렇게 띄우고, 결과 파일을 읽어 저장한 뒤 지운다.

로그인은 C2 의 student.hakstd.hakstd_page 를 그대로 쓴다 — 같은 학사정보시스템이고, 로그인 전이면 자체 로그인 화면
(/Main/Login.aspx)에 머무는 함정(2026-09-28 실측)도 거기서 처리한다. 비밀번호는 C3_Login_agent 코드만 다룬다.

읽는 곳 (notice_agent/references/site-structure.md §4)
    /web/Sung/Sung010  [조회](input[id$=ibtnSearch]) → table#…gvData
        년도 · 학기 · 교과구분 · 교과목번호 · 교과목명 · 성적 · 학점 · 교과목상태 · 재이수 · 교양영역
        학기 칸: 정규 '1'·'2', 계절 '하계 계절'·'동계 계절'. 년도 칸이 '학기 평점'인 합계 행이 섞여 있다 → 4자리 연도 행만.
    /Home/DashBoard    같은 김에 평점·학년·학적도 읽어 프로필(C2)에 '자동'으로 넘긴다 (C2 파서 그대로 — 이름·학번 칸은 안 읽는다)
표 파싱은 표준 라이브러리(html.parser)라 어느 파이썬에서나 테스트된다.
종료 코드: 0 성공 · 1 과목을 못 읽음(형식 변경 의심) · 2 로그인 필요
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
from datetime import datetime
from html.parser import HTMLParser
from typing import Optional

from . import config as C

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(C.C3_BROWSERS))

# 머리글 → 우리 칸 이름. 학교가 머리글 글자를 조금 바꿔도 읽히게 별칭을 둔다.
HEADERS = {
    "year": ("년도", "연도", "학년도", "이수년도"),
    "semester": ("학기", "이수학기"),
    "rawCategory": ("교과구분", "이수구분", "구분"),
    "code": ("교과목번호", "학수번호", "과목번호", "교과목코드"),
    "name": ("교과목명", "과목명", "교과목"),
    "grade": ("성적", "등급", "평어"),
    "credits": ("학점",),
    "status": ("교과목상태", "상태"),
    "retake": ("재이수", "재수강"),
    "geArea": ("교양영역", "영역"),
}
NEED = ("year", "semester", "name", "credits")


class _Grid(HTMLParser):
    """table[id$=gvData] 의 머리글(th)과 행(td)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.heads: list[str] = []
        self.rows: list[list[str]] = []
        self._depth = 0
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None
        self._is_th = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self._depth:
                self._depth += 1
            elif (dict(attrs).get("id") or "").endswith("gvData"):
                self._depth = 1
            return
        if not self._depth:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._is_th = [], tag == "th"

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if not self._depth:
            return
        if tag in ("td", "th") and self._cell is not None and self._row is not None:
            text = " ".join("".join(self._cell).split())
            (self.heads.append(text) if self._is_th else self._row.append(text))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._depth -= 1


def _index(heads: list[str]) -> dict[str, int]:
    idx: dict[str, int] = {}
    clean = [re.sub(r"\s+", "", h) for h in heads]
    for key, names in HEADERS.items():
        for i, h in enumerate(clean):
            if h in names and i not in idx.values():
                idx[key] = i
                break
    return idx


def parse_courses(html: str) -> list[dict]:
    """기이수성적 표 → 과목 목록. 이름·학번은 이 표에 없다. 표를 못 찾거나 머리글이 모자라면 []."""
    g = _Grid()
    g.feed(html)
    idx = _index(g.heads)
    if not all(k in idx for k in NEED):
        return []
    out = []
    for tds in g.rows:
        if len(tds) < len(g.heads):
            continue

        def cell(k: str) -> str:
            return tds[idx[k]].strip() if k in idx else ""

        year = cell("year")
        if not re.fullmatch(r"\d{4}", year):             # '학기 평점' 합계 행 (이 행 때문에 학점이 2배로 잡힌 적이 있다)
            continue
        credit = cell("credits")
        if not re.fullmatch(r"\d+(\.\d+)?", credit):
            continue
        out.append({"year": int(year), "semester": cell("semester"), "rawCategory": cell("rawCategory"),
                    "code": cell("code").upper(), "name": cell("name"), "grade": cell("grade").upper(),
                    "credits": float(credit), "status": cell("status"), "retake": cell("retake"),
                    "geArea": cell("geArea")})
    return out


# ── 브라우저 (C3_Login_agent .venv 에서만) ──────────────────────

def _c2_hakstd():
    if str(C.C2_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C2_AGENT_DIR))
    from student import hakstd as c2h      # type: ignore[import-not-found]  C2_Profile_agent/student/hakstd.py
    return c2h


def fetch(interactive: bool = False) -> dict:
    from urllib.parse import urlparse

    c2h = _c2_hakstd()
    out: dict = {"courses": [], "profile": {}}
    with c2h.hakstd_page(interactive) as page:
        if not urlparse(page.url).path.lower().startswith("/home/dashboard"):
            page.goto(C.HAKSTD_DASHBOARD, wait_until="load", timeout=60_000)
            c2h._settle(page, 20)
        out["profile"].update(c2h.parse_dashboard(page.content()))
        page.goto(C.HAKSTD_GRADES, wait_until="load", timeout=60_000)
        if c2h._settle(page, 20):
            with contextlib.suppress(Exception):
                page.click("input[id$=ibtnSearch]", timeout=10_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
            html = page.content()
            out["courses"] = parse_courses(html)
            out["profile"].update(c2h.parse_grades(html))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(C.IMPORT_OUT))
    ap.add_argument("--interactive", action="store_true")
    a = ap.parse_args(argv)
    print(f"======== {datetime.now():%Y-%m-%d %H:%M:%S} 학사정보시스템 기이수성적 가져오기 ========")
    try:
        data = fetch(a.interactive)
    except Exception as e:                              # noqa: BLE001
        if type(e).__name__ == "LoginRequired":
            print(f"  {e}")
            return 2
        raise
    terms = {(c["year"], c["semester"]) for c in data["courses"]}
    print(f"  과목 {len(data['courses'])}개 · {len(terms)}개 학기 · 프로필 항목: {', '.join(sorted(data['profile'])) or '없음'}")
    if not data["courses"]:                             # 값(성적·과목명)은 로그에 남기지 않는다
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"fetchedAt": datetime.now().isoformat(timespec="seconds"), **data}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
