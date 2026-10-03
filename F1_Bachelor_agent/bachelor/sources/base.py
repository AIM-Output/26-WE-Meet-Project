"""수집기 공통 — 요청 간격·재시도가 붙은 HTTP 클라이언트, HTML→텍스트, 결과 형식.

원천마다 구조가 달라서 수집기는 파일 하나씩(calendar_table · jnu_board · k2web) 두고, 공통 부분만 여기 모은다.
"""
from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

import requests
from bs4 import BeautifulSoup

from .. import config as C

# 일부 학교 서버는 중간 인증서를 보내지 않는다. 검증을 끄지 않고 OS 신뢰 저장소를 쓴다 (notice_agent 와 같은 처리).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


class SourceError(RuntimeError):
    """원천을 읽지 못함 — 화면에 '접속 실패' 로 보인다."""
    reason = "접속 실패"


class FormatChanged(SourceError):
    """페이지는 열렸는데 기대한 구조가 없음 — '형식 변경 의심' (F1 9절)."""
    reason = "형식 변경 의심"


class NeedsProfile(SourceError):
    """내 소속 원천(③·④)인데 프로필에 단과대학·학과가 없음 — 실패가 아니라 '대기'."""
    reason = "프로필에 소속이 없습니다"
    result = "needs_profile"


class NotListed(SourceError):
    """프로필 소속의 홈페이지를 목록에서 찾지 못함 — 사용자가 게시판 주소를 직접 지정하면 된다."""
    reason = "홈페이지를 찾지 못했습니다"
    result = "not_found"


class Http:
    """요청 간격 REQUEST_INTERVAL, 동시성 1, 실패하면 간격을 늘려 3회 재시도."""

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
                    raise requests.HTTPError(f"HTTP {r.status_code}")
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

    def soup(self, url: str) -> BeautifulSoup:
        return BeautifulSoup(self.get(url).text, "lxml")

    def download(self, url: str, max_mb: int = C.MAX_ATTACH_MB) -> Optional[bytes]:
        """첨부 파일 내용. HTML 응답(로그인 페이지 등)·용량 초과면 None."""
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
    """HTML 요소 → 줄 단위 텍스트. 표의 한 행은 셀을 ' | ' 로 이어 한 줄로 만든다 (행 단위로 일정을 뽑기 위해)."""
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


@dataclass
class Post:
    """게시판 글 하나 (공지 원천 공통)."""
    post_id: str
    title: str
    url: str
    posted_at: Optional[str] = None        # YYYY-MM-DD
    writer: Optional[str] = None
    pinned: bool = False
    body: str = ""
    image_only: bool = False               # 본문이 이미지뿐 → 날짜를 못 읽는다 (needs_ocr)
    attachments: list[dict] = field(default_factory=list)   # [{name, url}]
