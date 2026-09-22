"""텍스트·날짜 유틸 — HTML 본문 정리, 한국식 날짜 파싱, 근거 문장 검증, 파일명 정리.

LLM 없이도 돌아가야 하는 부분이라 전부 순수 함수다.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from bs4 import BeautifulSoup

UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
WS = re.compile(r"[ \t 　]+")
BLANK_LINES = re.compile(r"\n{3,}")


# ── HTML → 텍스트 ───────────────────────────────────────────

def html_to_text(root) -> str:
    """BeautifulSoup 요소 → 줄 단위 텍스트. 표는 셀을 ' | ' 로 이어 한 줄로 만든다 (표 안의 조건이 잘 보이게)."""
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
    text = soup.get_text()
    text = unicodedata.normalize("NFKC", text)
    lines = [WS.sub(" ", ln).strip() for ln in text.splitlines()]
    text = "\n".join(lines)
    text = BLANK_LINES.sub("\n\n", text).strip()
    return text


def normalize_title(title: str) -> str:
    """중복 판별용 제목 키 — 괄호 말머리·공백·기호 제거."""
    t = unicodedata.normalize("NFKC", title)
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|「[^」]*」|『[^』]*』", " ", t)
    t = re.sub(r"[^0-9A-Za-z가-힣]+", "", t)
    return t.lower()


def content_hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def sanitize_filename(name: str, limit: int = 80) -> str:
    name = UNSAFE_CHARS.sub("_", name).strip(" ._")
    return (name or "unnamed")[:limit]


# ── 날짜 ───────────────────────────────────────────────────
# 학교 공지에서 실제로 보이는 표기들:
#   2026. 9. 9.(수) 18:00  /  2026.09.11 13:21  /  2026-09-11  /  2026년 9월 30일(수)
#   9. 14.(월) ~ 9. 30.(수)  /  ~9/16까지  /  2026.9.1.~9.18.  /  9월 18일까지
_FULL = re.compile(
    r"(?P<y>20\d{2})\s*[.\-/년]\s*(?P<m>\d{1,2})\s*[.\-/월]\s*(?P<d>\d{1,2})\s*일?\.?"
    r"(?:\s*\([^)]{1,4}\))?(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)
# (?<![\d./]) … (?![\d/]) 는 '3.5/4.5 이상' 같은 평점 표기를 날짜로 오인하지 않기 위한 경계다.
_SHORT = re.compile(
    r"(?<![\d./])(?P<m>\d{1,2})\s*[./월]\s*(?P<d>\d{1,2})(?![\d/])\s*일?\.?(?:\s*\([^)]{1,4}\))?"
    r"(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)
_RANGE_SEP = re.compile(r"\s*(?:~|∼|～|-|–|—|부터|에서)\s*")
# 범위 뒤쪽의 '20일(화)' 같은 일(日)만 있는 표기 (앞 날짜의 연·월을 물려받음)
_DAY_ONLY = re.compile(
    r"(?:~|∼|～|-|–|—)\s*(?P<d>\d{1,2})\s*일(?:\s*\([^)]{1,4}\))?"
    r"(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)


def _mk(y: int, m: int, d: int, h: Optional[str], mi: Optional[str]) -> Optional[str]:
    try:
        if h is not None:
            return datetime(y, m, d, int(h), int(mi or 0)).strftime("%Y-%m-%dT%H:%M")
        return date(y, m, d).isoformat()
    except ValueError:
        return None      # 2월 30일 같은 존재하지 않는 날짜


def parse_date(text: str, default_year: Optional[int] = None) -> Optional[str]:
    """문자열 안의 첫 날짜 → ISO. 연도가 없으면 default_year(없으면 올해)."""
    if not text:
        return None
    text = unicodedata.normalize("NFKC", text)
    m = _FULL.search(text)
    if m:
        return _mk(int(m["y"]), int(m["m"]), int(m["d"]), m["h"], m["mi"])
    m = _SHORT.search(text)
    if m:
        y = default_year or date.today().year
        return _mk(y, int(m["m"]), int(m["d"]), m["h"], m["mi"])
    return None


def parse_period(text: str, default_year: Optional[int] = None) -> tuple[Optional[str], Optional[str]]:
    """'2026. 8. 12.(수) 09:00 ~ 2026. 9. 9.(수) 18:00' / '9.14.(월)~9.30.(수)' / '~9/16까지' → (start, end).

    뒤쪽 날짜에 연도가 없으면 앞쪽 연도를 물려받는다. 하나만 있으면 end 로 본다
    ('~까지', '마감' 표기가 대부분 종료일이기 때문).
    """
    if not text:
        return None, None
    text = unicodedata.normalize("NFKC", text)
    found: list[tuple[int, Optional[str], Optional[int]]] = []   # (pos, iso, year)
    for m in _FULL.finditer(text):
        found.append((m.start(), _mk(int(m["y"]), int(m["m"]), int(m["d"]), m["h"], m["mi"]), int(m["y"])))
    covered = [(m.start(), m.end()) for m in _FULL.finditer(text)]
    for m in _SHORT.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue
        # 연도 미정 — 앞선 완전한 날짜의 연도(없으면 default_year)를 아래에서 물려준다
        found.append((m.start(), ("SHORT", int(m["m"]), int(m["d"]), m["h"], m["mi"]), None))  # type: ignore[arg-type]
    # '1월 19일(월) ~ 20일(화)' 처럼 뒤쪽이 '일' 만 있는 표기 — 앞 날짜의 연·월을 물려받는다
    covered += [(m.start(), m.end()) for m in _SHORT.finditer(text)]
    for m in _DAY_ONLY.finditer(text):
        if any(s <= m.start("d") < e for s, e in covered):
            continue
        found.append((m.start("d"), ("DAY", int(m["d"]), m["h"], m["mi"]), None))  # type: ignore[arg-type]
    found.sort(key=lambda x: x[0])
    year_ctx = default_year or date.today().year
    month_ctx: Optional[int] = None
    isos: list[str] = []
    for _, v, y in found:
        if isinstance(v, tuple) and v[0] == "SHORT":
            _, mm, dd, h, mi = v
            iso = _mk(year_ctx, mm, dd, h, mi)
            month_ctx = mm
        elif isinstance(v, tuple):                     # DAY
            _, dd, h, mi = v
            if month_ctx is None:
                continue
            iso = _mk(year_ctx, month_ctx, dd, h, mi)
        else:
            iso = v
            if y:
                year_ctx = y
            if iso:
                month_ctx = int(iso[5:7])
        if iso:
            isos.append(iso)
    if not isos:
        return None, None
    if len(isos) == 1:
        # '2026. 9. 1.부터' 처럼 시작만 있는 경우
        if re.search(r"부터|시작|개시", text) and not re.search(r"까지|마감|종료", text):
            return isos[0], None
        return None, isos[0]
    start, end = isos[0], isos[-1]
    if end < start and len(isos) >= 2:      # '9.30 ~ 10.2' 인데 연도 추정이 꼬인 경우 → 그대로 두되 순서만 유지
        start, end = end, start
    return start, end


def days_until(iso: Optional[str], today: Optional[date] = None) -> Optional[int]:
    if not iso:
        return None
    today = today or date.today()
    try:
        d = datetime.fromisoformat(iso).date()
    except ValueError:
        return None
    return (d - today).days


# ── 근거 문장 검증 ──────────────────────────────────────────

def _squash(s: str) -> str:
    return re.sub(r"[\s\W_]+", "", unicodedata.normalize("NFKC", s)).lower()


def is_grounded(quote: str, source_text: str, min_len: int = 6) -> bool:
    """LLM 이 돌려준 근거 문장이 실제 원문에 있는지. 공백·기호 차이는 무시하고 부분 일치를 본다.

    근거가 원문에 없으면 그 값은 모델이 지어낸 것일 수 있으므로 신뢰도에서 뺀다.
    """
    q, s = _squash(quote), _squash(source_text)
    if len(q) < min_len:
        return False
    if q in s:
        return True
    # 긴 인용은 앞/뒤 절반만 맞아도 인정 (모델이 문장을 살짝 다듬는 경우)
    half = max(min_len, len(q) // 2)
    return q[:half] in s or q[-half:] in s


def find_sentence(source_text: str, pattern: str, window: int = 120) -> Optional[str]:
    """정규식이 맞는 지점을 포함하는 원문 한 줄(또는 주변 window 글자)을 돌려준다 — 규칙 추출의 근거용."""
    m = re.search(pattern, source_text)
    if not m:
        return None
    line_start = source_text.rfind("\n", 0, m.start()) + 1
    line_end = source_text.find("\n", m.end())
    line_end = len(source_text) if line_end == -1 else line_end
    line = source_text[line_start:line_end].strip()
    if len(line) > window * 2:
        a = max(m.start() - window, line_start)
        b = min(m.end() + window, line_end)
        line = source_text[a:b].strip()
    return line or None
