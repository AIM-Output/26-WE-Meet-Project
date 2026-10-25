"""수집기 공통 — 요청 간격·재시도가 붙은 HTTP 클라이언트, HTML→글자, 글 하나(Post).

수집기는 자식 프로세스(`-m scholarship sync`)에서만 돈다 — requests·bs4 는 여기서만 import 한다(백엔드는 이 폴더를 import 하지 않는다).
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .. import config as C

# 일부 학교 서버(국제협력본부 등)는 중간 인증서를 보내지 않는다. 검증을 끄지 않고 OS 신뢰 저장소를 쓴다 (F1·notice_agent 와 같은 처리).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


class SourceError(RuntimeError):
    """원천을 읽지 못함 — 화면에 '접속 실패'로 보인다."""
    reason = "접속 실패"


class FormatChanged(SourceError):
    """페이지는 열렸는데 기대한 구조가 없음 — '형식 변경 의심'."""
    reason = "형식 변경 의심"


class NeedsProfile(SourceError):
    reason = "프로필에 소속이 없습니다"


class NotListed(SourceError):
    reason = "홈페이지를 찾지 못했습니다"


class Http:
    """요청 간격 REQUEST_INTERVAL, 동시성 1, 실패하면 간격을 늘려 재시도."""

    def __init__(self, interval: float = C.REQUEST_INTERVAL, retry_waits: tuple[int, ...] = C.RETRY_WAITS):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": C.USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
        self.interval = interval
        self.retry_waits = retry_waits
        self._last = 0.0
        self.count = 0

    def _throttle(self) -> None:
        wait = self.interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.count += 1

    def get(self, url: str, **kw) -> requests.Response:
        last: Optional[Exception] = None
        for attempt in range(len(self.retry_waits) + 1):
            if attempt:
                time.sleep(self.retry_waits[attempt - 1])
            self._throttle()
            try:
                r = self.s.get(url, timeout=C.HTTP_TIMEOUT, **kw)
                if r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}", response=r)
                r.raise_for_status()
                if not r.encoding or r.encoding.lower() == "iso-8859-1":
                    r.encoding = r.apparent_encoding
                return r
            except requests.HTTPError as e:
                if e.response is not None and 400 <= e.response.status_code < 500:
                    raise SourceError(f"HTTP {e.response.status_code}: {url}") from e
                last = e
            except requests.RequestException as e:
                last = e
        raise SourceError(f"접속 실패 ({type(last).__name__}): {url}") from last

    def soup(self, url: str, **kw) -> BeautifulSoup:
        return BeautifulSoup(self.get(url, **kw).text, "lxml")

    def download(self, url: str, max_mb: int = C.MAX_ATTACH_MB) -> Optional[bytes]:
        """첨부 내용. HTML 응답(로그인 화면 등)·용량 초과면 None. 파일로 저장하지 않는다."""
        self._throttle()
        try:
            with self.s.get(url, timeout=C.HTTP_TIMEOUT, stream=True) as r:
                r.raise_for_status()
                if r.headers.get("content-type", "").startswith("text/html"):
                    return None
                limit = max_mb * 1024 * 1024
                buf = bytearray()
                for chunk in r.iter_content(64 * 1024):
                    buf.extend(chunk)
                    if len(buf) > limit:
                        return None
                return bytes(buf)
        except requests.RequestException:
            return None


_WS = re.compile(r"[ \t 　]+")


def html_to_text(root) -> str:
    """HTML 요소 → 줄 단위 글자. 표의 한 행은 셀을 ' | ' 로 이어 한 줄로 (표 안의 조건이 한 줄에 보이게)."""
    if root is None:
        return ""
    soup = BeautifulSoup(str(root), "html.parser")
    for bad in soup.select("script, style, noscript"):
        bad.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for tr in soup.find_all("tr"):
        cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
        tr.replace_with(" | ".join(x for x in cells if x) + "\n")
    for block in soup.find_all(["p", "div", "li", "h1", "h2", "h3", "h4", "h5", "table", "ul", "ol"]):
        block.insert_before("\n")
        block.insert_after("\n")
    text = unicodedata.normalize("NFKC", soup.get_text())
    lines = [_WS.sub(" ", ln).strip() for ln in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def clean_title(s: str) -> str:
    s = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", s or "")).strip()
    return re.sub(r"\s*(?:새글|new|NEW)\s*$", "", s).strip()


@dataclass
class Post:
    """게시판 글 하나 (수집기 공통)."""
    native_id: str
    title: str
    url: str
    posted_at: Optional[str] = None        # YYYY-MM-DD
    writer: Optional[str] = None
    category: Optional[str] = None
    pinned: bool = False
    body: str = ""
    image_only: bool = False
    attachments: list[dict] = field(default_factory=list)   # [{name, url}]
    images: list[str] = field(default_factory=list)         # 본문 이미지 주소(data: 포함) — 본문이 짧으면 OCR (attachments.gather)
    extra: dict = field(default_factory=dict)


def ymd(text: Optional[str]) -> Optional[str]:
    m = re.search(r"(20\d{2})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text or "")
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


_NOT_CONTENT_IMG = re.compile(r"icon|ico_|btn_|/btn|emoticon|emoji|blank\.|spacer|loading|\.svg(?:$|\?)", re.I)


def body_images(post: Post, el, limit: int = 6) -> list[str]:
    """본문 안 이미지 주소 — 아이콘·버튼·이모티콘은 뺀다. 상대 주소는 글 주소 기준으로."""
    if el is None:
        return []
    out: list[str] = []
    for img in el.select("img[src]"):
        src = (img.get("src") or "").strip()
        if not src or (not src.startswith("data:image/") and _NOT_CONTENT_IMG.search(src)):
            continue
        u = src if src.startswith("data:") else urljoin(post.url, src)
        if u not in out:
            out.append(u)
        if len(out) >= limit:
            break
    return out


def finish(post: Post, body_el) -> Post:
    post.body = html_to_text(body_el)
    post.images = body_images(post, body_el)
    has_img = bool(body_el is not None and body_el.select("img[src]"))
    post.image_only = has_img and len(re.sub(r"\s+", "", post.body)) < 40
    return post
