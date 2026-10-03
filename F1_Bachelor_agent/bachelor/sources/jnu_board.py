"""② 학사 공지 — www.jnu.ac.kr 공지사항 › 학사안내 (board.aspx?boardID=5&cate=5).

구조는 notice_agent/references/site-structure.md §1 과 같다 (같은 ASP.NET 게시판, 분류만 다름).
  목록  table.board_list tr → td.title a[href] (글 번호 = key), td 작성자·작성일, span.label '공지'(상단 고정)
  상세  .board_view_wrap .view_head h3 / span[id$=lbl_WriteDate] / .view_body .con / .view_info_file a

2026-09 실측: 학사안내 분류에는 채용·특강·공모전도 섞여 올라온다 → 제목·작성 부서로 학사 글만 고른다(is_academic).
"""
from __future__ import annotations

import re
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from .base import FormatChanged, Http, Post, html_to_text

# 학사 일정이 들어 있을 만한 제목
ACADEMIC_TITLE = re.compile(
    r"수강|등록|납부|고지서|휴학|복학|성적|졸업|학위|계절\s*(?:학기|수업)|폐강|정정|취소|철회|전과|복수\s*전공|부\s*전공|"
    r"융합\s*전공|연계\s*전공|전공\s*(?:배정|변경)|교직|학점|교과구분|수업|시험|개강|종강|휴업|보강|학사\s*일정|학적|학생증")
# 제목에 이것이 있으면 학사 일정이 아니다 (채용·행사 홍보)
NOT_ACADEMIC = re.compile(r"채용|초빙|모집\s*요강|입학\s*전형|합격자|공모전|특강|세미나|워크숍|서포터즈|경진\s*대회|대회|"
                          r"실원\s*모집|연구원\s*모집|연구생\s*모집|현황\s*파악|박람회|콘서트|캠프")
# 학사 일정을 올리는 부서 (제목 키워드가 약해도 이 부서 글이면 본다)
ACADEMIC_WRITERS = ("학사과", "재무과", "교육혁신정책실", "학생과")


def is_academic(title: str, writer: str | None) -> bool:
    if NOT_ACADEMIC.search(title):
        return False
    return bool(ACADEMIC_TITLE.search(title)) or (writer or "").strip() in ACADEMIC_WRITERS


def _list_url(cfg: dict, page: int) -> str:
    params = dict(cfg.get("params", {}))
    params["page"] = str(page)
    return f"{cfg['base']}{cfg['list_path']}?{urlencode(params)}"


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
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
            href = urljoin(cfg["base"] + cfg["list_path"], a["href"])
            pid = parse_qs(urlparse(href).query).get("key", [""])[0]
            if not pid:
                continue
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            posted = next((t for t in tds if re.fullmatch(r"\d{4}-\d{2}-\d{2}", t)), None)
            label = tr.select_one("span.label")
            posts.setdefault(pid, Post(post_id=pid, title=a.get_text(" ", strip=True), url=href, posted_at=posted,
                                       writer=tds[2] if len(tds) >= 4 else None,
                                       pinned=bool(label and "공지" in label.get_text())))
            found += 1
        if found == 0:
            break
    return list(posts.values())


def fetch_detail(post: Post, http: Http) -> Post:
    soup = http.soup(post.url)
    view = soup.select_one(".board_view_wrap") or soup
    title_el = view.select_one(".view_head h3") or view.select_one(".view_head .title")
    date_el = view.select_one("span[id$=lbl_WriteDate]")
    body_el = view.select_one(".view_body .con") or view.select_one(".view_body")
    if title_el:
        post.title = title_el.get_text(" ", strip=True)
    if date_el:
        m = re.search(r"(\d{4})[.\-](\d{2})[.\-](\d{2})", date_el.get_text())
        if m:
            post.posted_at = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    post.body = html_to_text(body_el)
    has_img = bool(body_el and body_el.select("img[src]"))
    post.image_only = has_img and len(re.sub(r"\s+", "", post.body)) < 40
    post.attachments = []
    for a in view.select(".view_info_file a[href]"):
        href = a["href"]
        if "preview" in " ".join(a.get("class", [])) or "download" not in href.lower():
            continue
        post.attachments.append({"name": a.get_text(" ", strip=True), "url": urljoin(post.url, href)})
    return post


def select(posts: Iterable[Post]) -> list[Post]:
    return [p for p in posts if is_academic(p.title, p.writer)]
