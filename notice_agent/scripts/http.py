"""레이트리밋이 붙은 얇은 HTTP 클라이언트 (공개 게시판 수집용).

- 요청 간격 config.REQUEST_INTERVAL, 동시성 1 — 학교 서버에 부담을 주지 않는다.
- 브라우저 없이 requests 만 쓴다. SSO 가 필요한 소스는 sso_session.py 를 쓴다.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

from . import config as C

# 일부 학교 서버(international.jnu.ac.kr)는 중간 인증서를 보내지 않아 certifi 만으로는 검증에 실패한다.
# OS 신뢰 저장소를 쓰면 (Windows 는 AIA 로 중간 인증서를 받아와) 검증을 끄지 않고도 통과한다.
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:      # 없으면 certifi 기본 동작 — 해당 소스만 SSL 오류로 건너뛴다
    pass


class Http:
    def __init__(self, interval: float = C.REQUEST_INTERVAL, timeout: int = 30):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": C.USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
        self.interval = interval
        self.timeout = timeout
        self._last = 0.0
        self.requests = 0

    def _throttle(self) -> None:
        wait = self.interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1

    def get(self, url: str, **kw) -> requests.Response:
        self._throttle()
        r = self.s.get(url, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def post(self, url: str, data: dict, **kw) -> requests.Response:
        self._throttle()
        r = self.s.post(url, data=data, timeout=self.timeout, **kw)
        r.raise_for_status()
        return r

    def soup(self, url: str, **kw) -> BeautifulSoup:
        r = self.get(url, **kw)
        r.encoding = r.apparent_encoding if not r.encoding or r.encoding.lower() == "iso-8859-1" else r.encoding
        return BeautifulSoup(r.text, "lxml")

    def soup_post(self, url: str, data: dict, **kw) -> BeautifulSoup:
        r = self.post(url, data, **kw)
        return BeautifulSoup(r.text, "lxml")

    def download(self, url: str, dest: Path, max_mb: int = C.MAX_ATTACH_MB) -> Optional[int]:
        """파일을 내려받아 dest 에 저장. HTML 응답(로그인 페이지 등)·용량 초과면 None."""
        self._throttle()
        with self.s.get(url, timeout=self.timeout, stream=True) as r:
            r.raise_for_status()
            ct = r.headers.get("content-type", "")
            if ct.startswith("text/html"):
                return None
            limit = max_mb * 1024 * 1024
            cl = r.headers.get("content-length")
            if cl and int(cl) > limit:
                return None
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = 0
            with open(dest, "wb") as f:
                for chunk in r.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > limit:
                        f.close()
                        dest.unlink(missing_ok=True)
                        return None
                    f.write(chunk)
            return size
