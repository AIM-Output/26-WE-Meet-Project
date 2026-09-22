"""전남대 대표 홈페이지 계열 ASP.NET 게시판 수집기.

같은 구조를 쓰는 사이트 (references/site-structure.md §1, §5)
  - www.jnu.ac.kr        /WebApp/web/HOM/COM/Board/board.aspx?boardID=5&cate=8   (공지사항 › 장학안내)
  - international.jnu.ac.kr  /Board/Board.aspx?BoardID=3                          (국제협력과 공지)

목록  table.board_list tr → td.title a (글 번호는 URL 의 key= / Seq=), 작성자·작성일 td
상세  .board_view_wrap  .view_head h3|p.title / span[id$=lbl_Writer|lbl_name] / span[id$=lbl_WriteDate|lbl_date]
      첨부 .view_info_file a (bbsMode=download&fileCode= / ByteToFile.aspx?Seq=)   본문 .view_body .con
본문이 이미지(byteToImage.aspx / <img>)뿐인 공지가 많다 → body_is_image_only 로 표시해 '확인 필요'로 보낸다.
"""
from __future__ import annotations

from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from .. import config as C
from ..schemas import Attachment
from ..textutil import html_to_text, parse_date
from .base import BaseSource, ListItem


class JnuAspxBoard(BaseSource):
    kind = "jnu_aspx"

    def _list_url(self, page: int) -> str:
        params = dict(self.cfg.get("params", {}))
        params[self.cfg.get("page_param", "page")] = str(page)
        return f"{self.base}{self.cfg['list_path']}?{urlencode(params)}"

    def list_items(self, pages: int = C.LIST_PAGES) -> list[ListItem]:
        id_param = self.cfg.get("id_param", "key")
        items: dict[str, ListItem] = {}
        for page in range(1, pages + 1):
            soup = self.http.soup(self._list_url(page))
            rows = soup.select("table.board_list tr")
            found = 0
            for tr in rows:
                a = tr.select_one("td.title a[href]")
                if a is None:
                    continue
                href = urljoin(self.base, a["href"])
                native = parse_qs(urlparse(href).query).get(id_param, [""])[0]
                if not native:
                    continue
                tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
                date = next((t for t in tds if len(t) == 10 and t[4] == "-" and t[7] == "-"), None)
                writer = tds[2] if len(tds) >= 4 else None
                label = tr.select_one("span.label")
                item = ListItem(
                    native_id=native, title=a.get_text(" ", strip=True), url=href,
                    posted_at=date, writer=writer,
                    category=self.cfg.get("category_label"),
                    extra={"pinned": bool(label and "공지" in label.get_text())},
                )
                items.setdefault(native, item)      # 상단 고정 공지가 매 페이지 반복됨 → 한 번만
                found += 1
            if found == 0:
                break
        return list(items.values())

    def fetch_detail(self, item: ListItem):
        soup = self.http.soup(item.url)
        view = soup.select_one(".board_view_wrap") or soup
        title_el = view.select_one(".view_head h3") or view.select_one(".view_head .title")
        writer_el = view.select_one("span[id$=lbl_Writer], span[id$=lbl_name]")
        date_el = view.select_one("span[id$=lbl_WriteDate], span[id$=lbl_date]")
        body_el = view.select_one(".view_body .con") or view.select_one(".view_body")

        def strip_label(el):
            if el is None:
                return None
            for st in el.select("strong"):
                st.extract()
            return el.get_text(" ", strip=True) or None

        attachments = []
        for a in view.select(".view_info_file a[href]"):
            if "preview" in " ".join(a.get("class", [])):
                continue
            href = a["href"]
            if "download" not in href.lower() and "bytetofile" not in href.lower():
                continue
            attachments.append(Attachment(name=a.get_text(" ", strip=True) or "attachment",
                                          url=urljoin(item.url, href)))
        images = [urljoin(item.url, img["src"]) for img in (body_el.select("img[src]") if body_el else [])]
        return self.build_notice(
            item,
            title=title_el.get_text(" ", strip=True) if title_el else None,
            writer=strip_label(writer_el),
            posted_at=(parse_date(strip_label(date_el) or "") or item.posted_at or "")[:10] or None,
            body_text=html_to_text(body_el),
            images=images,
            attachments=attachments,
        )
