"""인공지능혁신융합대학사업단(AICOSS, aicoss.kr) 공지 수집기.  (references/site-structure.md §3)

목록  GET /www/notice/?page=N&searchOption=<분류>&searchItem=<검색어>&cate=
      table.basicBoard tbody tr → a[href="javascript:movePageView(<id>)"], strong.cutText(제목),
      span.boardCat-wrap > span(분류: 글로벌·교과·비교과·행사·경진대회·학생지원·기자재·AICOSS레터·기타),
      td.mobileNone(날짜 YYYY.MM.DD). input#b_link_<id> 값이 "0" 이 아니면 외부 링크 글.
상세  GET /www/notice/view/<id> → section.viewContainer h3 / .viewContainer-info li(일시) / .viewContainer-content
      본문이 에디터 이미지(/upload/editor/…)로만 된 글이 많다.
장학 페이지 /www/program/scholarship 는 성과형·근로·성적우수 장학의 상시 안내(공지 아님).
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .. import config as C
from ..schemas import Attachment
from ..textutil import html_to_text, parse_date
from .base import BaseSource, ListItem

VIEW_RE = re.compile(r"movePageView\((\d+)\)")


class AicossBoard(BaseSource):
    kind = "aicoss"

    def list_items(self, pages: int = C.LIST_PAGES) -> list[ListItem]:
        items: dict[str, ListItem] = {}
        list_url = f"{self.base}{self.cfg.get('list_path', '/www/notice/')}"
        for page in range(1, pages + 1):
            params = {"page": str(page), "searchOption": self.cfg.get("search_option", ""),
                      "searchItem": self.cfg.get("search_item", ""), "cate": ""}
            soup = self.http.soup(list_url, params=params)
            found = 0
            for tr in soup.select("table.basicBoard tbody tr"):
                a = tr.select_one("a[href*=movePageView]")
                if a is None:
                    continue
                m = VIEW_RE.search(a["href"])
                if not m:
                    continue
                native = m.group(1)
                title_el = a.select_one("strong.cutText") or a
                cat_el = a.select_one("span.boardCat-wrap > span")
                link_input = tr.select_one(f"#b_link_{native}")
                external = link_input.get("value") if link_input is not None else "0"
                dates = [td.get_text(strip=True) for td in tr.select("td.mobileNone")
                         if re.fullmatch(r"\d{4}\.\d{2}\.\d{2}", td.get_text(strip=True))]
                url = (external if external and external != "0" and external.startswith("http")
                       else f"{self.base}/www/notice/view/{native}")
                item = ListItem(
                    native_id=native, title=title_el.get_text(" ", strip=True), url=url,
                    posted_at=(parse_date(dates[0]) or "")[:10] or None if dates else None,
                    category=cat_el.get_text(strip=True) if cat_el else None,
                    extra={"external": external not in (None, "", "0")},
                )
                items.setdefault(native, item)
                found += 1
            if found == 0:
                break
        return list(items.values())

    def fetch_detail(self, item: ListItem):
        if item.extra.get("external"):
            # 외부 링크 글은 본문이 없다 — 제목만으로 기록하고 사람이 링크를 확인하게 둔다
            return self.build_notice(item, body_text="", images=[], attachments=[])
        soup = self.http.soup(item.url)
        view = soup.select_one("section.viewContainer") or soup
        title_el = view.select_one("h3")
        date_el = view.select_one(".viewContainer-info li")
        body_el = view.select_one(".viewContainer-content")
        cat_el = view.select_one(".boardCat-wrap > span")
        attachments = []
        for a in view.select("a[href]"):
            href = a["href"]
            if any(k in href.lower() for k in ("download", "/upload/file", "filedown")):
                attachments.append(Attachment(name=a.get_text(" ", strip=True) or "attachment",
                                              url=urljoin(item.url, href)))
        images = [urljoin(item.url, img["src"]) for img in (body_el.select("img[src]") if body_el else [])]
        return self.build_notice(
            item,
            title=title_el.get_text(" ", strip=True) if title_el else None,
            posted_at=((parse_date(date_el.get_text(strip=True)) if date_el else None) or item.posted_at or "")[:10] or None,
            category=cat_el.get_text(strip=True) if cat_el else item.category,
            body_text=html_to_text(body_el),
            images=images,
            attachments=attachments,
        )
