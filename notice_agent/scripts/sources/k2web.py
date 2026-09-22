"""학과·단과대 홈페이지(K2Web Wizard) 게시판 수집기.

같은 구조를 쓰는 사이트 (references/site-structure.md §2)
  - aisw.jnu.ac.kr  /bbs/aisw/64/artclList.do   인공지능학부 공지 (말머리: 45 공지사항 · 236 학사 · 237 장학 · 238 행사 …)
  - cvg.jnu.ac.kr   /bbs/cvg/405/artclList.do   AI융합대학 공지 (말머리 없음)
  - sw.jnu.ac.kr, 그 외 /bbs/<site>/<board>/ 형태의 전남대 하위 사이트 대부분

목록  GET artclList.do?page=N[&bbsOpenWrdSeq=<말머리>]  → table.board-table tbody tr
      td.td-subject a[href=/bbs/<site>/<board>/<글번호>/artclView.do], td.td-write, td.td-date(YYYY.MM.DD)
상세  .view-info h2.view-title / .view-con / .view-file a[href$=download.do] / dl(dt 작성일·작성자) dd
RSS   /bbs/<site>/<board>/rssList.do?row=50 도 있다 (제목·링크·요약). 목록 파싱이 깨지면 대안으로 쓸 것.
"""
from __future__ import annotations

import re
from urllib.parse import urljoin

from .. import config as C
from ..schemas import Attachment
from ..textutil import html_to_text, parse_date
from .base import BaseSource, ListItem

ARTCL_RE = re.compile(r"/bbs/[^/]+/\d+/(\d+)/artclView\.do")


class K2WebBoard(BaseSource):
    kind = "k2web"

    @property
    def list_url(self) -> str:
        return f"{self.base}/bbs/{self.cfg['site']}/{self.cfg['board']}/artclList.do"

    def list_items(self, pages: int = C.LIST_PAGES) -> list[ListItem]:
        items: dict[str, ListItem] = {}
        for page in range(1, pages + 1):
            params = {"page": str(page)}
            if self.cfg.get("category"):
                params["bbsOpenWrdSeq"] = str(self.cfg["category"])
            soup = self.http.soup(self.list_url, params=params)
            rows = soup.select("table.board-table tbody tr")
            found = 0
            for tr in rows:
                a = tr.select_one("td.td-subject a[href]")
                if a is None:
                    continue
                href = urljoin(self.base, a["href"])
                m = ARTCL_RE.search(href)
                if not m:
                    continue
                native = m.group(1)
                date_el = tr.select_one("td.td-date")
                writer_el = tr.select_one("td.td-write")
                num_el = tr.select_one("td.td-num")
                title = a.get_text(" ", strip=True)
                cat = None
                mcat = re.match(r"^\[([^\]]{1,12})\]", title)      # 제목 앞 [장학] 말머리
                if mcat:
                    cat = mcat.group(1)
                item = ListItem(
                    native_id=native, title=title, url=href,
                    posted_at=parse_date(date_el.get_text(strip=True)) if date_el else None,
                    writer=writer_el.get_text(" ", strip=True) if writer_el else None,
                    category=cat,
                    extra={"pinned": bool(num_el and "공지" in num_el.get_text()),
                           "has_file": bool(tr.select_one("td.td-file img, td.td-file a, td.td-file span"))},
                )
                items.setdefault(native, item)
                found += 1
            if found == 0:
                break
        return list(items.values())

    def fetch_detail(self, item: ListItem):
        soup = self.http.soup(item.url)
        title_el = soup.select_one(".view-info h2.view-title, h2.view-title")
        body_el = soup.select_one(".view-con")
        meta = {}
        for dl in soup.select("dl"):
            dt, dd = dl.select_one("dt"), dl.select_one("dd")
            if dt and dd:
                meta[dt.get_text(strip=True)] = dd.get_text(" ", strip=True)
        attachments = [
            Attachment(name=a.get_text(" ", strip=True) or "attachment", url=urljoin(item.url, a["href"]))
            for a in soup.select(".view-file a[href]") if a["href"].endswith("download.do")
        ]
        images = [urljoin(item.url, img["src"]) for img in (body_el.select("img[src]") if body_el else [])]
        title = " ".join(title_el.get_text(" ", strip=True).split()) if title_el else None
        return self.build_notice(
            item,
            title=title,
            writer=meta.get("작성자") or item.writer,
            posted_at=(parse_date(meta.get("작성일", "")) or item.posted_at or "")[:10] or None,
            body_text=html_to_text(body_el),
            images=images,
            attachments=attachments,
        )
