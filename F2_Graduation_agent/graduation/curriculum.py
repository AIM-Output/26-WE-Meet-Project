"""교육과정 — 학과·전공·입학년도별 교과목(교필·전필·전선 …) 목록. 표준 라이브러리만 (F2-R16, C2 2절 '가').

원천: 교육과정검색 `CurriCulumnSM.aspx?aYear=<연도>&aLanguage=1&aColl=<단과대>&aDept=<학과·전공>&aPageNum=<n>`
2026-09-28 실측
  - GET 만으로 결과 표 `table#…grvwList` 가 나온다: NO · 학년 · 학기 · 교과구분 · 교과목명 · 교과목No · 학점 · 이론 · 실험 (10행/페이지)
  - 페이지 링크는 `…aPageNum=N' onclick='uChangePage(N)'` — '끝페이지' 링크의 N 이 마지막 페이지
  - 학부(30001265 인공지능학부)는 1~2학년 교필·전필·전선, 전공(30001267 인공지능전공)은 3~4학년 전선·전필이 나온다
    → 전공까지 고른 학생의 과목 목록 = 학부 + 전공 두 목록을 합친 것
교과구분 값: 교필 · 전필 · 전선 (학과에 따라 더 있을 수 있다 — 그대로 둔다)

파일 두 곳
  curriculum/<코드>/<연도>.json          저장소에 넣어 두는 스냅숏 (시연 학과 — 첫 실행에도 네트워크 없이 계산된다)
  data/curriculum/<코드>/<연도>.json     사용자가 '교육과정 받기'로 내려받은 것 — 있으면 이것을 쓴다
"""
from __future__ import annotations

import html as _html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
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


class _Table(HTMLParser):
    """table#…grvwList 의 <tr> 마다 <td> 글자 목록."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._in = 0                   # grvwList 안의 table 깊이
        self._row: Optional[list[str]] = None
        self._cell: Optional[list[str]] = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            if self._in:
                self._in += 1
            elif (dict(attrs).get("id") or "").endswith("grvwList"):
                self._in = 1
        elif not self._in:
            return
        elif tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        if not self._in:
            return
        if tag == "td" and self._cell is not None and self._row is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table":
            self._in -= 1


def _num(s: str) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def parse_rows(html: str) -> list[dict]:
    """결과 표 → [{grade, term, category, name, code, credits}] (NO 열이 숫자인 행만)."""
    p = _Table()
    p.feed(html)
    out = []
    for r in p.rows:
        if len(r) < 7 or not r[0].strip().isdigit():
            continue
        credits = _num(r[6])
        out.append({
            "grade": int(r[1]) if r[1].strip().isdigit() else None,          # 권장 학년
            "term": r[2].strip() or None,                                     # 권장 학기
            "category": r[3].strip(),
            "name": _html.unescape(r[4]).strip(),
            "code": r[5].strip().upper() or None,
            "credits": credits if credits is not None else 0.0,
        })
    return out


def last_page(html: str) -> int:
    nums = [int(x) for x in re.findall(r"aPageNum=(\d+)'\s*onclick", html)]
    return max(nums or [1])


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


def url_for(college_code: str, code: str, year: int, page: int = 1) -> str:
    q = {"aYear": year, "aLanguage": 1, "aColl": college_code, "aDept": code, "aPageNum": page}
    return f"{C.CURRICULUM_URL}?{urllib.parse.urlencode(q)}"


def crawl(college_code: str, code: str, year: int, http: Optional[Http] = None,
          log: Callable[[str], None] = print) -> dict:
    """한 학과(또는 전공)·한 학년도의 교과목 전부."""
    http = http or Http()
    first = http.get(url_for(college_code, code, year, 1))
    if "grvwList" not in first:
        raise SourceError("교육과정검색 결과 표를 찾지 못했습니다 (페이지 형식이 바뀐 것 같습니다)")
    rows = parse_rows(first)
    pages = min(last_page(first), C.MAX_PAGES)
    for p in range(2, pages + 1):
        more = parse_rows(http.get(url_for(college_code, code, year, p)))
        if not more:
            break
        rows += more
    seen, courses = set(), []
    for r in rows:                                      # 같은 과목이 학기만 달리 두 번 나오는 경우가 있다
        k = (r["code"] or r["name"], r["category"])
        if k in seen:
            continue
        seen.add(k)
        courses.append(r)
    log(f"  교육과정 {code} {year}학년도 — {len(courses)}과목 ({pages}쪽)")
    return {"code": code, "collegeCode": college_code, "year": year, "fetchedAt": datetime.now().isoformat(timespec="seconds"),
            "source": url_for(college_code, code, year, 1), "courses": courses}


# ── 읽기·쓰기 ──────────────────────────────────────────────

def _file(base: Path, code: str, year: int) -> Path:
    return base / code / f"{year}.json"


def load(code: Optional[str], year: Optional[int]) -> Optional[dict]:
    if not code or not year:
        return None
    for base, origin in ((C.LOCAL_CURRICULUM, "local"), (C.BUNDLED_CURRICULUM, "bundled")):
        p = _file(base, code, year)
        if p.exists():
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            return {**doc, "origin": origin}
    return None


def save_local(doc: dict) -> Path:
    p = _file(C.LOCAL_CURRICULUM, doc["code"], int(doc["year"]))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps({k: v for k, v in doc.items() if k != "origin"}, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
    return p


def targets(dept_code: Optional[str], major_code: Optional[str]) -> list[str]:
    """과목 목록을 모을 코드 — 학부 공통 + 전공 (전공이 학과와 같으면 한 번)."""
    out = [c for c in (dept_code, major_code) if c]
    return list(dict.fromkeys(out))


def courses_for(dept_code: Optional[str], major_code: Optional[str], year: Optional[int],
                category: Optional[str] = None) -> tuple[list[dict], dict]:
    """학부 + 전공 교과목(교과구분이 category 인 것만). 반환: (과목 목록, {sources, missing})."""
    courses, sources, missing, seen = [], [], [], set()
    for code in targets(dept_code, major_code):
        doc = load(code, year)
        if doc is None:
            missing.append(code)
            continue
        sources.append({"code": code, "year": doc["year"], "origin": doc["origin"], "fetchedAt": doc.get("fetchedAt"),
                        "url": doc.get("source")})
        for c in doc.get("courses", []):
            if category and c.get("category") != category:
                continue
            k = c.get("code") or c.get("name")
            if k in seen:
                continue
            seen.add(k)
            courses.append({"code": c.get("code"), "name": c.get("name"), "credits": c.get("credits") or 0,
                            "grade": c.get("grade"), "term": c.get("term"), "category": c.get("category"), "from": code})
    return courses, {"sources": sources, "missing": missing, "year": year}


def available() -> list[dict]:
    """가지고 있는 스냅숏 목록 (코드·연도·출처)."""
    out = {}
    for base, origin in ((C.BUNDLED_CURRICULUM, "bundled"), (C.LOCAL_CURRICULUM, "local")):
        if not base.exists():
            continue
        for p in base.glob("*/*.json"):
            out[(p.parent.name, p.stem)] = {"code": p.parent.name, "year": int(p.stem), "origin": origin}
    return sorted(out.values(), key=lambda d: (d["code"], d["year"]))
