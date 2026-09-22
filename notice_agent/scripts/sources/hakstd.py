"""학사정보시스템(내학사행정, hakstd.jnu.ac.kr) › 장학 › 장학 안내 카탈로그 수집기.  (references/site-structure.md §4)

SSO 로그인이 필요하다 (sso_session.py). 조회만 하며 신청 버튼은 절대 누르지 않는다.

  /web/Jang/Jang012  전체 장학 안내
      div.content 안에 h4(장학명) 가 반복되고, 그 뒤 div.img-box .cont 에 "1. 지원대상 / 2. 성적기준 / 3. 지원금액 …" 목록.
      → h4 단위로 잘라 장학 1건 = Notice 1건. 학기마다 크게 바뀌지 않는 '상시 카탈로그'라 마감일은 없다.
  /web/Jang/Jang011  학생 맞춤형 장학 안내
      table#…gvData: 장학명 | 지원조건(한 줄) | 선발인원 | 문의처 | 바로가기(→ Jang012#장학명)
      → 같은 장학명에 지원조건 한 줄·문의처를 덧붙인다.

수집한 Notice 는 다른 소스와 같은 파이프라인(추출 → 매칭 → 초안)을 탄다.
공지 게시판과 달리 '지금 신청 가능한가'는 알 수 없으므로, 매칭되면 학생과 공고(홈페이지 장학안내)를 확인하라는 메모를 남긴다.
"""
from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

from .. import config as C
from ..textutil import html_to_text
from .base import BaseSource, ListItem

# 장학명 키워드 → 학사정보시스템 신청 메뉴 (references/site-structure.md §4 메뉴 지도)
APPLY_MENU = [
    ("국가근로", "/web/Jang/Jang040", "장학 › 국가근로장학 › 국가근로 장학신청"),
    ("열정장학", "/web/Jang/Jang130", "장학 › 열정장학 › 열정장학 확인서 업로드"),
    ("미래성장", "/web/Jang/Jang101", "장학 › 미래성장·취업더하기 장학 › 미래성장 장학 신청"),
    ("도전장학", "/web/Jang/Jang711", "장학 › 도전장학 › 도전장학신청(계획서 작성)"),
    ("느티나무", "/web/Jang/Jang810", "장학 › 느티나무 장학 › 느티나무 장학 신청"),
    ("창조장학", "/web/Jang/Jang020", "장학 › 저소득(창조) 장학금 신청"),
    ("응원장학", "/web/Jang/Jang910", "장학 › 응원장학 › 응원장학 신청"),
    ("학생성공지원금", "/web/Jang/Jang150", "장학 › 학생성공지원금 신청"),
    ("국가장학금", "https://www.kosaf.go.kr", "한국장학재단 홈페이지/앱에서 신청"),
    ("지역인재국가장학금", "https://www.kosaf.go.kr", "한국장학재단 홈페이지/앱에서 신청"),
]


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKC", name)
    return re.sub(r"[^0-9A-Za-z가-힣]+", "_", s).strip("_").lower() or "unnamed"


class HakstdCatalog(BaseSource):
    kind = "hakstd"

    def __init__(self, cfg: dict, http, interactive: bool = False):
        super().__init__(cfg, http)
        self.interactive = interactive
        self._sections: dict[str, dict] = {}      # slug → {name, html, text}
        self._mine: dict[str, dict] = {}          # slug → {condition, count, contact}

    # -- 페이지 로드 ------------------------------------------------------
    def _load(self) -> None:
        from .. import sso_session as S
        with S.hakstd_page(interactive=self.interactive) as page:
            if not S.goto(page, C.HAKSTD_CATALOG_ALL):
                raise S.SsoError("전체 장학 안내 페이지로 이동 중 세션이 끊겼습니다.")
            self._parse_all(page.content())
            if S.goto(page, C.HAKSTD_CATALOG_MINE):
                self._parse_mine(page.content())

    def _parse_all(self, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        content = soup.select_one("div.content") or soup
        for h4 in content.find_all("h4"):
            name = " ".join(h4.get_text(" ", strip=True).split())
            if not name:
                continue
            parts = []
            for sib in h4.find_next_siblings():
                if sib.name == "h4":
                    break
                parts.append(str(sib))
            frag = "".join(parts)
            self._sections[slug(name)] = {"name": name, "html": frag, "text": html_to_text(frag)}

    def _parse_mine(self, html: str) -> None:
        soup = BeautifulSoup(html, "lxml")
        table = soup.select_one("table[id$=gvData]")
        if table is None:
            return
        for tr in table.select("tr"):
            tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
            if len(tds) < 4:
                continue
            name = tds[0]
            self._mine[slug(name)] = {"condition": tds[1], "count": tds[2], "contact": tds[3]}

    # -- BaseSource 인터페이스 ----------------------------------------------
    def list_items(self, pages: int = 1) -> list[ListItem]:
        if not self._sections:
            self._load()
        items = []
        for sl, sec in self._sections.items():
            items.append(ListItem(native_id=sl, title=sec["name"],
                                  url=f"{C.HAKSTD_CATALOG_ALL}#{sec['name']}",
                                  writer="학생과(학사정보시스템)", category="장학 카탈로그"))
        return items

    def wanted(self, item: ListItem) -> bool:
        return True     # 카탈로그 전체가 장학

    def fetch_detail(self, item: ListItem):
        sec = self._sections[item.native_id]
        mine = self._mine.get(item.native_id, {})
        lines = []
        if mine.get("condition"):
            lines.append(f"[지원조건 요약] {mine['condition']}")
        if mine.get("count") and mine["count"] != "미정":
            lines.append(f"[선발인원] {mine['count']}")
        if mine.get("contact"):
            lines.append(f"[문의처] {mine['contact']}")
        apply_hint = next((f"[신청 경로] 학사정보시스템 {label} ({C.HAKSTD_BASE + path if path.startswith('/') else path})"
                           for kw, path, label in APPLY_MENU if kw in sec["name"]), None)
        if apply_hint:
            lines.append(apply_hint)
        body = "\n".join(lines + ["", sec["text"]]).strip()
        return self.build_notice(item, body_text=body, images=[], attachments=[])
