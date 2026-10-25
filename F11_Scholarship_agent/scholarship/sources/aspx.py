"""전남대 ASP.NET 게시판 — 대표 홈페이지 공지(board.aspx, 글 번호 key) · 국제협력본부·취업진로포털(Board.aspx, 글 번호 Seq).

2026-10-09 실측 (notice_agent/references/site-structure.md §1·§5 와 같다)
  목록  table.board_list tr → td.title a[href] (글 번호는 URL 의 key= / Seq=), 셋째 칸 작성자(부서), YYYY-MM-DD 칸
        span.label '공지' = 상단 고정(매 페이지 반복 → 번호로 한 번만)
  상세  .board_view_wrap  .view_head h3|.title · span[id$=lbl_Writer|lbl_name] · span[id$=lbl_WriteDate|lbl_date]
        첨부 .view_info_file a(download / ByteToFile) · 본문 .view_body .con (이미지뿐인 공지가 많다)
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from .base import FormatChanged, Http, Post, clean_title, finish, ymd


def _list_url(cfg: dict, page: int) -> str:
    params = dict(cfg.get("params", {}))
    params[cfg.get("pageParam", "page")] = str(page)
    return f"{cfg['base']}{cfg['listPath']}?{urlencode(params)}"


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    id_param = cfg.get("idParam", "key")
    posts: dict[str, Post] = {}
    for page in range(1, pages + 1):
        soup = http.soup(_list_url(cfg, page))
        rows = soup.select("table.board_list tr")
        if page == 1 and not soup.select_one("table.board_list"):
            raise FormatChanged("게시판 목록 표(table.board_list)를 찾지 못했습니다")
        found = 0
        for tr in rows:
            a = tr.select_one("td.title a[href]")
            if a is None:
                continue
            href = urljoin(cfg["base"] + cfg["listPath"], a["href"])
            q = {k.lower(): v for k, v in parse_qs(urlparse(href).query).items()}
            native = (q.get(id_param.lower()) or [""])[0]
            if not native:
                continue
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            date = next((ymd(t) for t in tds if ymd(t)), None)
            writer = tds[2] if len(tds) >= 4 and not ymd(tds[2]) else None
            label = tr.select_one("span.label")
            posts.setdefault(native, Post(native_id=native, title=clean_title(a.get_text(" ", strip=True)), url=href,
                                          posted_at=date, writer=writer, category=cfg.get("categoryLabel"),
                                          pinned=bool(label and "공지" in label.get_text())))
            found += 1
        if found == 0:
            break
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    view = soup.select_one(".board_view_wrap") or soup
    title_el = view.select_one(".view_head h3") or view.select_one(".view_head .title")
    writer_el = view.select_one("span[id$=lbl_Writer], span[id$=lbl_name]")
    date_el = view.select_one("span[id$=lbl_WriteDate], span[id$=lbl_date]")
    body_el = view.select_one(".view_body .con") or view.select_one(".view_body")
    if title_el is not None:
        for st in title_el.select("strong"):
            st.extract()
        post.title = clean_title(title_el.get_text(" ", strip=True)) or post.title
    if writer_el is not None:
        for st in writer_el.select("strong"):
            st.extract()
        post.writer = writer_el.get_text(" ", strip=True) or post.writer
    if date_el is not None:
        post.posted_at = ymd(date_el.get_text(" ", strip=True)) or post.posted_at
    post.attachments = []
    for a in view.select(".view_info_file a[href]"):
        if "preview" in " ".join(a.get("class", [])):
            continue
        href = a["href"]
        if "download" not in href.lower() and "bytetofile" not in href.lower():
            continue
        post.attachments.append({"name": a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, href)})
    return finish(post, body_el)
