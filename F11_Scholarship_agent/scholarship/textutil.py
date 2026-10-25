"""글자·날짜 유틸 — 한국식 날짜 파싱, 제목 키, 근거 문장 찾기. 표준 라이브러리만 (백엔드도 import 한다).

날짜 규칙은 notice_agent/scripts/textutil.py 에서 옮겨 왔다 (실측 표기 그대로):
    2026. 9. 9.(수) 18:00 · 2026.09.11 13:21 · 2026-09-11 · 2026년 9월 30일(수)
    9. 14.(월) ~ 9. 30.(수) · ~9/16까지 · 2026.9.1.~9.18. · 9월 18일까지 · 1월 19일(월) ~ 20일(화)
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import date, datetime
from typing import Optional

from . import config as C


def nfkc(s: Optional[str]) -> str:
    return unicodedata.normalize("NFKC", s or "")


def squash(s: Optional[str]) -> str:
    """비교용 — 공백·기호를 빼고 소문자."""
    return re.sub(r"[\s\W_]+", "", nfkc(s)).lower()


def norm_title(title: str) -> str:
    """같은 공지가 여러 게시판에 올라온 것을 묶는 키 — 말머리·괄호·기호를 뺀 제목."""
    t = nfkc(title)
    t = re.sub(r"\[[^\]]*\]|\([^)]*\)|「[^」]*」|『[^』]*』|<[^>]*>", " ", t)
    t = re.sub(r"새글|new", " ", t, flags=re.I)
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", t).lower()


def content_hash(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


def has_any(text: str, words) -> bool:
    t = nfkc(text)
    return any(w in t for w in words)


def is_scholarship(title: str, category: Optional[str] = None) -> bool:
    return has_any(f"{title} {category or ''}", C.SCHOLARSHIP_WORDS)


def is_result(title: str) -> bool:
    return has_any(title, C.RESULT_WORDS)


# ── 날짜 ───────────────────────────────────────────────────
_FULL = re.compile(
    r"(?P<y>20\d{2})\s*[.\-/년]\s*(?P<m>\d{1,2})\s*[.\-/월]\s*(?P<d>\d{1,2})\s*일?\.?"
    r"(?:\s*\([^)]{1,4}\))?(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)
# (?<![\d./]) … (?![\d/]) 는 '3.5/4.5 이상' 같은 평점 표기를 날짜로 오인하지 않기 위한 경계다.
_SHORT = re.compile(
    r"(?<![\d./])(?P<m>\d{1,2})\s*[./월]\s*(?P<d>\d{1,2})(?![\d/])\s*일?\.?(?:\s*\([^)]{1,4}\))?"
    r"(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)
_DAY_ONLY = re.compile(
    r"(?:~|∼|～|-|–|—)\s*(?P<d>\d{1,2})\s*일(?:\s*\([^)]{1,4}\))?"
    r"(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)


def _mk(y: int, m: int, d: int, h: Optional[str], mi: Optional[str]) -> Optional[str]:
    try:
        if h is not None:
            hh = int(h)
            if hh == 24:                 # '24:00' = 그날 밤 끝
                return datetime(y, m, d, 23, 59).strftime("%Y-%m-%dT%H:%M")
            return datetime(y, m, d, hh, int(mi or 0)).strftime("%Y-%m-%dT%H:%M")
        return date(y, m, d).isoformat()
    except ValueError:
        return None                      # 2월 30일 같은 존재하지 않는 날짜


def parse_date(text: str, default_year: Optional[int] = None) -> Optional[str]:
    """문자열 안의 첫 날짜 → ISO. 연도가 없으면 default_year(없으면 올해)."""
    if not text:
        return None
    text = nfkc(text)
    m = _FULL.search(text)
    if m:
        return _mk(int(m["y"]), int(m["m"]), int(m["d"]), m["h"], m["mi"])
    m = _SHORT.search(text)
    if m:
        return _mk(default_year or date.today().year, int(m["m"]), int(m["d"]), m["h"], m["mi"])
    return None


def parse_period(text: str, default_year: Optional[int] = None) -> tuple[Optional[str], Optional[str]]:
    """'2026. 8. 12.(수) 09:00 ~ 2026. 9. 9.(수) 18:00' / '9.14.(월)~9.30.(수)' / '~9/16까지' → (start, end).
    뒤쪽 날짜에 연도가 없으면 앞쪽 연도를 물려받는다. 하나만 있으면 end 로 본다('~까지' 가 대부분 종료일)."""
    if not text:
        return None, None
    text = nfkc(text)
    found: list = []
    for m in _FULL.finditer(text):
        found.append((m.start(), _mk(int(m["y"]), int(m["m"]), int(m["d"]), m["h"], m["mi"]), int(m["y"])))
    covered = [(m.start(), m.end()) for m in _FULL.finditer(text)]
    for m in _SHORT.finditer(text):
        if any(s <= m.start() < e for s, e in covered):
            continue
        found.append((m.start(), ("SHORT", int(m["m"]), int(m["d"]), m["h"], m["mi"]), None))
    covered += [(m.start(), m.end()) for m in _SHORT.finditer(text)]
    for m in _DAY_ONLY.finditer(text):
        if any(s <= m.start("d") < e for s, e in covered):
            continue
        found.append((m.start("d"), ("DAY", int(m["d"]), m["h"], m["mi"]), None))
    found.sort(key=lambda x: x[0])
    year_ctx = default_year or date.today().year
    month_ctx: Optional[int] = None
    isos: list[str] = []
    for _, v, y in found:
        if isinstance(v, tuple) and v[0] == "SHORT":
            _, mm, dd, h, mi = v
            iso = _mk(year_ctx, mm, dd, h, mi)
            month_ctx = mm
        elif isinstance(v, tuple):
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
        if re.search(r"부터|시작|개시", text) and not re.search(r"까지|마감|종료", text):
            return isos[0], None
        return None, isos[0]
    start, end = isos[0], isos[-1]
    if end < start:
        start, end = end, start
    return start, end


def to_date(iso: Optional[str]) -> Optional[date]:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).date()
    except ValueError:
        try:
            return date.fromisoformat(iso[:10])
        except ValueError:
            return None


def days_until(iso: Optional[str], today: Optional[date] = None) -> Optional[int]:
    d = to_date(iso)
    if d is None:
        return None
    return (d - (today or date.today())).days


def find_sentence(source_text: str, pattern: str, window: int = 120) -> Optional[str]:
    """정규식이 맞는 지점을 포함하는 원문 한 줄(또는 주변 window 글자) — 규칙 추출의 근거(인용)."""
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


def lines(text: str) -> list[str]:
    return [ln.strip() for ln in (text or "").splitlines() if ln.strip()]


def semester_of(d: date) -> str:
    """학기 이름 — 이력 탭 묶음용 (3~8월 1학기, 9~2월 2학기)."""
    if 3 <= d.month <= 8:
        return f"{d.year}-1"
    return f"{d.year if d.month >= 9 else d.year - 1}-2"
