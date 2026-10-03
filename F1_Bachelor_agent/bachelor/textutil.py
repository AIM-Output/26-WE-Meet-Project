"""텍스트·날짜 유틸 — 한국식 날짜·기간 찾기, 제목 정규화, 해시, 근거 검증.

표준 라이브러리만 쓴다 (백엔드가 import 해도 추가 설치가 필요 없게).

학교 공지에서 실제로 보이는 표기 (2026-09 실측):
    2026. 10. 1.(목) ~ 10. 2.(금) 16:00         2026. 9. 15.(화) 10:00 ~ 9. 16.(수)18:00
    2026. 8. 18.( 화 ) ~ 10. 28.( 수 )           '26. 9. 2.(수) 09:00 ~ 9. 9.(수) 18:00
    2026. 9. 21.(월) ~ 9.30(수)                  8.7.(4학년), 8.10.(3학년), 8.13~14(전학년 공통)
    (~10.14.)                                    2026년 9월 30일(수) 오후 6시
걸러야 하는 것: '수업일수 1/4' · '평점 3.5/4.5' · 전화번호 · '2일간'.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

# ── 문자열 ──────────────────────────────────────────────────

WS = re.compile(r"[ \t 　]+")


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def squash(s: str) -> str:
    """공백·기호를 뺀 소문자 — 근거 인용 비교용."""
    return re.sub(r"[\s\W_]+", "", nfkc(s)).lower()


def short_hash(*parts: str, n: int = 10) -> str:
    h = hashlib.sha1()
    for p in parts:
        h.update((p or "").encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()[:n]


def tidy(s: str) -> str:
    """괄호 안쪽 공백 '( 미등록 )' → '(미등록)', 연속 공백 한 칸."""
    s = WS.sub(" ", nfkc(s)).strip()
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return s


_TAGS = re.compile(r"^\s*(?:\[[^\]]*\]\s*)+")
_TAIL_WORDS = re.compile(r"\s*(?:실시\s*안내|시행\s*안내|신청\s*안내|안내|공고|공지|알림|실시|알려드립니다)\s*$")
_TITLE_DATE = re.compile(r"\(\s*[~∼]?\s*[\d.\s~∼/]+\s*\)")   # 제목 끝의 '(~10.14.)' · '(9.4.~ 9.6.)'


def clean_post_title(title: str) -> str:
    """공지 제목 → 일정 이름. '[학사안내] 2026학년도 제2학기 최종 등록 공고' → '제2학기 최종 등록'."""
    t = tidy(title)
    t = _TAGS.sub("", t)
    t = _TITLE_DATE.sub("", t)
    t = re.sub(r"^20\d{2}\s*학년도\s*", "", t)
    t = re.sub(r"\(홈페이지\s*게시용\)", "", t)
    for _ in range(3):
        t2 = _TAIL_WORDS.sub("", t)
        if t2 == t:
            break
        t = t2
    return t.strip(" -·:") or tidy(title)


def normalize_title(title: str) -> str:
    """같은 일정인지 비교하는 키. 말머리·학년도·공백·기호·'기간/안내' 같은 꼬리말을 뺀다. (4학년) 같은 괄호 안 글자는 남긴다."""
    t = nfkc(title).lower()
    t = _TAGS.sub("", t)
    t = re.sub(r"\[[^\]]*\]", "", t)
    t = re.sub(r"20\d{2}\s*학년도", "", t)
    t = re.sub(r"['’](\d{2})\s*년", r"20\1년", t)             # "('26년 8월)" = "(2026년 8월)"
    t = re.sub(r"제\s*(\d)\s*학기", r"\1학기", t)
    t = re.sub(r"\(\s*[월화수목금토일]\s*\)", "", t)
    t = re.sub(r"[^0-9a-z가-힣]+", "", t)
    for _ in range(2):
        t = re.sub(r"(안내|공고|실시|알림|기간|일정)$", "", t)
    return t


# ── 날짜 찾기 ───────────────────────────────────────────────

_WD = r"[월화수목금토일]"
_PAREN = rf"\(\s*(?:{_WD}|\d\s*학년|전\s*학년[^)]{{0,12}})\s*\)"
_TIME = (r"(?:(?P<ampm>오전|오후)\s*)?(?P<h>[01]?\d|2[0-3])\s*"
         r"(?::\s*(?P<mi>[0-5]\d)|시(?:\s*(?P<mi2>[0-5]?\d)\s*분)?)")

DATE_RE = re.compile(
    r"(?<![\d.:/])"
    r"(?:(?P<y>20\d{2}|['’]\d{2})\s*(?:[.\-/]|년)\s*)?"
    r"(?P<m>1[0-2]|0?[1-9])\s*(?P<sep>[.\-/]|월)\s*"
    r"(?P<d>3[01]|[12]\d|0?[1-9])(?!\d)"
    r"(?P<tail>\s*일)?(?P<dot>\s*\.)?"
    rf"(?P<paren>\s*{_PAREN})?"
    rf"(?:\s*,?\s*{_TIME})?"
)
_RANGE_SEP = r"(?:~|∼|〜|-|–|—)"
DAY_ONLY_RE = re.compile(
    rf"^\s*{_RANGE_SEP}\s*(?P<d>3[01]|[12]\d|0?[1-9])(?!\d)(?!\s*[.\-/월]\s*\d)(?!\s*[:시])\s*일?\.?"
    rf"(?:\s*{_PAREN})?(?:\s*,?\s*{_TIME})?"
)
TIME_ONLY_RE = re.compile(rf"^\s*{_RANGE_SEP}\s*{_TIME}")
_SEP_BETWEEN = re.compile(rf"{_RANGE_SEP}|부터|에서")


@dataclass
class Span:
    """글 안에서 찾은 날짜 하나 또는 기간 하나."""
    start: date
    start_time: Optional[str]          # 'HH:MM'
    end: Optional[date]                # 마지막 날(포함). 하루짜리면 None
    end_time: Optional[str]
    pos: int                           # 원문에서 시작 위치
    pos_end: int
    year_explicit: bool                # 시작 날짜에 연도가 적혀 있었나
    deadline: bool = False             # '~까지' 처럼 끝만 있는 표기

    @property
    def is_period(self) -> bool:
        return self.end is not None and self.end > self.start


def _time_of(m: re.Match) -> Optional[str]:
    h = m.groupdict().get("h")
    if h is None:
        return None
    hh = int(h)
    mi = m.groupdict().get("mi") or m.groupdict().get("mi2") or "0"
    if m.groupdict().get("ampm") == "오후" and hh < 12:
        hh += 12
    return f"{hh:02d}:{int(mi):02d}"


def _year_of(raw: Optional[str]) -> Optional[int]:
    if not raw:
        return None
    raw = raw.strip("'’")
    return int(raw) if len(raw) == 4 else 2000 + int(raw)


def _guess_year(month: int, ctx_year: int, ctx_month: int) -> int:
    """연도 없는 날짜의 연도 — 글이 쓰인 달과 너무 멀면 앞뒤 해로 넘긴다 (12월 글의 '1. 5.' → 다음 해)."""
    diff = month - ctx_month
    if diff < -5:
        return ctx_year + 1
    if diff > 6:
        return ctx_year - 1
    return ctx_year


def _mkdate(y: int, m: int, d: int) -> Optional[date]:
    try:
        return date(y, m, d)
    except ValueError:
        return None          # 2월 30일 같은 없는 날짜


def _accept(text: str, m: re.Match) -> bool:
    """연도 없는 'm.d' 가 정말 날짜인가 — 표지(끝 점·요일·월/일·범위 기호)가 하나는 있어야 한다."""
    before = text[max(0, m.start() - 8):m.start()]
    after = text[m.end():m.end() + 3]
    if m["sep"] == "/" and (re.match(r"\s*선", text[m.end("d"):m.end("d") + 3]) or "수업일수" in before):
        return False           # '수업일수 1/4선'
    if m["y"]:
        return True
    if m["dot"] or m["paren"] or m["tail"] or m["sep"] == "월":
        return True
    if re.search(rf"{_RANGE_SEP}\s*$", before) or re.match(rf"\s*(?:{_RANGE_SEP}|까지|부터)", after):
        return True
    return False


def find_spans(text: str, ctx: date) -> list[Span]:
    """text 안의 날짜·기간을 순서대로. ctx 는 연도를 추정할 기준(공지 게시일 등).

    - 연도가 없으면 ctx(또는 같은 줄 앞쪽에 나온 연도)를 물려받는다.
    - 두 날짜 사이에 '~' '부터' 가 있으면(표 칸 경계 ' | ' 는 넘지 않음) 기간으로 묶는다.
    - '8.13~14' 처럼 뒤쪽이 일(日)만 있거나 '10:00 ~ 17:00' 처럼 시각만 있으면 앞 날짜의 연·월을 물려받는다.
    """
    text = nfkc(text)
    year_ctx, month_ctx = ctx.year, ctx.month
    hits: list[tuple[re.Match, date, bool]] = []
    for m in DATE_RE.finditer(text):
        if not _accept(text, m):
            continue
        y = _year_of(m["y"])
        explicit = y is not None
        if y is None:
            y = _guess_year(int(m["m"]), year_ctx, month_ctx)
        d = _mkdate(y, int(m["m"]), int(m["d"]))
        if d is None:
            continue
        if explicit:
            year_ctx, month_ctx = d.year, d.month
        hits.append((m, d, explicit))

    spans: list[Span] = []
    i = 0
    while i < len(hits):
        m, d, explicit = hits[i]
        st = _time_of(m)
        end: Optional[date] = None
        et: Optional[str] = None
        pos_end = m.end()
        joined = False
        if i + 1 < len(hits):
            m2, d2, _ = hits[i + 1]
            between = text[m.end():m2.start()]
            if "|" not in between and len(between) <= 40 and _SEP_BETWEEN.search(between):
                end, et, pos_end = d2, _time_of(m2), m2.end()
                if end < d:                       # '12. 28. ~ 1. 8.' — 해가 넘어간다
                    end = _mkdate(end.year + 1, end.month, end.day) or end
                joined = True
        if not joined:
            rest = text[m.end():]
            dm = DAY_ONLY_RE.match(rest)
            tm = TIME_ONLY_RE.match(rest)
            if dm:
                end = _mkdate(d.year, d.month, int(dm["d"]))
                if end and end < d:               # '1. 30. ~ 2.' 같은 달 넘김은 없다고 본다 → 다음 달
                    nm = d.month % 12 + 1
                    end = _mkdate(d.year + (d.month == 12), nm, int(dm["d"]))
                et = _time_of(dm)
                pos_end = m.end() + dm.end()
            elif tm and st:
                end, et, pos_end = d, _time_of(tm), m.end() + tm.end()
        before = text[max(0, m.start() - 3):m.start()]
        after = text[pos_end:pos_end + 6]
        deadline = end is None and (bool(re.search(rf"{_RANGE_SEP}\s*$", before)) or "까지" in after or "마감" in after)
        if end == d and et is None:
            end = None
        spans.append(Span(start=d, start_time=st, end=end, end_time=et, pos=m.start(), pos_end=pos_end,
                          year_explicit=explicit, deadline=deadline))
        i += 2 if joined else 1
    return spans


def iso_date(d: Optional[date]) -> Optional[str]:
    return d.isoformat() if d else None


def parse_iso_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def add_days(d: date, n: int) -> date:
    return d + timedelta(days=n)


# ── 게시판 주소 ─────────────────────────────────────────────

_BOARD_PATH = re.compile(r"/bbs/(?P<site>[\w-]+)/(?P<board>\d+)(?:/|$)")


def parse_board_url(url: str) -> Optional[dict]:
    """학과·단과대 홈페이지(K2Web) 게시판 주소 → {base, site, board, category, categoryParam}. 형식이 다르면 None.

    'https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do?bbsOpenWrdSeq=236' → aisw / 64 / 말머리 236
    말머리는 사이트에 따라 bbsOpenWrdSeq 또는 bbsClSeq 로 온다.
    """
    from urllib.parse import parse_qs, urlparse
    u = urlparse((url or "").strip())
    if u.scheme not in ("http", "https") or not u.netloc:
        return None
    m = _BOARD_PATH.search(u.path)
    if not m:
        return None
    q = parse_qs(u.query)
    param = next((k for k in ("bbsOpenWrdSeq", "bbsClSeq") if q.get(k, [""])[0]), None)
    return {"base": f"{u.scheme}://{u.netloc}", "site": m["site"], "board": m["board"],
            "category": q[param][0] if param else None, "categoryParam": param}


# ── 근거 검증 ───────────────────────────────────────────────

def is_grounded(quote: str, source_text: str, min_len: int = 6) -> bool:
    """근거 인용이 원문에 실제로 있는가 (공백·기호 차이만 무시). 없으면 모델이 지어낸 값일 수 있다 → 버린다 (F1-R12).

    날짜를 이 인용문에서 다시 읽으므로 '앞 절반만 맞으면 인정' 같은 느슨한 비교를 하지 않는다 — 날짜 부분이 다를 수 있다.
    """
    q, s = squash(quote), squash(source_text)
    return len(q) >= min_len and q in s
