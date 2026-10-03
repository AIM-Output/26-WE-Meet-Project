"""③ 내 단과대학 · ④ 내 학부 홈페이지 공지 — K2Web Wizard CMS (전남대 단과대학·학부 사이트가 모두 같은 구조).

URL 패턴 /bbs/<site>/<board>/artclList.do (notice_agent/references/site-structure.md §2).
  목록  table.board-table tbody tr → td.td-subject a[href=/bbs/<site>/<board>/<글번호>/artclView.do], td.td-date(YYYY.MM.DD)
        tr.notice = 상단 고정(말머리 필터를 걸어도 섞여 온다)
  상세  .view-info h2.view-title, .view-con, .view-file a[href$=download.do]
어느 게시판을 읽을지는 k2web_discover 가 프로필의 소속 홈페이지에서 찾는다. 사용자가 게시판 주소를 직접 지정할 수도 있다.
말머리는 보통 bbsOpenWrdSeq, 일부 게시판은 bbsClSeq 로 거른다(categoryParam).
"""
from __future__ import annotations

import re
from urllib.parse import urlencode, urljoin

from ..textutil import parse_board_url  # noqa: F401  (주소 해석은 백엔드도 쓰므로 표준 라이브러리 쪽에 둔다)
from .base import FormatChanged, Http, Post, html_to_text
from .jnu_board import is_academic


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
            posted = None
            if d:
                dm = re.search(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", d.get_text())
                posted = f"{dm.group(1)}-{dm.group(2)}-{dm.group(3)}" if dm else None
            posts.setdefault(m.group(1), Post(post_id=m.group(1), title=a.get_text(" ", strip=True),
                                              url=urljoin(cfg["base"], a["href"]), posted_at=posted,
                                              pinned="notice" in (tr.get("class") or [])))
            found += 1
        if found == 0:
            break
    return list(posts.values())


def fetch_detail(post: Post, http: Http) -> Post:
    soup = http.soup(post.url)
    t = soup.select_one(".view-info h2.view-title") or soup.select_one("h2.view-title")
    if t:
        post.title = re.sub(r"\s+", " ", t.get_text(" ", strip=True))
    body_el = soup.select_one(".view-con")
    post.body = html_to_text(body_el)
    has_img = bool(body_el and body_el.select("img[src]"))
    post.image_only = has_img and len(re.sub(r"\s+", "", post.body)) < 40
    post.attachments = [{"name": a.get_text(" ", strip=True), "url": urljoin(post.url, a["href"])}
                        for a in soup.select(".view-file a[href]") if "download" in a["href"]]
    return post


def select(posts: list[Post], cfg: dict) -> list[Post]:
    # 말머리(학사)로 이미 거른 게시판이면 제목 필터를 약하게: 고정 공지만 제목으로 거른다
    if cfg.get("category"):
        return [p for p in posts if not p.pinned or is_academic(p.title, None)]
    return [p for p in posts if is_academic(p.title, None)]
