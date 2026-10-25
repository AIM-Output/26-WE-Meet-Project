"""CNU Events — events.jnu.ac.kr 전남대 행사일정 (2026-10-25 실측). 학교 전체의 특강·세미나·워크숍·박람회·공연·전시·모집 행사가 모인다.

목록  GET /Search.aspx?mode=cate&query= → div.media (지금 걸려 있는 행사 전부 — 페이지 나눔이 없다)
      span.u-label(분류: 세미나·공연·기타 …) · h3 a[href="/EventView.aspx?eventId=<n>"](제목)
      li > i.fa-calendar(기간 '2026.10.22.(목) ~ 2026.11.10.(화)(20일간)') · i.fa-map-marker(장소) · i.fa-building(주최)
상세  GET /EventView.aspx?eventId=<n> → '참여대상: …' · '행사방식 : …' 줄 · '주최 및 주관 / <부서>' · '등록일 YYYY.MM.DD' ·
      a[download](첨부) · h3 '행사 상세 정보 :' 를 담은 칸(본문)
본문 맨 앞에 '기간 : <행사 기간>' 줄을 붙인다 — 신청 기간이 따로 없으면 행사 기간의 끝을 마감으로 읽게(행사가 끝나면 접힌다).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .base import FormatChanged, Http, Post, body_images, clean_title, html_to_text, ymd


def _icon_text(card, icon: str) -> str:
    i = card.select_one(f"i.{icon}")
    return re.sub(r"\s+", " ", i.parent.get_text(" ", strip=True)).strip() if i and i.parent else ""


def list_posts(cfg: dict, http: Http, pages: int) -> list[Post]:
    soup = http.soup(f"{cfg['base']}/Search.aspx", params={"mode": "cate", "query": ""})
    cards = [c for c in soup.select("div.media") if c.select_one("a[href*='EventView.aspx?eventId=']")]
    if not cards and not soup.select_one("a[href*='EventView.aspx']"):
        raise FormatChanged("행사 목록(div.media)을 찾지 못했습니다")
    posts: dict[str, Post] = {}
    for c in cards:
        a = c.select_one("h3 a[href*='eventId=']") or c.select_one("a[href*='eventId=']")
        m = re.search(r"eventId=(\d+)", a["href"])
        if not m:
            continue
        label = c.select_one("span.u-label")
        when, place, org = _icon_text(c, "fa-calendar"), _icon_text(c, "fa-map-marker"), _icon_text(c, "fa-building")
        posts.setdefault(m.group(1), Post(
            native_id=m.group(1), title=clean_title(a.get_text(" ", strip=True)), url=urljoin(cfg["base"], a["href"]),
            writer=org or None, category=label.get_text(strip=True) if label else None,
            extra={"when": when, "place": place}))
    return list(posts.values())


def fetch_detail(post: Post, cfg: dict, http: Http) -> Post:
    soup = http.soup(post.url)
    for bad in soup.select("script, style"):
        bad.decompose()
    flat = re.sub(r"\s+", " ", soup.get_text(" ", strip=True))
    m = re.search(r"주최 및 주관\s*/\s*([^/]{2,40}?)\s+(?:등록일|<)", flat)
    if m:
        post.writer = m.group(1).strip()
    m = re.search(r"등록일\s*(20\d{2}\.\d{1,2}\.\d{1,2})", flat)
    post.posted_at = ymd(m.group(1)) if m else post.posted_at
    facts = [f"기간 : {post.extra['when']}" if post.extra.get("when") else "",
             f"장소 : {post.extra['place']}" if post.extra.get("place") else ""]
    for lab in ("참여대상", "행사방식"):
        mm = re.search(rf"{lab}\s*[:：]\s*([^:：]{{1,60}}?)(?=\s+(?:행사방식|온라인 참여|행사 웹사이트|\d{{2,4}}-\d|Apple|Google|공유하기)|$)", flat)
        if mm:
            facts.append(f"{lab} : {mm.group(1).strip()}")
    h = next((x for x in soup.select("h3") if "행사 상세 정보" in x.get_text()), None)
    body = html_to_text(h.parent) if h is not None else ""
    body = re.sub(r"^\s*행사 상세 정보\s*[:：]?\s*", "", body)
    post.body = "\n".join(x for x in (*facts, body) if x).strip()
    post.image_only = bool(h is not None and h.parent.select("img[src]")) and len(re.sub(r"\s+", "", body)) < 40
    post.images = body_images(post, h.parent if h is not None else None)
    post.attachments = [{"name": a.get("download") or a.get_text(" ", strip=True) or "첨부", "url": urljoin(post.url, a["href"])}
                        for a in soup.select("a[download][href]")]
    return post
