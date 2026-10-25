"""coursemos 게시판 — 교육혁신본부(ile.jnu.ac.kr) · 성장마루 비교과 플랫폼(grow.jnu.ac.kr). 2026-10-09 실측.

목록  GET <path>?p=N → ul[data-role=table] li.tbody → span.title a[href=<path>/view/<번호>] · time[datetime] · span.name
      li.tbody.notice = 상단 고정
상세  GET <path>/view/<번호> → <title> '제목 - 전남대학교 교육혁신본부' · time[datetime] · article(본문)
      첨부 a[href*=/attachment/download]
      교육혁신본부 학습지원 공지(/ko/learning/notice) 상세는 **로그인해야 열린다**(2026-10-10 실측 — '회원로그인이 필요합니다',
      <title> 은 '공지사항 - …') → 목록의 제목·날짜만 남기고 본문은 비운다(extra.login). 학부 공지(/ko/division/notice)는 공개.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import FormatChanged, Http, Post, clean_title, finish, ymd


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    posts: dict[str, Post] = {}
    for path in cfg.get("paths", []):
        for page in range(1, pages + 1):
            soup = http.soup(f"{cfg['base']}{path}", params={"p": str(page)})
            rows = soup.select("ul[data-role=table] li.tbody")
            if page == 1 and not soup.select_one("ul[data-role=table]"):
                raise FormatChanged(f"게시판 목록(ul[data-role=table])을 찾지 못했습니다: {path}")
            found = 0
            for li in rows:
                a = li.select_one("span.title a[href]")
                m = re.search(r"/view/(\d+)", a["href"]) if a else None
                if not m:
                    continue
                t = li.select_one("time[datetime]")
                w = li.select_one("span.name")
                native = f"{path.strip('/').replace('/', '-')}-{m.group(1)}"
                posts.setdefault(native, Post(
                    native_id=native, title=clean_title(a.get_text(" ", strip=True)),
                    url=urljoin(cfg["base"], re.sub(r"\?.*$", "", a["href"])),
                    posted_at=ymd(t.get("datetime") if t else None), writer=w.get_text(" ", strip=True) if w else None,
                    pinned="notice" in (li.get("class") or [])))
                found += 1
            if found == 0:
                break
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    body = soup.select_one("article") or soup.select_one(".content")
    if body is None and "로그인이 필요" in soup.get_text(" ", strip=True)[:4000]:
        post.extra["login"] = True               # 로그인 화면 — 목록 제목을 그대로 둔다(<title> 이 '공지사항')
        return post
    if soup.title:
        t = clean_title(soup.title.get_text(" ", strip=True).rsplit(" - ", 1)[0])
        if t and t not in ("공지사항", "공지", "게시판"):
            post.title = t
    tm = soup.select_one("time[datetime]")
    post.posted_at = ymd(tm.get("datetime") if tm else None) or post.posted_at
    post.attachments = [{"name": a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, a["href"])}
                        for a in soup.select("a[href*='/attachment/download']")]
    return finish(post, body)
