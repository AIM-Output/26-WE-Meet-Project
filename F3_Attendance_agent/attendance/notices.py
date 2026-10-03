"""e클래스 과목 공지에서 휴강 찾기 (2026-09-29 수정 ③) — 표준 라이브러리만. F6 e클래스 수집이 모은 글을 읽기만 한다.

원천: F6_Eclass_agent/data/manifest.json 의 posts(과목 id · 게시판 · 작성일 · .md 경로)와 그 .md(제목 + 본문).
      F6 는 이름에 '공지'·'자료'가 들어간 게시판만 모은다(F6_Eclass_agent/eclass/config.py BOARD_INCLUDE).

규칙 — '휴강'이 들어간 줄마다 날짜를 찾는다 (2026-09-28 실제 공지 4건으로 맞춤)
    '9월 17일 목요일 휴강'              → 9/17
    '오늘 수업 휴강(9/16)'              → 9/16 (날짜가 있으면 그것, '오늘'은 작성일)
    '금일 수업은 휴강하겠습니다'         → 작성일
    '다음 주 화요일 휴강' · '이번 주 휴강' → 작성일 기준 그 요일 / 그 주 전체
    '9월 16일~18일 휴강'                → 기간 (14일까지)
    '휴강 없이 정상 수업' · '휴강 취소'   → 건너뛴다(부정)
    '9월 17일 휴강, 보강은 9월 24일'     → '보강…' 구절의 날짜는 빼고 9/17 만
  휴강 줄에 날짜가 없으면 같은 글 제목의 날짜를 쓴다. 그래도 없으면 '확인 필요'(hints)로 화면에 링크만 띄운다.
  찾은 날짜가 그 과목의 수업일이 아니면 sessions.build 가 버린다(수업일에만 휴강을 건다).

결과는 manifest 가 바뀔 때만 다시 읽는다(수정 시각·크기로 캐시).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import config as C

_CANCEL = re.compile(r"휴\s*강")
_NEGATE = re.compile(r"휴\s*강\s*(?:을|은|는|이)?\s*(?:하지\s*않|안\s*[하합]|없|취소|아님|철회)|정상\s*(?:수업|진행)|휴강\s*없이")
_MAKEUP_CLAUSE = re.compile(r"보\s*강[^,.\n]*")
_KO_RANGE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\([월화수목금토일]\))?\s*[~\-–]\s*(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일")
_KO_DATE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_NUM_RANGE = re.compile(r"(?<![\d.:])(\d{1,2})\s*[/.]\s*(\d{1,2})\s*[~\-–]\s*(\d{1,2})\s*[/.]\s*(\d{1,2})(?![\d:])")
_NUM_DATE = re.compile(r"(?<![\d.:/])(\d{1,2})\s*[/.]\s*(\d{1,2})(?![\d.:/]|\s*(?:학점|점|%|시간|교시))")
_REL_DAY = {"오늘": 0, "금일": 0, "내일": 1, "명일": 1, "모레": 2}
_REL = re.compile(r"오늘|금일|내일|명일|모레")
_WEEKDAY = re.compile(r"(이번\s*주|금주|다음\s*주|차주)?\s*([월화수목금토일])\s*요일")
_WEEK = re.compile(r"(이번\s*주|금주|다음\s*주|차주)(?!\s*[월화수목금토일]\s*요일)")
_WD = "월화수목금토일"
_POSTED = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")

_cache: dict[str, Any] = {"key": None, "value": None}


def _mk(m: int, d: int, posted: date) -> Optional[date]:
    """연도가 없는 월·일 → 작성일에 가장 가까운 해 (12월에 쓴 '1월 5일'은 다음 해)."""
    try:
        cands = [date(y, m, d) for y in (posted.year - 1, posted.year, posted.year + 1)]
    except ValueError:
        return None
    return min(cands, key=lambda x: abs((x - posted).days))


def _expand(a: Optional[date], b: Optional[date]) -> list[date]:
    if not a or not b or b < a or (b - a).days > C.NOTICE_RANGE_MAX_DAYS:
        return [a] if a else []
    return [a + timedelta(days=i) for i in range((b - a).days + 1)]


def dates_in(text: str, posted: date) -> list[date]:
    """한 구절에서 날짜들. 명시 날짜 > 상대 표현(오늘·다음 주 화요일·이번 주)."""
    out: list[date] = []
    used = [False] * len(text)

    def take(m: re.Match) -> None:
        for i in range(m.start(), m.end()):
            used[i] = True

    for m in _KO_RANGE.finditer(text):
        a = _mk(int(m.group(1)), int(m.group(2)), posted)
        b = _mk(int(m.group(3) or m.group(1)), int(m.group(4)), posted)
        out += _expand(a, b)
        take(m)
    for m in _NUM_RANGE.finditer(text):
        out += _expand(_mk(int(m.group(1)), int(m.group(2)), posted), _mk(int(m.group(3)), int(m.group(4)), posted))
        take(m)
    for m in _KO_DATE.finditer(text):
        if not any(used[m.start():m.end()]):
            if d := _mk(int(m.group(1)), int(m.group(2)), posted):
                out.append(d)
            take(m)
    for m in _NUM_DATE.finditer(text):
        if not any(used[m.start():m.end()]) and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
            if d := _mk(int(m.group(1)), int(m.group(2)), posted):
                out.append(d)
    if out:
        return sorted(set(out))
    for m in _REL.finditer(text):
        out.append(posted + timedelta(days=_REL_DAY[m.group(0)]))
    monday = posted - timedelta(days=posted.weekday())
    for m in _WEEKDAY.finditer(text):
        wd = _WD.index(m.group(2))
        which = re.sub(r"\s", "", m.group(1) or "")
        if which in ("다음주", "차주"):
            out.append(monday + timedelta(days=7 + wd))
        elif which in ("이번주", "금주"):
            out.append(monday + timedelta(days=wd))
        else:                                             # 그냥 '목요일' — 작성일 이후 첫 그 요일
            out.append(posted + timedelta(days=(wd - posted.weekday()) % 7))
    if not out:
        for m in _WEEK.finditer(text):
            base = monday + timedelta(days=7 if re.sub(r"\s", "", m.group(1)) in ("다음주", "차주") else 0)
            out += [base + timedelta(days=i) for i in range(7)]
    return sorted(set(out))


def cancel_dates(title: str, body: str, posted: date) -> tuple[list[date], bool]:
    """글 하나 → (휴강 날짜들, 휴강을 말하는가). 날짜를 못 찾아도 휴강을 말하면 두 번째가 True(확인 필요)."""
    mentioned = False
    found: list[date] = []
    title_dates = dates_in(_MAKEUP_CLAUSE.sub(" ", title), posted)
    for line in [title, *body.splitlines()]:
        if not _CANCEL.search(line) or _NEGATE.search(line):
            continue
        mentioned = True
        found += dates_in(_MAKEUP_CLAUSE.sub(" ", line), posted)
    if mentioned and not found and _CANCEL.search(title):
        found = title_dates
    if mentioned and not found:
        found = [d for d in title_dates if _CANCEL.search(body)]
    return sorted(set(found)), mentioned


def _body(md: str) -> tuple[str, str]:
    """F6 수집기가 쓴 .md → (제목, 본문). 머리 목록(과목·게시판·작성자·링크)과 첨부 목록은 뺀다."""
    lines = md.splitlines()
    title = lines[0].lstrip("# ").strip() if lines else ""
    try:
        i = lines.index("## 본문")
        body = "\n".join(lines[i + 1:])
    except ValueError:
        body = "\n".join(l for l in lines[1:] if not l.startswith("- "))
    return title, body


def load(manifest: Optional[Path] = None, root: Optional[Path] = None) -> dict:
    """{available, stamp, byCourse: {과목 id: {cancels: {날짜: {reason, url, posted}}, hints: [...]}}}"""
    manifest = Path(manifest or C.ECLASS_MANIFEST)
    root = Path(root or C.ECLASS_ROOT)
    try:
        st = manifest.stat()
    except OSError:
        return {"available": False, "stamp": None, "byCourse": {}}
    key = (str(manifest), st.st_mtime_ns, st.st_size)
    if _cache["key"] == key:
        return _cache["value"]
    try:
        posts = (json.loads(manifest.read_text(encoding="utf-8")) or {}).get("posts") or {}
    except (OSError, ValueError):
        return {"available": False, "stamp": None, "byCourse": {}}
    by: dict[str, dict] = {}
    for p in posts.values():
        cid = str(p.get("course_id") or "")
        m = _POSTED.search(str(p.get("date") or "")) or _POSTED.search(Path(str(p.get("path") or "")).name)
        if not cid or not m:
            continue
        try:
            posted = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        title = str(p.get("title") or "")
        body = ""
        path = root / str(p.get("path") or "").replace("\\", "/")
        try:
            title, body = _body(path.read_text(encoding="utf-8"))
        except OSError:
            pass
        if not _CANCEL.search(title + body):
            continue
        dates, mentioned = cancel_dates(title, body, posted)
        slot = by.setdefault(cid, {"cancels": {}, "hints": []})
        src = {"reason": title, "url": p.get("url"), "posted": posted.isoformat(), "board": p.get("activity")}
        for d in dates:
            slot["cancels"].setdefault(d.isoformat(), src)
        if mentioned and not dates:
            slot["hints"].append({**src, "why": "휴강 공지인데 날짜를 찾지 못했습니다"})
    # 마이크로초까지 — 같은 밀리초 안에 두 번 쓰이면 도장이 같아 화면이 다시 부르지 않았다
    value = {"available": True, "stamp": datetime.fromtimestamp(st.st_mtime_ns / 1e9).isoformat(timespec="microseconds"),
             "byCourse": by}
    _cache.update(key=key, value=value)
    return value
