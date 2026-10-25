"""XpressEngine(XE) 게시판 — startup.jnu.ac.kr (전남대 창업보육센터 · 창업포털, 2026-10-25 실측).

https 인증서가 다른 이름으로 되어 있어(CN 불일치) 사이트가 안내하는 http 주소를 쓴다 — 공개 글을 읽기만 한다.
목록  GET /index.php?mid=<mid>&page=N → table.bd_lst tbody tr (tr.notice = 상단 고정) · td.title a
      (href 는 '/<mid>/<번호>' 또는 '/index.php?mid=<mid>&page=1&document_srl=<번호>' — 두 모양 다 받는다)
      목록에는 날짜 칸이 없다 → 상세에서 읽는다
상세  GET /<mid>/<번호> → .rd_hd h1(제목) · .rd_hd .date('2026.10.22 17:48') · .xe_content(본문) · a[href*=procFileDownload](첨부)
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import FormatChanged, Http, Post, clean_title, finish, ymd


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    posts: dict[str, Post] = {}
    for mid in cfg.get("mids", []):
        for page in range(1, pages + 1):
            soup = http.soup(f"{cfg['base']}/index.php", params={"mid": mid, "page": str(page)})
            if page == 1 and not soup.select_one("table.bd_lst"):
                raise FormatChanged(f"XE 게시판 목록(table.bd_lst)을 찾지 못했습니다: {mid}")
            found = 0
            for tr in soup.select("table.bd_lst tbody tr"):
                a = tr.select_one("td.title a[href]")
                m = (re.search(rf"/{re.escape(mid)}/(\d+)", a["href"]) or re.search(r"document_srl=(\d+)", a["href"])) if a else None
                if not m:
                    continue
                title = clean_title(a.get_text(" ", strip=True))
                cat = re.match(r"^\[([^\]]{1,14})\]", title)
                native = f"{mid}-{m.group(1)}"
                posts.setdefault(native, Post(
                    native_id=native, title=title, url=urljoin(cfg["base"], f"/{mid}/{m.group(1)}"), writer=cfg.get("org"),
                    category=cat.group(1) if cat else None, pinned="notice" in (tr.get("class") or [])))
                found += 1
            if found == 0:
                break
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    h = soup.select_one(".rd_hd h1")
    if h and h.get_text(strip=True):
        post.title = clean_title(h.get_text(" ", strip=True))
    d = soup.select_one(".rd_hd .date")
    post.posted_at = (ymd(d.get_text(" ", strip=True)) if d else None) or post.posted_at
    post.attachments = [{"name": a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, a["href"])}
                        for a in soup.select("a[href*=procFileDownload]")]
    return finish(post, soup.select_one(".xe_content") or soup.select_one(".rd_body"))
