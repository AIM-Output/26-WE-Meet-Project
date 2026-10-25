"""K2Web Wizard 게시판 — 전남대 단과대학·학과·사업단 사이트 대부분 (/bbs/<site>/<board>/artclList.do).

목록  table.board-table tbody tr → td.td-subject a[href=…/<글번호>/artclView.do], td.td-date(YYYY.MM.DD), td.td-write
      tr.notice = 상단 고정(말머리 필터를 걸어도 섞여 온다)
      말머리 탭 jf_searchArtcl('bbsOpenWrdSeq'|'bbsClSeq', '<번호>') — 인공지능학부 '장학 237'·경영학부 '장학관련 1908'·
      컴퓨터정보통신공학과 '장학 1988' 처럼 장학 말머리가 있는 학과가 있다 (2026-10-09 실측 15곳 중 3곳)
상세  .view-info h2.view-title · .view-con · .view-file a[href*=download] · dl(dt 작성일·작성자)

discover(homepage) — 내 단과대학·학과 홈페이지에서 장학 게시판 찾기 (F1 k2web_discover 와 같은 길, 고르는 것만 '장학'):
  1) 메뉴에 '장학' 이 들어간 게시판 메뉴가 있으면 그것 (그린바이오 '장학금' · 총동창회 '장학사업' 같은 곳)
  2) 없으면 '공지' 메뉴 → 그 게시판의 말머리 중 '장학' 이 있으면 그 말머리만
  3) 없으면 공지 게시판 전체 + 제목 어휘로 거른다 · 메뉴에 공지가 없으면 첫 화면 '더보기' 게시판
"""
from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from typing import Optional
from urllib.parse import urlencode, urljoin, urlparse

from .base import FormatChanged, Http, Post, clean_title, finish, ymd

_MENU = re.compile(r"/([\w-]+)/(\d+)/subview\.do")
_BOARD = re.compile(r"/bbs/([\w-]+)/(\d+)/")
_TAB = re.compile(r"jf_searchArtcl\(\s*'(bbsOpenWrdSeq|bbsClSeq)'\s*,\s*'(\d+)'\s*\)[^>]*>\s*([^<]{1,20}?)\s*<")
_NOT_NOTICE = re.compile(r"대학원|학생회|BK|입학|채용|세미나|뉴스|언론|보도|갤러리|연구실|자료실")


def _list_url(cfg: dict, page: int) -> str:
    params = {"page": str(page)}
    if cfg.get("category"):
        params[cfg.get("categoryParam") or "bbsOpenWrdSeq"] = str(cfg["category"])
    return f"{cfg['base']}/bbs/{cfg['site']}/{cfg['board']}/artclList.do?{urlencode(params)}"


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    posts: dict[str, Post] = {}
    for page in range(1, pages + 1):
        soup = http.soup(_list_url(cfg, page))
        if page == 1 and not soup.select_one("table.board-table"):
            raise FormatChanged("K2Web 게시판 목록 표(table.board-table)를 찾지 못했습니다")
        found = 0
        for tr in soup.select("table.board-table tbody tr"):
            a = tr.select_one("td.td-subject a[href]")
            if a is None:
                continue
            m = re.search(r"/(\d+)/artclView\.do", a["href"])
            if not m:
                continue
            d = tr.select_one("td.td-date")
            w = tr.select_one("td.td-write")
            title = clean_title(a.get_text(" ", strip=True))
            cat = re.match(r"^\[([^\]]{1,14})\]", title)
            posts.setdefault(m.group(1), Post(
                native_id=m.group(1), title=title, url=urljoin(cfg["base"], a["href"]),
                posted_at=ymd(d.get_text()) if d else None, writer=w.get_text(" ", strip=True) if w else None,
                category=cat.group(1) if cat else None, pinned="notice" in (tr.get("class") or [])))
            found += 1
        if found == 0:
            break
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    t = soup.select_one(".view-info h2.view-title") or soup.select_one("h2.view-title")
    if t:
        post.title = clean_title(t.get_text(" ", strip=True)) or post.title
    meta = {}
    for dl in soup.select("dl"):
        dt, dd = dl.select_one("dt"), dl.select_one("dd")
        if dt and dd:
            meta[dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
    post.writer = meta.get("작성자") or post.writer
    post.posted_at = ymd(meta.get("작성일", "")) or post.posted_at
    post.attachments = [{"name": a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, a["href"])}
                        for a in soup.select(".view-file a[href]") if "download" in a["href"]]
    return finish(post, soup.select_one(".view-con"))


# ── 내 단과대학·학과 게시판 찾기 ──────────────────────────────

def _menus(html: str, base: str) -> list[tuple[int, str, str]]:
    """첫 화면 메뉴 → [(점수, 글, 주소)] 높은 순. 장학 메뉴 > 학부·학과 공지 > 공지사항."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(base).netloc
    out, seen = [], set()
    for i, a in enumerate(soup.select("a[href]")):
        url = urljoin(base, a["href"])
        if urlparse(url).netloc != host or not _MENU.search(url) or url in seen:
            continue
        t = re.sub(r"\s+", "", a.get_text(" ", strip=True))
        if not t or len(t) > 16 or _NOT_NOTICE.search(t):
            continue
        if "장학" in t and "제도" not in t and "안내" not in t:
            score = 40
        elif re.search(r"(?<!인)공지", t):
            score = 20 if re.search(r"학부|학과|학사|학생", t) else 10
        else:
            continue
        seen.add(url)
        out.append((score - i / 10000, t, url))
    return sorted(out, key=lambda x: -x[0])


def _board_ref(html: str) -> Optional[tuple[str, str]]:
    refs = Counter(_BOARD.findall(html))
    return refs.most_common(1)[0][0] if refs else None


def categories(html: str) -> list[dict]:
    return [{"param": p, "value": v, "label": re.sub(r"\s+", " ", lab).strip()} for p, v, lab in _TAB.findall(html)]


def pick_scholarship_tab(tabs: list[dict]) -> Optional[dict]:
    return next((t for t in tabs if "장학" in t["label"] and not re.search(r"대학원|석사|박사", t["label"])), None)


def discover(homepage: str, http: Http) -> dict:
    """홈페이지 → {base, site, board, boardLabel, boardUrl, category, categoryParam, categoryLabel, filter, discoveredAt}.
    filter = all(장학 게시판·말머리라 다 장학) | keyword(공지 전체 → 제목으로 거름)."""
    r = http.get(homepage)
    base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
    label, ref, scholarship_menu = None, None, False
    for score, text, url in _menus(r.text, r.url)[:4]:
        ref = _board_ref(http.get(url).text)
        if ref:
            label, scholarship_menu = text, score >= 40
            break
    if not ref:
        more = list(dict.fromkeys(re.findall(r"/bbs/([\w-]+)/(\d+)/artclList\.do", r.text)))
        if not more:
            raise FormatChanged(f"{base} 에서 공지 게시판을 찾지 못했습니다 — 주소를 직접 지정해 주세요")
        ref, label = more[0], "첫 화면 공지"
    site, board = ref
    list_url = f"{base}/bbs/{site}/{board}/artclList.do"
    tab = None if scholarship_menu else pick_scholarship_tab(categories(http.get(list_url).text))
    return {
        "base": base, "site": site, "board": board, "boardLabel": label, "boardUrl": list_url,
        "category": tab["value"] if tab else None, "categoryParam": tab["param"] if tab else None,
        "categoryLabel": tab["label"] if tab else None,
        "filter": "all" if (scholarship_menu or tab) else "keyword",
        "discoveredAt": datetime.now().isoformat(timespec="seconds"),
    }
