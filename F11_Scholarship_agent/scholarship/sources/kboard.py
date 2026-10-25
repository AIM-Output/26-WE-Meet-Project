"""워드프레스 KBoard 게시판 — sojoong.kr (전남대 소프트웨어중심대학사업단, 2026-10-25 실측).

목록  GET <path>?pageid=N&mod=list → .kboard-list tbody tr (tr.kboard-list-notice = 상단 고정)
      a[href*="uid="] · .custom-title(제목, 같은 클래스가 두 겹) · .kboard-list-date(YYYY.MM.DD)
      cfg.paths = 같은 사이트의 KBoard 게시판들 (공지사항 /notice/notice-board/ — '소중마일리지'는 게시판이 아닌 안내 표라 넣지 않는다)
상세  GET <path>?uid=<n>&mod=document → .kboard-title · .detail-date('작성일 2026-10-19 13:25') · .kboard-content · .kboard-attach a
글 id 는 '<게시판 경로>-<uid>' — 게시판마다 uid 가 따로 매겨질 수 있어서.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from .base import FormatChanged, Http, Post, clean_title, finish, ymd


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    posts: dict[str, Post] = {}
    for path in cfg.get("paths", []):
        url = f"{cfg['base']}{path}"
        for page in range(1, pages + 1):
            soup = http.soup(url, params={"pageid": str(page), "mod": "list"})
            if page == 1 and not soup.select_one(".kboard-list"):
                raise FormatChanged(f"KBoard 목록(.kboard-list)을 찾지 못했습니다: {path}")
            found = 0
            for tr in soup.select(".kboard-list tbody tr"):
                a = tr.select_one("a[href*='uid=']")
                if a is None:
                    continue
                uid = (parse_qs(urlparse(a["href"]).query).get("uid") or [""])[0]
                if not uid:
                    continue
                t = tr.select(".custom-title")
                title = clean_title((t[-1] if t else a).get_text(" ", strip=True))
                d = tr.select_one(".kboard-list-date")
                cat = re.match(r"^\[([^\]]{1,14})[\]}]", title)
                native = f"{path.strip('/').replace('/', '-')}-{uid}"
                posts.setdefault(native, Post(
                    native_id=native, title=title, url=urljoin(url, a["href"]),
                    posted_at=ymd(d.get_text(" ", strip=True)) if d else None, writer=cfg.get("org"),
                    category=cat.group(1) if cat else None, pinned="kboard-list-notice" in (tr.get("class") or [])))
                found += 1
            if found == 0:
                break
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    t = soup.select_one(".kboard-title")
    if t and t.get_text(strip=True):
        post.title = clean_title(t.get_text(" ", strip=True))
    d = soup.select_one(".detail-date")
    post.posted_at = (ymd(d.get_text(" ", strip=True)) if d else None) or post.posted_at
    post.attachments = [{"name": a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, a["href"])}
                        for a in soup.select(".kboard-attach a[href]")]
    return finish(post, soup.select_one(".kboard-content") or soup.select_one(".content-view"))
