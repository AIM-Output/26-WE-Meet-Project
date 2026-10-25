"""COSS 사업단 '프로그램 신청' 목록 — jnu.nccoss.kr/www/apply_program/ (차세대통신, 2026-10-25 실측). coss.py 와 같은 업체 CMS.

공지 게시판과 따로, 사업단이 운영하는 교과·비교과 프로그램을 신청 기간·진행 기간·상태와 함께 카드로 보여 준다.
목록  GET <listPath>?page=N → li > a[onclick="movePageView(<id>)"]
      .applyInfo-title strong(제목) · .applyInfo-solt em(교과과정·비교과과정·기타 — 말머리가 아니라 본문 '과정 :' 줄로) · .applyInfo-field i(분야)
      .applyInfo-date > span(em '신청기간 :' + span 'YYYY-MM-DD ~ YYYY-MM-DD') · .applyInfo-state i(신청중·신청마감·진행마감)
      게시일이 없다 → 신청 시작일을 게시일로 쓴다(오래된 프로그램 거르기용)
상세  GET <listPath>view/<id> → section.viewContainer (.applyProgram_info 표: 상태·대분류·분류·신청기간·진행기간·참여대상·선발기준 +
      .viewContainer-content 본문)
"""
from __future__ import annotations

import re

from .base import FormatChanged, Http, Post, clean_title, finish, html_to_text, ymd

VIEW_RE = re.compile(r"movePageView\((\d+)\)")


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    posts: dict[str, Post] = {}
    url = f"{cfg['base']}{cfg.get('listPath', '/www/apply_program/')}"
    for page in range(1, pages + 1):
        soup = http.soup(url, params={"page": str(page)})
        items = [a for a in soup.select("a[onclick*=movePageView]") if a.select_one(".applyInfo-title")]
        if page == 1 and not items and not soup.select_one(".applyInfo-title, .no-data, .noData"):
            raise FormatChanged("프로그램 신청 목록(.applyInfo-title)을 찾지 못했습니다")
        if not items:
            break
        for a in items:
            m = VIEW_RE.search(a.get("onclick", ""))
            if not m:
                continue
            native = m.group(1)
            dates = {}
            for sp in a.select(".applyInfo-date > span"):
                label = sp.select_one("em")
                val = sp.select_one("span")
                if label and val:
                    dates[re.sub(r"[\s:：]", "", label.get_text())] = val.get_text(" ", strip=True)
            state = a.select_one(".applyInfo-state i")
            slot = a.select_one(".applyInfo-solt em")
            lines = [f"신청기간 : {dates['신청기간']}" if dates.get("신청기간") else "",
                     f"진행기간 : {dates['진행기간']}" if dates.get("진행기간") else "",
                     f"상태 : {state.get_text(strip=True)}" if state else "",
                     f"과정 : {slot.get_text(strip=True)}" if slot else ""]
            posts.setdefault(native, Post(
                native_id=native, title=clean_title(a.select_one(".applyInfo-title").get_text(" ", strip=True)),
                url=f"{url}view/{native}", posted_at=ymd(dates.get("신청기간")),
                writer=cfg.get("org"),          # 교과과정·비교과과정은 말머리가 아니다 — 본문 '과정 :' 줄로만 남긴다(학사로 오인하지 않게)
                extra={"summary": "\n".join(x for x in lines if x), "state": state.get_text(strip=True) if state else None}))
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    view = soup.select_one("section.viewContainer") or soup
    t = view.select_one("h3")
    if t and t.get_text(strip=True):
        post.title = clean_title(t.get_text(" ", strip=True))
    post.attachments = [{"name": a.get_text(" ", strip=True) or "첨부", "url": a["href"] if a["href"].startswith("http")
                         else f"{cfg['base']}{a['href']}"}
                        for a in view.select("a[href]")
                        if any(k in a["href"].lower() for k in ("download", "/upload/file", "filedown"))]
    info = html_to_text(view.select_one(".applyProgram_info"))
    post = finish(post, view.select_one(".viewContainer-content"))
    post.body = "\n".join(x for x in (post.extra.get("summary", ""), info, post.body) if x).strip()
    return post
