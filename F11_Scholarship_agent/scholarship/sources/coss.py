"""혁신융합대학(COSS) 사업단 사이트 — aicoss.kr(AICOSS) · jnu.nccoss.kr(차세대통신) · futurecar.kr(미래차 부트캠프). 같은 업체 CMS.

목록  GET <listPath>?page=N → table.basicBoard tbody tr → a[href="javascript:movePageView(<id>)"]
      strong.cutText(제목) · span.boardCat-wrap > span(분류: 학생지원·경진대회 …) · td.mobileNone(YYYY.MM.DD)
      input#b_link_<id> 값이 "0" 이 아니면 외부 링크 글 (본문 없음)
      cfg.cate = 말머리(대학) — AICOSS 는 7개 대학 연합 게시판이라 `?cate=전남대학교` 로 전남대 글만 (2026-10-25 실측:
      말머리 없이 읽으면 영진전문대·성균관대 글이 섞여 'AICOSS-UTAS 프로그램'처럼 남의 학교 모집이 들어왔다)
상세  GET <viewPath><id> → section.viewContainer h3 · .viewContainer-info li(일시) · .viewContainer-content
      viewPath 기본 /www/notice/view/ — 미래차 부트캠프는 /notice/view/
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import FormatChanged, Http, Post, clean_title, finish, ymd

VIEW_RE = re.compile(r"movePageView\((\d+)\)")


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    posts: dict[str, Post] = {}
    url = f"{cfg['base']}{cfg.get('listPath', '/www/notice/')}"
    view = cfg.get("viewPath", "/www/notice/view/")
    for page in range(1, pages + 1):
        soup = http.soup(url, params={"page": str(page), "searchOption": "", "searchItem": "", "cate": cfg.get("cate", "")})
        if page == 1 and not soup.select_one("table.basicBoard"):
            raise FormatChanged("게시판 목록 표(table.basicBoard)를 찾지 못했습니다")
        found = 0
        for tr in soup.select("table.basicBoard tbody tr"):
            a = tr.select_one("a[href*=movePageView]")
            m = VIEW_RE.search(a["href"]) if a else None
            if not m:
                continue
            native = m.group(1)
            title_el = a.select_one("strong.cutText") or a
            cat_el = a.select_one("span.boardCat-wrap > span")
            link = tr.select_one(f"#b_link_{native}")
            external = link.get("value") if link is not None else "0"
            dates = [ymd(td.get_text()) for td in tr.select("td.mobileNone") if ymd(td.get_text())]
            is_ext = bool(external and external != "0" and external.startswith("http"))
            posts.setdefault(native, Post(
                native_id=native, title=clean_title(title_el.get_text(" ", strip=True)),
                url=external if is_ext else f"{cfg['base']}{view}{native}",
                posted_at=dates[0] if dates else None, category=cat_el.get_text(strip=True) if cat_el else None,
                writer=cfg.get("org"), extra={"external": is_ext}))
            found += 1
        if found == 0:
            break
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    if post.extra.get("external"):
        return post                              # 외부 링크 글 — 본문 없이 제목·링크만
    soup = http.soup(post.url)
    view = soup.select_one("section.viewContainer") or soup
    t = view.select_one("h3")
    if t:
        post.title = clean_title(t.get_text(" ", strip=True)) or post.title
    d = view.select_one(".viewContainer-info li")
    post.posted_at = (ymd(d.get_text()) if d else None) or post.posted_at
    post.attachments = [{"name": a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, a["href"])}
                        for a in view.select("a[href]")
                        if any(k in a["href"].lower() for k in ("download", "/upload/file", "filedown"))]
    return finish(post, view.select_one(".viewContainer-content"))
