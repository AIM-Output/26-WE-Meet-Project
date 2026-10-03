"""홈페이지 주소 하나 → 그 사이트의 학사 공지 게시판 찾기 (원천 ③·④). K2Web Wizard 공통 구조, 2026-09-29 실측.

전남대 단과대학·학부 홈페이지는 모두 같은 CMS(K2Web Wizard)다 (표본 12곳 전부).
  1. 첫 화면(/<site>/index.do)의 메뉴에서 '공지' 가 들어간 링크(/<site>/<메뉴번호>/subview.do)를 고른다.
     '학사공지' > '학부공지·학과공지·공지사항(학부)' > '공지사항' 순, '대학원·학생회·사업단·취업' 공지는 뺀다.
  2. 그 메뉴 화면은 게시판을 서버에서 그려 넣어 /bbs/<site>/<게시판번호>/ 가 한 종류만 나온다 → 게시판 번호.
     메뉴에서 못 찾으면 첫 화면의 '더보기'(/bbs/<site>/<번호>/artclList.do) 중 첫째를 쓴다.
  3. 게시판 목록(artclList.do)의 말머리 탭 `jf_searchArtcl('bbsOpenWrdSeq', '236')` 중 '학사' 가 있으면 그것만 본다.
     없으면 게시판 전체를 받고 제목으로 학사 글을 거른다(k2web.select → is_academic).
요청은 보통 3번(첫 화면 · 메뉴 화면 · 게시판 목록), 메뉴 화면에 게시판이 없으면 다음 후보로 최대 5번.
실측(2026-09-29): 인공지능학부 → 공지사항(말머리 '학사'), 기계공학부 → 공지사항(학부), AI융합대학·공과대학·전자컴퓨터공학부·경영대학 →
공지사항, 수산해양대학 → 메뉴에 없어 첫 화면 '더보기'.
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

from .base import FormatChanged, Http

_MENU = re.compile(r"/([\w-]+)/(\d+)/subview\.do")
_BOARD = re.compile(r"/bbs/([\w-]+)/(\d+)/")
_TAB = re.compile(r"jf_searchArtcl\(\s*'(bbsOpenWrdSeq|bbsClSeq)'\s*,\s*'(\d+)'\s*\)[^>]*>\s*([^<]{1,20}?)\s*<")
_EXCLUDE = re.compile(r"대학원|학생회|사업|BK|취업|입학|채용|장학|행사|세미나|뉴스|언론|보도|동문|연구실|자료실|갤러리|국제")


def _score(text: str) -> Optional[int]:
    t = re.sub(r"\s+", "", text)
    # '인공지능' 에도 '공지' 가 들어 있다 ('인공지능학부' 메뉴를 공지로 오인하지 않게)
    if not re.search(r"(?<!인)공지", t) or len(t) > 16 or _EXCLUDE.search(t):
        return None
    if "학사" in t:
        return 30
    if re.search(r"학부|학과|학생", t):
        return 20
    if t in ("공지사항", "공지"):
        return 10
    return 5


def menu_candidates(html: str, base: str) -> list[tuple[int, int, str, str]]:
    """첫 화면 → [(점수, 메뉴 순서, 링크 글, 메뉴 주소)] 점수 높은 순."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(base).netloc
    out, seen = [], set()
    for i, a in enumerate(soup.select("a[href]")):
        url = urljoin(base, a["href"])
        if urlparse(url).netloc != host or not _MENU.search(url):
            continue
        s = _score(a.get_text(" ", strip=True))
        if s is None or url in seen:
            continue
        seen.add(url)
        out.append((s, i, a.get_text(" ", strip=True), url))
    return sorted(out, key=lambda x: (-x[0], x[1]))


def board_ref(html: str) -> Optional[tuple[str, str]]:
    """메뉴 화면 → (site, 게시판 번호). 여러 개면 가장 많이 나온 것."""
    refs = Counter(_BOARD.findall(html))
    return refs.most_common(1)[0][0] if refs else None


def more_links(html: str) -> list[tuple[str, str]]:
    """첫 화면의 '더보기' 게시판 (site, 번호) — 메뉴에서 못 찾았을 때."""
    return list(dict.fromkeys(re.findall(r"/bbs/([\w-]+)/(\d+)/artclList\.do", html)))


def categories(html: str) -> list[dict]:
    """게시판 목록 → 말머리 탭 [{param, value, label}]."""
    return [{"param": p, "value": v, "label": re.sub(r"\s+", " ", lab).strip()} for p, v, lab in _TAB.findall(html)]


def pick_category(tabs: list[dict]) -> Optional[dict]:
    exact = [t for t in tabs if t["label"] == "학사"]
    loose = [t for t in tabs if "학사" in t["label"] and not re.search(r"대학원|석사|박사", t["label"])]
    return (exact or loose or [None])[0]


def discover(homepage: str, http: Http) -> dict:
    """홈페이지 → {base, site, board, boardLabel, boardUrl, category, categoryParam, categoryLabel, discoveredAt}."""
    r = http.get(homepage)
    base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
    label, ref = None, None
    for _score_, _i, text, url in menu_candidates(r.text, r.url)[:3]:
        ref = board_ref(http.get(url).text)
        if ref:
            label = text
            break
    if not ref:
        more = more_links(r.text)
        if not more:
            raise FormatChanged(f"{base} 에서 공지 게시판을 찾지 못했습니다 — 주소를 직접 지정해 주세요")
        ref, label = more[0], "첫 화면 공지"
    site, board = ref
    list_url = f"{base}/bbs/{site}/{board}/artclList.do"
    cat = pick_category(categories(http.get(list_url).text))
    return {
        "base": base, "site": site, "board": board, "boardLabel": label, "boardUrl": list_url,
        "category": cat["value"] if cat else None, "categoryParam": cat["param"] if cat else None,
        "categoryLabel": cat["label"] if cat else None,
        "discoveredAt": datetime.now().isoformat(timespec="seconds"),
    }
