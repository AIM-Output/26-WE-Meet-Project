"""단과대학·학부(과) 홈페이지 목록 수집 — 전남대 대표 홈페이지의 '대학·학부' 안내 (2026-09-29 실측).

  www.jnu.ac.kr 첫 화면
    · 아래쪽 '대학 / 대학원 › 대학·학부' 링크 모음: 단과대학 이름 → 홈페이지 (https://cvg.jnu.ac.kr/ …)
    · 메뉴 '대학·대학원 › 대학·학부(과)': 단과대학마다 /MainUniversity/University/Uni_<이름> 안내 페이지
  단과대학 안내 페이지 (/MainUniversity/University/Uni_Convergence …)
    <table><caption>학부(과)</caption> 대학 | 학부(과) | 전화번호 | 홈페이지('홈페이지 바로가기' 링크)
요청은 단과대학 수 + 1번(약 20번, 1.5초 간격). 결과는 directory/homepages.json — 저장소에 넣어 둔다.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Callable
from urllib.parse import urljoin

from .base import FormatChanged, Http

MAIN = "https://www.jnu.ac.kr/"
_UNI = re.compile(r"/MainUniversity/University/Uni_\w+$")
_ROOT_HOST = re.compile(r"^https?://[\w.-]+\.jnu\.ac\.kr", re.I)


def _root(url: str) -> str:
    """'http://aisw.jnu.ac.kr/' → 'https://aisw.jnu.ac.kr' (학교 하위 사이트는 모두 https 로 넘어간다)."""
    m = _ROOT_HOST.match(url.strip())
    return re.sub(r"^http://", "https://", m.group(0).lower()) if m else url.strip()


def parse_main(html: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    """첫 화면 → ({단과대학 이름: 홈페이지}, [(단과대학 이름, 안내 페이지 주소)])."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    homes: dict[str, str] = {}
    box = soup.select_one("#site_link_01_con") or soup
    for a in box.select("a[href]"):
        name, href = a.get_text(" ", strip=True), a["href"]
        if _ROOT_HOST.match(href) and re.search(r"(대학|학부)(\(\d+년\))?$", name) and "대학원" not in name:
            homes.setdefault(name, _root(href))
    pages: list[tuple[str, str]] = []
    seen = set()
    for a in soup.select("a[href]"):
        href, name = a["href"], a.get_text(" ", strip=True)
        if _UNI.search(href) and not href.endswith("Uni_Total") and re.search(r"(대학|학부)(\(\w+\))?$", name):
            if href not in seen:
                seen.add(href)
                pages.append((name, urljoin(MAIN, href)))
    return homes, pages


def parse_college_page(html: str) -> tuple[str | None, list[dict]]:
    """단과대학 안내 페이지 → (단과대학 홈페이지, [{name, homepage}]). '학부(과)' 표를 읽는다."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    table = None
    for t in soup.select("table"):
        cap = t.select_one("caption")
        heads = [th.get_text(strip=True) for th in t.select("thead th")]
        if (cap and "학부" in cap.get_text()) or "학부(과)" in heads:
            table = t
            break
    if table is None:
        return None, []
    heads = [th.get_text(strip=True) for th in table.select("thead th")]
    depts: list[dict] = []
    for tr in table.select("tbody tr"):
        tds = tr.select("td")
        # 첫 행은 '대학' 칸(rowspan)이 앞에 붙어 칸이 하나 더 많다
        if len(tds) == len(heads):
            tds = tds[1:]
        if not tds:
            continue
        name = tds[0].get_text(" ", strip=True)
        link = next((a["href"] for a in tr.select("a[href]") if _ROOT_HOST.match(a["href"])), None)
        if name:
            depts.append({"name": name, "homepage": _root(link) if link else None})
    college_home = next((_root(a["href"]) for a in soup.select("#content a[href], .content a[href]")
                         if _ROOT_HOST.match(a["href"]) and a.get_text(strip=True).startswith("http")), None)
    return college_home, depts


def crawl(http: Http, log: Callable[[str], None] = print) -> dict:
    homes, pages = parse_main(http.get(MAIN).text)
    if not pages:
        raise FormatChanged("대표 홈페이지에서 단과대학 안내 페이지를 찾지 못했습니다")
    colleges = []
    for name, url in pages:
        college_home, depts = parse_college_page(http.get(url).text)
        base = re.sub(r"\(.*?\)$", "", name)
        # 표 첫 칸에 단과대학 자체(소개 영상 링크 등)가 섞여 나오는 곳이 있다 — '○○대학…' 행은 뺀다
        if base.endswith("대학"):
            depts = [x for x in depts if not x["name"].startswith(base)]
        home = homes.get(name) or homes.get(base) or next((v for k, v in homes.items() if k.startswith(base)), None)
        colleges.append({"name": name, "homepage": home or college_home, "page": url, "departments": depts})
        log(f"  {name}: 홈페이지 {home or college_home or '없음'} · 학부(과) {len(depts)}")
    return {"updatedAt": datetime.now().isoformat(timespec="seconds"), "source": MAIN, "colleges": colleges}
