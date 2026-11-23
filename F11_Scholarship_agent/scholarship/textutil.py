"""글자·날짜 유틸 — 한국식 날짜 파싱, 제목 키, 근거 문장 찾기. 표준 라이브러리만 (백엔드도 import 한다).

날짜 규칙은 예전 장학 도구 notice_agent 에서 옮겨 왔다 (실측 표기 그대로):
    2026. 9. 9.(수) 18:00 · 2026.09.11 13:21 · 2026-09-11 · 2026년 9월 30일(수)
    9. 14.(월) ~ 9. 30.(수) · ~9/16까지 · 2026.9.1.~9.18. · 9월 18일까지 · 1월 19일(월) ~ 20일(화)
    '26. 11. 16.(월) ~ 26.(목) 18:00 · ’26. 10. 22.(수) 9시 ∼ ’26. 11. 12.(목) 18시   (두 자리 연도 · 날만 있는 끝, 2026-11-23)
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


# 게시판 말머리 — 제목 앞 [ ] 가 이것이면 글 내용이 아니라 게시판 분류다 (대표 공지 '[모집공고]·[장학안내]·[취업정보]…' ·
# 학과 K2Web '[학사]·[장학]·[장학관련]' · COSS 분류). 같은 글 묶기(title_key)와 F12 분류·주관 찾기(activity.extract)가 같이 쓴다.
# [KIA]·[(재)김해시미래인재장학재단] 같은 기관 괄호는 넣지 않는다 — 그게 글을 가른다.
BOARD_CATEGORIES = frozenset({
    "모집공고", "학사안내", "공모전", "대학생활", "채용공고", "취업정보", "행정공고", "입찰공고", "장학안내", "일반공지", "학술연구",
    "공지", "공지사항", "안내", "행사", "특강", "학사", "취업", "장학", "장학관련", "일반", "모집", "교육", "대학원", "학부", "학과",
    "기타", "홍보", "알림", "학생지원", "경진대회", "비교과", "프로그램", "학과공지", "학부공지", "행사안내", "채용"})


def strip_board_category(title: str) -> str:
    """제목 앞의 말머리 [모집공고]·[장학안내] 같은 것만 떼고, [KIA]·[제주대학교] 같은 기관 괄호는 둔다."""
    t = nfkc(title).strip()
    while True:
        m = re.match(r"^\[([^\]]{1,14})\]\s*", t)
        if not m or m.group(1).strip() not in BOARD_CATEGORIES:
            return t
        t = t[m.end():]


def title_key(title: str) -> str:
    """같은 글을 묶는 제목 키 (F11·F12 — 여러 게시판에 올라온 같은 글, 같은 게시판에 다시 올린 글) — 앞 말머리와 공백·기호만 뺀다.
    괄호·대괄호·「」 안은 남긴다: 재단·대학·회사·프로그램 이름, 회차('(2차)'), 연사, 날짜가 거기 있다. 2026-11-19 까지는 괄호 안을
    다 지워 다른 글이 하나로 접혔다 — 장학: 김해시↔경주시·인천↔대구 달서 장학이 묶여 숨고 푸른등대 '(2차)'가 1차 뒤에 숨었다 ·
    대외활동: 묶음 83건 중 65건(대학별 교류수학 추천·글로컬대학사업 「…」·회사만 다른 채용·추가모집)."""
    t = re.sub(r"새글|new", " ", strip_board_category(title), flags=re.I)
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
# 끝 날짜에 날만 있는 표기 — '~ 20일(화)' · '~ 26.(목) 18:00' ('일' 없이 요일 괄호만 붙은 것은 2026-11-23 실측)
_DAY_ONLY = re.compile(
    r"(?:~|∼|～|-|–|—)\s*(?P<d>\d{1,2})\s*(?:일(?:\s*\([^)]{1,4}\))?|\.?\s*\([월화수목금토일]\))"
    r"(?:\s*,?\s*(?P<h>\d{1,2})\s*[:시]\s*(?P<mi>\d{2})?)?"
)
# 두 자리 연도 — 한국장학재단·재단 공고문에 많다: '26. 11. 16.(월) · ’26.10.26.(월) · `26. 10. 30.(금)
_Y2 = re.compile(r"['’‘`′´]\s*(\d{2})(?=\s*[.년/\-]\s*\d{1,2}\s*[.월/\-])")
# 따옴표 없는 '26.10.26.(월)' 은 세 덩어리 뒤에 요일 괄호가 있을 때만 — 평점·전화번호·'9. 14.(월)' 과 헷갈리지 않게
_Y2_BARE = re.compile(r"(?<![\d.'’‘`′´])(2[4-9])(?=\s*\.\s*\d{1,2}\s*\.\s*\d{1,2}\s*\.?\s*\([월화수목금토일]\))")


def _years(text: str) -> str:
    """두 자리 연도를 네 자리로 ('26. → 2026.) — 날짜 규칙이 연도를 '26월'로 읽어 날짜를 통째로 놓치지 않게."""
    text = _Y2.sub(lambda m: "20" + m.group(1), text)
    return _Y2_BARE.sub(lambda m: "20" + m.group(1), text)


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
    text = _years(nfkc(text))
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
    text = _years(nfkc(text))
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
