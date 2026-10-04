"""학과 마스터 수집 — 교육과정검색 (www.jnu.ac.kr … CurriCulumnSM.aspx). 표준 라이브러리만 (C2-R02).

2026-09-28 실측
  - `?aYear=2026&aLanguage=1` 로 열면 단과대 select(`…ddl_sch_COLL`)에 61개가 들어 있다(학부 3000…, 대학원 2000…).
  - `&aColl=<단과대코드>` 를 붙여 GET 하면 **포스트백 없이** 학과 select(`…ddl_sch_DEPT`)가 채워진다.
  - 학과·전공 계층은 이름으로 드러난다: `인공지능학부` 와 `인공지능학부 인공지능전공` (학과 이름 + 공백 + 전공 이름).
    전공이 하나뿐인 융합전공은 `로봇공학융합전공 로봇공학융합전공` 처럼 같은 이름이 반복된다.
요청은 단과대 수 + 1번(약 45번, 1.5초 간격 → 1분 남짓).
"""
from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from typing import Callable, Optional

from . import config as C

# 맥 python.org 설치판은 인증서 묶음이 없어 urllib 이 CERTIFICATE_VERIFY_FAILED 로 실패한다.
# truststore 가 있으면 검증을 끄지 않고 OS 신뢰 저장소(맥 키체인·Windows 인증서 저장소)를 쓴다 (F1·notice_agent 와 같은 처리).
try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass


class SourceError(RuntimeError):
    pass


class _Selects(HTMLParser):
    """<select id="…ddl_sch_COLL|DEPT"> 의 option 들 (value, text)."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.options: dict[str, list[tuple[str, str]]] = {}
        self._sel: Optional[str] = None
        self._val: Optional[str] = None
        self._txt: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "select":
            sid = a.get("id") or ""
            self._sel = next((k for k in ("COLL", "DEPT", "YEAR") if sid.endswith(f"ddl_sch_{k}")), None)
            if self._sel:
                self.options.setdefault(self._sel, [])
        elif tag == "option" and self._sel:
            self._val, self._txt = a.get("value") or "", []

    def handle_data(self, data):
        if self._val is not None:
            self._txt.append(data)

    def handle_endtag(self, tag):
        if tag == "option" and self._sel and self._val is not None:
            text = " ".join("".join(self._txt).split())
            if self._val:
                self.options[self._sel].append((self._val, text))
            self._val = None
        elif tag == "select":
            self._sel = None


class Http:
    def __init__(self, interval: float = C.REQUEST_INTERVAL):
        self.interval = interval
        self._last = 0.0

    def get(self, url: str) -> str:
        last: Optional[Exception] = None
        for attempt in range(len(C.RETRY_WAITS) + 1):
            if attempt:
                time.sleep(C.RETRY_WAITS[attempt - 1])
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": C.USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
                with urllib.request.urlopen(req, timeout=C.HTTP_TIMEOUT) as r:
                    return r.read().decode("utf-8", errors="replace")
            except urllib.error.HTTPError as e:
                if 400 <= e.code < 500:
                    raise SourceError(f"HTTP {e.code}: {url}") from e
                last = e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last = e
        raise SourceError(f"교육과정검색에 접속하지 못했습니다 ({type(last).__name__})") from last


def parse_selects(html: str) -> dict[str, list[tuple[str, str]]]:
    p = _Selects()
    p.feed(html)
    return p.options


def build_departments(options: list[tuple[str, str]]) -> list[dict]:
    """학과 select 항목 → [{code, name, majors: [{code, name}]}]. '학과 전공' 이름으로 계층을 되살린다."""
    names = {n for _, n in options}
    depts: dict[str, dict] = {}
    majors: list[tuple[str, str, str]] = []            # (parent name, code, major name)
    for code, name in options:
        parent = max((p for p in names if p != name and name.startswith(p + " ")), key=len, default=None)
        if parent:
            majors.append((parent, code, name[len(parent) + 1:].strip()))
        else:
            depts[name] = {"code": code, "name": name, "majors": []}
    for parent, code, mname in majors:
        depts[parent]["majors"].append({"code": code, "name": mname})
    return sorted(depts.values(), key=lambda d: d["name"])


def crawl(year: Optional[int] = None, log: Callable[[str], None] = print) -> dict:
    """전 학부 단과대의 학과·전공 → 마스터 dict."""
    year = year or C.current_year()
    http = Http()
    base = f"{C.CURRICULUM_URL}?{urllib.parse.urlencode({'aYear': year, 'aLanguage': 1})}"
    root = parse_selects(http.get(base))
    colleges = [(c, n) for c, n in root.get("COLL", [])
                if c.startswith(C.UNDERGRAD_PREFIX) and c not in C.SKIP_COLLEGES]
    if not colleges:
        raise SourceError("교육과정검색에서 단과대 목록을 찾지 못했습니다 (페이지 형식이 바뀐 것 같습니다)")
    log(f"  {year}학년도 학부 단과대 {len(colleges)}개")
    out = []
    for i, (code, name) in enumerate(colleges, 1):
        opts = parse_selects(http.get(f"{base}&aColl={code}")).get("DEPT", [])
        depts = build_departments(opts)
        if depts:
            out.append({"code": code, "name": name, "departments": depts})
        log(f"  [{i}/{len(colleges)}] {name} — 학과 {len(depts)}")
    return {"updatedAt": datetime.now().isoformat(timespec="seconds"), "year": year, "source": C.CURRICULUM_URL,
            "colleges": out}
