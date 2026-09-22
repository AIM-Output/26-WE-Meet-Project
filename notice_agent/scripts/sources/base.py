"""수집기 공통 인터페이스.

수집기는 두 단계만 책임진다.
  list_items(pages)   목록 페이지 → ListItem (제목·URL·날짜만, 요청 수 최소화)
  fetch_detail(item)  글 1건 → Notice (본문 텍스트·첨부·이미지)

첨부 내려받기·텍스트 추출·신규 판별은 collect.py 가 공통으로 한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .. import config as C
from ..schemas import Notice
from ..textutil import content_hash


@dataclass
class ListItem:
    native_id: str
    title: str
    url: str
    posted_at: Optional[str] = None
    writer: Optional[str] = None
    category: Optional[str] = None
    extra: dict = field(default_factory=dict)


class BaseSource:
    kind = "base"

    def __init__(self, cfg: dict, http):
        self.cfg = cfg
        self.key = cfg["key"]
        self.name = cfg.get("name", cfg["key"])
        self.base = cfg["base"].rstrip("/")
        self.http = http

    # -- 구현체가 채우는 부분 ------------------------------------------
    def list_items(self, pages: int = C.LIST_PAGES) -> list[ListItem]:
        raise NotImplementedError

    def fetch_detail(self, item: ListItem) -> Notice:
        raise NotImplementedError

    # -- 공통 --------------------------------------------------------
    def notice_id(self, native_id: str) -> str:
        return f"{self.key}:{native_id}"

    def wanted(self, item: ListItem) -> bool:
        """장학 관련 글만 남긴다. 카테고리가 장학인 게시판은 keyword_filter=False 로 두어 전부 통과시킨다."""
        if not self.cfg.get("keyword_filter", True):
            return True
        title = item.title or ""
        cat = item.category or ""
        return any(k in title or k in cat for k in C.SCHOLARSHIP_KEYWORDS)

    @staticmethod
    def is_result_notice(title: str) -> bool:
        return any(k in title for k in C.RESULT_KEYWORDS)

    def build_notice(self, item: ListItem, **fields) -> Notice:
        body = fields.get("body_text", "") or ""
        images = fields.get("images", []) or []
        n = Notice(
            id=self.notice_id(item.native_id),
            source=self.key,
            source_name=self.name,
            title=fields.get("title") or item.title,
            url=item.url,
            posted_at=fields.get("posted_at") or item.posted_at,
            writer=fields.get("writer") or item.writer,
            category=fields.get("category") or item.category,
            body_text=body,
            body_is_image_only=(len(body.strip()) < 40 and len(images) > 0),
            images=images,
            attachments=fields.get("attachments", []) or [],
            is_result_notice=self.is_result_notice(fields.get("title") or item.title),
        )
        n.content_hash = content_hash(n.title, n.body_text, *[a.url for a in n.attachments])
        return n
