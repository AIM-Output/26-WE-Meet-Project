"""시간표 — ① 강의시간 파서 (순수 함수) ② 학사정보시스템 시간표 조회 수집기 (표준 라이브러리 urllib).

① 강의시간 원문은 `요일 한 글자 + 교시 숫자` 의 반복이다 (F3 2절).
      '화5목5'          → 화 5교시 · 목 5교시
      '월5월6수5'       → 월 5·6교시(연강) · 수 5교시
      '수10수11수8수9'  → 수 8·9·10·11교시 (원문 순서가 섞여 있어도 정렬한다 — 2026-09-28 실측)
   같은 요일이라도 교시가 이어지지 않으면('월1월3') 따로 떨어진 수업 두 개로 본다.
   강의실 칸은 토큰마다 한 줄이다('공2-100<br>공2-100<br>공2-100') → 토큰 순서대로 짝짓는다.

② 교과목조회 `Suup053C.aspx` (로그인 불필요). ASP.NET 포스트백 — 첫 GET 의 __VIEWSTATE 등을 들고 POST.
   e클래스 과목명 `운영체제[2] (CIS2001)` → 이름 '운영체제' 로 검색 → 결과의 `CIS2001-2` 행을 고른다.
   학수번호로 검색하면 0건이고, 학년(ddlGrade)은 필수지만 결과를 거르지 않는다(실측) → 과목당 1회.
"""
from __future__ import annotations

import html
import http.cookiejar
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import Any, Callable, Iterable, Optional

from . import config as C

_TOKEN = re.compile(r"([월화수목금토일])\s*(\d{1,2})")
_JUNK = re.compile(r"[\s,/·]+")


class ParseError(ValueError):
    pass


def parse_times(raw: str, rooms: Optional[Iterable[str]] = None) -> list[dict]:
    """강의시간 원문 → [{weekday: 0(월)~6(일), periods: [..], room}] (요일·첫 교시 순).
    읽지 못하는 글자가 섞여 있으면 ParseError — 모르는 형식을 아는 척하지 않는다."""
    text = (raw or "").strip()
    if not text:
        return []
    tokens = [(m.group(1), int(m.group(2))) for m in _TOKEN.finditer(text)]
    if not tokens or _JUNK.sub("", _TOKEN.sub("", text)):
        raise ParseError(f"강의시간을 읽지 못했습니다: {raw!r}")
    room_list = [r.strip() for r in (rooms or [])]
    by_day: dict[int, dict[int, str]] = {}
    for i, (day, period) in enumerate(tokens):
        if not 1 <= period <= 15:
            raise ParseError(f"교시가 이상합니다: {day}{period}")
        room = room_list[i] if i < len(room_list) else (room_list[-1] if room_list else "")
        by_day.setdefault(C.WEEKDAYS.index(day), {})[period] = room
    out = []
    for wd in sorted(by_day):
        periods = sorted(by_day[wd])
        run: list[int] = []
        for p in periods + [None]:              # type: ignore[list-item]
            if run and (p is None or p != run[-1] + 1):
                rooms_in = [by_day[wd][x] for x in run if by_day[wd][x]]
                out.append({"weekday": wd, "periods": run, "room": ", ".join(dict.fromkeys(rooms_in))})
                run = []
            if p is not None:
                run.append(p)
    return out


def meeting_text(m: dict) -> str:
    """{weekday: 0, periods: [5, 6]} → '월 5·6교시'"""
    return f"{C.WEEKDAYS[m['weekday']]} {'·'.join(str(p) for p in m['periods'])}교시"


def meetings_text(ms: list[dict]) -> str:
    return " · ".join(meeting_text(m) for m in ms)


def normalize_meetings(ms: Any) -> list[dict]:
    """사용자가 보낸 요일·교시를 검사해 저장할 모양으로. 틀리면 ParseError."""
    if not isinstance(ms, list):
        raise ParseError("요일·교시는 목록이어야 합니다")
    out, seen = [], set()
    for m in ms:
        if not isinstance(m, dict):
            raise ParseError("요일·교시 한 줄은 {weekday, periods} 입니다")
        wd = m.get("weekday")
        if isinstance(wd, str) and wd in C.WEEKDAYS:
            wd = C.WEEKDAYS.index(wd)
        if not isinstance(wd, int) or not 0 <= wd <= 6:
            raise ParseError(f"요일이 이상합니다: {m.get('weekday')!r}")
        try:
            periods = sorted({int(p) for p in (m.get("periods") or [])})
        except (TypeError, ValueError) as e:
            raise ParseError("교시는 숫자입니다") from e
        if not periods:
            raise ParseError(f"{C.WEEKDAYS[wd]}요일 교시가 비었습니다")
        limit = max(C.MODULE_TT) if C.WEEKDAY_MODULE[wd] == "tt" else max(C.MODULE_MWF)
        if periods[0] < 1 or periods[-1] > limit:
            raise ParseError(f"{C.WEEKDAYS[wd]}요일은 1~{limit}교시입니다")
        for p in periods:
            if (wd, p) in seen:
                raise ParseError(f"{C.WEEKDAYS[wd]} {p}교시가 두 번 들어 있습니다")
            seen.add((wd, p))
        # 이어지지 않는 교시는 따로 떨어진 수업으로 나눈다 (파서와 같은 규칙)
        run: list[int] = []
        for p in periods + [None]:              # type: ignore[list-item]
            if run and (p is None or p != run[-1] + 1):
                out.append({"weekday": wd, "periods": run, "room": str(m.get("room") or "").strip()[:60]})
                run = []
            if p is not None:
                run.append(p)
    return sorted(out, key=lambda x: (x["weekday"], x["periods"][0]))


# ── ② 시간표 조회 ────────────────────────────────────────────

class _Rows(HTMLParser):
    """결과 표 gvData 의 행 → {data-th: 글자}. 칸 안의 <br> 는 '\\n' 으로 남긴다(강의실 토큰 구분)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[dict[str, str]] = []
        self.hidden: dict[str, str] = {}
        self.total: Optional[int] = None
        self._in_table = 0
        self._row: Optional[dict[str, str]] = None
        self._cell: Optional[str] = None
        self._buf: list[str] = []
        self._total_span = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        a = {k: (v or "") for k, v in attrs}
        if tag == "input" and a.get("type") == "hidden" and a.get("name"):
            self.hidden[a["name"]] = a.get("value", "")
        elif tag == "span" and a.get("id", "").endswith("lblTcnt"):
            self._total_span = True
        elif tag == "table" and a.get("id", "").endswith("gvData"):
            self._in_table = 1
        elif tag == "table" and self._in_table:
            self._in_table += 1
        elif self._in_table and tag == "tr":
            self._row = {}
        elif self._in_table and tag == "td" and self._row is not None and a.get("data-th"):
            self._cell, self._buf = a["data-th"], []
        elif tag == "br" and self._cell is not None:
            self._buf.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._cell is not None and self._row is not None:
            txt = "".join(self._buf)
            lines = [re.sub(r"\s+", " ", x).strip() for x in txt.split("\n")]
            self._row[self._cell] = "\n".join(x for x in lines if x)
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
        elif tag == "table" and self._in_table:
            self._in_table -= 1
        elif tag == "span":
            self._total_span = False

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._buf.append(data)
        elif self._total_span and data.strip().isdigit():
            self.total = int(data.strip())


def parse_page(text: str) -> tuple[list[dict], dict[str, str], Optional[int]]:
    """조회 화면 HTML → (행 목록, 숨은 입력값, 'total' 숫자)."""
    p = _Rows()
    p.feed(text)
    rows = []
    for r in p.rows:
        code_sec = re.sub(r"\s+", "", r.get("교과목번호(분반)", ""))
        m = re.match(r"^([A-Za-z0-9]+)-?(\d+)$", code_sec)
        rows.append({
            "name": r.get("교과목명", "").replace("\n", " "),
            "code": m.group(1).upper() if m else code_sec,
            "section": str(int(m.group(2))) if m else "",
            "category": r.get("교과구분", ""),
            "targetGrade": r.get("대상학년", ""),
            "credits": r.get("학점", "").replace("\n", " "),
            "professor": r.get("담당교수", "").replace("\n", " "),
            "times": r.get("강의시간", "").replace("\n", ""),
            "rooms": [x for x in r.get("강의실", "").split("\n") if x],
            "campus": r.get("수업장소", "").replace("\n", " "),
        })
    return rows, p.hidden, p.total


class Http:
    """쿠키를 이어 가는 urllib 오프너 + 요청 간격 1.5초. 실패하면 3초·10초 뒤 다시."""

    def __init__(self, interval: float = C.REQUEST_INTERVAL) -> None:
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.opener.addheaders = [("User-Agent", C.USER_AGENT), ("Accept-Language", "ko-KR,ko;q=0.9")]
        self.interval = interval
        self._last = 0.0

    def fetch(self, url: str, data: Optional[dict] = None) -> str:
        body = urllib.parse.urlencode(data).encode("utf-8") if data is not None else None
        waits = (0,) + C.RETRY_WAITS
        err: Optional[Exception] = None
        for w in waits:
            if w:
                time.sleep(w)
            gap = self.interval - (time.monotonic() - self._last)
            if gap > 0:
                time.sleep(gap)
            try:
                req = urllib.request.Request(url, data=body, headers={"Referer": url} if body else {})
                with self.opener.open(req, timeout=C.HTTP_TIMEOUT) as res:
                    raw = res.read()
                self._last = time.monotonic()
                return raw.decode("utf-8", "replace")
            except Exception as e:                       # noqa: BLE001 — 네트워크 오류는 다시 시도
                self._last = time.monotonic()
                err = e
        raise ConnectionError(f"시간표 조회에 접속하지 못했습니다: {err}")


class TimetableSearch:
    """교과목조회 화면 하나를 붙잡고 여러 과목을 차례로 검색한다 (포스트백마다 새 __VIEWSTATE 를 쓴다)."""

    def __init__(self, year: int, term: str, grade: int = 1, http: Optional[Http] = None) -> None:
        if term not in C.TERM_CODES:
            raise ValueError(f"학기를 모릅니다: {term}")
        self.year, self.term, self.grade = year, C.TERM_CODES[term], grade
        self.http = http or Http()
        self._hidden: Optional[dict[str, str]] = None

    def search(self, name: str) -> list[dict]:
        if self._hidden is None:
            _, self._hidden, _ = parse_page(self.http.fetch(C.TIMETABLE_URL))
        P = C.FORM_PREFIX
        form = {k: v for k, v in self._hidden.items() if k.startswith("__")}
        form.update({
            "__EVENTTARGET": P + "ibtnSearch", "__EVENTARGUMENT": "",
            P + "ddlYear": str(self.year), P + "ddlTerm": self.term, P + "ddlGrade": str(self.grade),
            P + "hakgubun": "0",                         # 학부
            P + "txtSubj": name, P + "txtEmp_Name": "", P + "hdLang": "KOR",
        })
        rows, hidden, _ = parse_page(self.http.fetch(C.TIMETABLE_URL, form))
        if hidden.get("__VIEWSTATE"):
            self._hidden = hidden
        return rows


def search_names(short: str) -> list[str]:
    """검색에 쓸 이름 후보 — 전체 이름, 없으면 괄호 앞 ('산학협력프로젝트(캡스톤디자인)' → '산학협력프로젝트')."""
    s = html.unescape(short or "").strip()
    out = [s] if s else []
    base = re.split(r"[\(\[（]", s)[0].strip()
    if base and base != s:
        out.append(base)
    return out


def pick_row(rows: list[dict], code: str, section: str) -> Optional[dict]:
    code, section = (code or "").upper(), str(int(section)) if str(section or "").isdigit() else str(section or "")
    for r in rows:
        if r["code"] == code and r["section"] == section:
            return r
    return None


def lookup(courses: list[dict], year: int, term: str, grade: int = 1, *, search: Optional[TimetableSearch] = None,
           log: Callable[[str], None] = lambda s: None) -> list[dict]:
    """과목마다 시간표 행을 찾아 요일·교시로. 반환 [{courseId, status, meetings, raw, message}].
    status: found · not_found(학수번호+분반 행 없음) · no_time(강의시간 칸이 빔 — 원격·집중강의) · parse_error · no_code · error"""
    s = search or TimetableSearch(year, term, grade)
    out = []
    cache: dict[str, list[dict]] = {}
    for c in courses:
        base = {"courseId": c["id"], "name": c.get("short") or c.get("name"), "meetings": [], "raw": None}
        if not c.get("code") or not c.get("section"):
            out.append({**base, "status": "no_code", "message": "학수번호·분반을 몰라 찾을 수 없습니다"})
            continue
        row = None
        try:
            for name in search_names(c.get("short") or c.get("name") or ""):
                if name not in cache:
                    cache[name] = s.search(name)
                    log(f"검색 '{name}' → {len(cache[name])}행")
                row = pick_row(cache[name], c["code"], c["section"])
                if row or cache[name]:
                    break
        except Exception as e:                           # noqa: BLE001 — 한 과목이 실패해도 나머지는 계속
            out.append({**base, "status": "error", "message": str(e)[:200]})
            continue
        if not row:
            out.append({**base, "status": "not_found",
                        "message": f"시간표에서 {c['code']}-{c['section']} 을 찾지 못했습니다"})
            continue
        raw = {k: row[k] for k in ("times", "rooms", "professor", "campus", "credits", "category")}
        if not row["times"]:
            out.append({**base, "raw": raw, "status": "no_time",
                        "message": "시간표에 강의시간이 없습니다 (원격·집중강의일 수 있음)"})
            continue
        try:
            ms = parse_times(row["times"], row["rooms"])
        except ParseError as e:
            out.append({**base, "raw": raw, "status": "parse_error", "message": str(e)})
            continue
        out.append({**base, "raw": raw, "status": "found", "meetings": ms, "message": meetings_text(ms)})
    return out
