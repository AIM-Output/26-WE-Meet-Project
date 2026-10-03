"""e클래스 과목 공지에서 시험 찾기 (F5-R01·R02) — 표준 라이브러리만. F6 수집이 모은 글을 읽기만 한다.

원천: F6_Eclass_agent/data/manifest.json 의 posts(과목 id · 게시판 · 작성일 · .md 경로)와 그 .md(제목 + 본문).
      F6 는 이름에 '공지'·'자료'가 들어간 게시판만 모은다(F6_Eclass_agent/eclass/config.py BOARD_INCLUDE).
      날짜 정규식은 F3 출결의 휴강 추출(2026-09-29 실측으로 맞춘 것)과 같은 계통이고, 시험에 필요한
      **시각·장소·범위**를 더 읽는다. LLM 을 부르지 않는다.

찾는 방법 — 글 하나에서 '언제'를 고르는 순서 (2026-09-30 실측 공지 18건으로 맞춤)
    1. 시험말(중간고사·기말·퀴즈·발표·시험)**과 날짜가 같은 줄**에 있으면 그 날짜
         '- 09월 16일: 기획서 발표 (발표 4분 이내)'      → 9/16 발표
    2. 줄머리가 **일시·일정·날짜·시험일** 같은 이름표면 그 줄의 날짜 (유형은 제목에서 가져온다)
         제목 '중간고사 장소 및 준비물 공지' + '1. 일정: 10월 22일 목요일 오후 3시부터 4시까지'
                                                        → 10/22 15:00~16:00 중간고사
    3. 제목에 날짜가 있으면 그것
    4. 본문 전체에 날짜가 **딱 하나**면 그것 (신뢰도를 깎는다)
  '범위' 줄 · '제출·마감' 줄 · '작년·지난 학기' 줄의 날짜는 시험일이 아니다 → 날짜 찾기에서 뺀다.
      '4. 시험 범위: 10월 15일 까지 강의한 내용 전반'     → 범위 문구로만 쓴다
  '발표 일정이 없습니다' · '시험 취소' 처럼 부정하는 줄은 건너뛴다.
  시험을 말하는데 날짜를 못 찾으면 '확인 필요'(hints)로 화면에 링크만 띄운다 — 조용히 버리지 않는다.

신뢰도 (F5-R02) — 1.0 에서 깎는다. `config.REVIEW_BELOW`(0.75) 밑이면 status='review' 로 승인을 받는다.
    제목이 아니라 본문에서 유형을 알았다 −0.15 · 이름표로 찾았다 −0.05 · 제목 날짜 −0.10 · 유일한 날짜 −0.20
    '오늘·다음 주' 같은 상대 표현 −0.20 · 중간·기말인데 날짜 후보가 여럿 −0.25
    시각 없음 −0.10 · 장소 없음 −0.05 · 범위 없음 −0.05
  근거 원문(evidence)은 항상 남긴다 — 화면에서 '공지 원문 보기'로 이어진다 (F5 9절 '신뢰').

결과는 manifest 가 바뀔 때만 다시 읽는다(수정 시각·크기로 캐시).
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from . import config as C

# ── 시험말 → 유형 (앞쪽이 이긴다) ──
_TYPE_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("midterm", re.compile(r"중간\s*(?:고사|시험|평가|테스트)")),
    ("final", re.compile(r"기말\s*(?:고사|시험|평가|테스트)")),
    ("quiz", re.compile(r"퀴즈|쪽지\s*시험|소\s*테스트")),
    ("presentation", re.compile(r"발\s*표")),
    ("etc", re.compile(r"시\s*험|고\s*사")),
)
_ANY_TYPE = re.compile(r"중간\s*(?:고사|시험|평가|테스트)|기말\s*(?:고사|시험|평가|테스트)|퀴즈|쪽지\s*시험|"
                       r"소\s*테스트|발\s*표|시\s*험|고\s*사")
# 부정 — '발표 일정이 없습니다' · '시험 취소' · '시험 없이'
_NEGATE = re.compile(r"(?:시\s*험|고\s*사|퀴즈|발\s*표)[^,.\n]{0,12}?(?:없|취소|안\s*[하합]|하지\s*않|철회|미정)")
# 줄머리 이름표 — 유형 말이 없어도 이 줄의 날짜는 시험 일시로 본다
_WHEN_LABEL = re.compile(r"(?:일\s*시|일\s*정|날\s*짜|시험\s*일|시험\s*날|고사\s*일|응시\s*일)\s*[:：]?")
_SCOPE_LABEL = re.compile(r"범\s*위")
# 제출·마감·신청 줄의 날짜는 시험일이 아니다 (F6 가 맡는 과제 마감이다)
_DEADLINE_LINE = re.compile(r"제\s*출|마\s*감|신\s*청|접\s*수|납\s*부|등\s*록")
# 지난 학기·작년 이야기의 날짜도 시험일이 아니다 ('작년 중간고사는 3월 2일이었습니다')
_PAST_LINE = re.compile(r"작\s*년|지난\s*(?:해|학기|학년도|번)|전\s*년\s*도|예\s*년|이\s*전\s*학기")

# ── 날짜 (F3 notices.py 와 같은 계통) ──
_KO_RANGE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일(?:\s*\([월화수목금토일]\))?\s*[~\-–]\s*"
                       r"(?:(\d{1,2})\s*월\s*)?(\d{1,2})\s*일")
_KO_DATE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_NUM_DATE = re.compile(r"(?<![\d.:/])(\d{1,2})\s*[/.]\s*(\d{1,2})(?![\d.:/]|\s*(?:학점|점|%|시간|교시|분|명|쪽|주))")
_REL_DAY = {"오늘": 0, "금일": 0, "내일": 1, "명일": 1, "모레": 2}
_REL = re.compile(r"오늘|금일|내일|명일|모레")
_WEEKDAY = re.compile(r"(이번\s*주|금주|다음\s*주|차주)?\s*([월화수목금토일])\s*요일")
_WD = "월화수목금토일"
_POSTED = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})")

# ── 시각 ──
_HHMM = re.compile(r"(?<![\d])([01]?\d|2[0-3])\s*:\s*([0-5]\d)(?![\d])")
_KO_TIME = re.compile(r"(오전|오후|아침|저녁|밤|낮)?\s*(\d{1,2})\s*시\s*(?:(\d{1,2})\s*분)?")
_PM_WORDS = {"오후", "저녁", "밤"}
_AM_WORDS = {"오전", "아침"}

# ── 장소 ──
#   이름표 뒤에 **`:` 나 `은/는` 이 있어야** 값으로 본다 — 없으면 '중간고사 장소 및 준비물 공지' 같은 제목에서
#   '및 준비물 공지'를 장소로 읽는다 (2026-09-30 실측 공지에서 실제로 그랬다).
_PLACE_LABEL = re.compile(r"(?:장\s*소|위\s*치|강의실|고사장|시험장|교\s*실)\s*(?:[:：]|은|는)\s*(.+)")
_ROOM = re.compile(r"[가-힣A-Za-z]{0,8}\s?\d{1,2}\s*-\s*\d{3,4}\s*(?:호|강의실)?")
_PAREN = re.compile(r"[(（][^)）]*[)）]")
_PLACE_TAIL = re.compile(r"\s*(?:에서|입니다|이다|이며|임|으로|로)\s*$")

# ── 범위 ──
_WEEK_RANGE = re.compile(r"(\d{1,2})\s*[~\-–]\s*(\d{1,2})\s*주\s*차?")
_WEEK_ONE = re.compile(r"(\d{1,2})\s*주\s*차")

# ── 발표 이름 (실측 공지에서 쓰인 말 — 없으면 유형 이름을 쓴다) ──
_PRESENT_NAMES = ("기획서", "제안서", "중간진도 점검", "중간진도", "진도 점검", "최종", "결과", "중간", "기말", "1차", "2차")

_cache: dict[str, Any] = {"key": None, "value": None}


# ---------------------------------------------------------------- 조각 읽기

def classify(text: str) -> Optional[str]:
    """시험말 → 유형. 없으면 None."""
    for kind, pat in _TYPE_PATTERNS:
        if pat.search(text):
            return kind
    return None


def _mk(m: int, d: int, posted: date) -> Optional[date]:
    """연도가 없는 월·일 → 작성일에 가장 가까운 해 (12월에 쓴 '1월 5일'은 다음 해)."""
    try:
        cands = [date(y, m, d) for y in (posted.year - 1, posted.year, posted.year + 1)]
    except ValueError:
        return None
    return min(cands, key=lambda x: abs((x - posted).days))


def dates_in(text: str, posted: date) -> tuple[list[date], bool]:
    """한 구절의 날짜들 + 상대 표현으로 찾았는지. 명시 날짜가 있으면 상대 표현은 보지 않는다."""
    out: list[date] = []
    used = [False] * len(text)

    def take(m: re.Match) -> None:
        for i in range(m.start(), m.end()):
            used[i] = True

    for m in _KO_RANGE.finditer(text):                       # '10월 21일~22일' → 앞뒤 둘 다 후보
        for mm, dd in ((int(m.group(1)), int(m.group(2))),
                       (int(m.group(3) or m.group(1)), int(m.group(4)))):
            if d := _mk(mm, dd, posted):
                out.append(d)
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
        return sorted(set(out)), False
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
        else:                                                # 그냥 '목요일' — 작성일 이후 첫 그 요일
            out.append(posted + timedelta(days=(wd - posted.weekday()) % 7))
    return sorted(set(out)), bool(out)


def times_in(text: str) -> tuple[str, str]:
    """한 줄의 (시작, 끝) 시각. 못 찾으면 ('', '') — 시각 없이 저장하고 '시각 미정'으로 보여 준다 (F5 8절).

    '오후 3시부터 4시까지' → 15:00 · 16:00 (뒤의 시각은 앞의 오전/오후를 물려받는다)
    오전·오후 표시가 없는 1~7시는 **오후로 본다** (대학 공지에서 '3시'는 15시다). 8시 이상은 그대로.
    """
    found: list[tuple[int, int, int, Optional[str]]] = []      # (위치, 시, 분, 오전/오후 또는 'exact')
    spans: list[tuple[int, int]] = []
    for m in _HHMM.finditer(text):
        found.append((m.start(), int(m.group(1)), int(m.group(2)), "exact"))
        spans.append((m.start(), m.end()))
    for m in _KO_TIME.finditer(text):
        if any(m.start() < e and s < m.end() for s, e in spans):               # '14:00 시' 같은 겹침
            continue
        mer = m.group(1)
        found.append((m.start(), int(m.group(2)), int(m.group(3) or 0),
                      "pm" if mer in _PM_WORDS else "am" if mer in _AM_WORDS else None))
    if not found:
        return "", ""
    found.sort()
    out: list[str] = []
    carried: Optional[str] = None
    for _, h, mi, mer in found[:2]:
        if mer == "exact":
            pass
        else:
            if mer:
                carried = mer
            elif carried:
                mer = carried
            if mer == "pm" and h < 12:
                h += 12
            elif mer == "am" and h == 12:
                h = 0
            elif mer is None and 1 <= h <= 7:
                h += 12                                        # '3시' → 15:00
        if not 0 <= h <= 23 or not 0 <= mi <= 59:
            continue
        out.append(f"{h:02d}:{mi:02d}")
    start = out[0] if out else ""
    end = out[1] if len(out) > 1 and out[1] > out[0] else ""
    return start, end


def place_in(line: str) -> str:
    """장소. 이름표(`위치:`)가 있으면 그 뒤, 없으면 강의실 번호(`공7-223`)."""
    if m := _PLACE_LABEL.search(line):
        value = _PAREN.sub(" ", m.group(1))                    # '박물관 시청각실 (미리 파악해두세요!)' → 앞부분만
        value = _PLACE_TAIL.sub("", value.strip(" .·-—:："))
        return re.split(r"[,，/]| 및 ", value)[0].strip()[:80]
    if m := _ROOM.search(line):
        return re.sub(r"\s+", "", m.group(0))[:80]
    return ""


def scope_in(lines: list[str]) -> tuple[list[int], str]:
    """'범위' 줄 → (주차들, 원문 문구). '3~7주차' 는 3·4·5·6·7 로 펼친다 (F5-R06)."""
    weeks: set[int] = set()
    note = ""
    for line in lines:
        if not _SCOPE_LABEL.search(line):
            continue
        text = line.split("범위", 1)[1].lstrip(" :：는은을") if "범위" in line else line
        text = text.strip(" .·-—")
        if text and not note:
            note = text[:200]
        for m in _WEEK_RANGE.finditer(line):
            a, b = int(m.group(1)), int(m.group(2))
            if 1 <= a <= b <= 20:
                weeks.update(range(a, b + 1))
        for m in _WEEK_ONE.finditer(line):
            w = int(m.group(1))
            if 1 <= w <= 20:
                weeks.add(w)
    return sorted(weeks), note


def _present_title(line: str) -> str:
    for name in _PRESENT_NAMES:
        if re.search(name + r"\s*발\s*표", line):
            return f"{name} 발표"
    return "발표"


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


# ---------------------------------------------------------------- 글 하나

def exams_in(title: str, body: str, posted: date) -> tuple[list[dict], list[str]]:
    """글 하나 → (찾은 시험들, 확인이 필요한 이유들). 날짜를 못 찾아도 시험을 말하면 이유를 남긴다."""
    lines = [title, *(l.strip() for l in body.splitlines())]
    lines = [l for l in lines if l]
    doc_type = classify(title)
    scope_weeks, scope_note = scope_in(lines)
    body_type = doc_type or next((t for l in lines if (t := classify(l))), None)

    cands: list[dict] = []
    for line in lines:
        if _NEGATE.search(line):
            continue
        if _SCOPE_LABEL.search(line) or _DEADLINE_LINE.search(line) or _PAST_LINE.search(line):
            continue                                            # 범위·제출 마감·지난 학기 줄의 날짜는 시험일이 아니다
        line_type = classify(line)
        labelled = bool(_WHEN_LABEL.search(line))
        if not line_type and not labelled:
            continue
        dates, relative = dates_in(line, posted)
        for d in dates:
            cands.append({"date": d, "line": line, "type": line_type or doc_type or body_type,
                          "via": "keyword" if line_type else "label", "relative": relative})

    if not cands and (doc_type or body_type):
        dates, relative = dates_in(title, posted)
        for d in dates[:1]:
            cands.append({"date": d, "line": title, "type": doc_type or body_type,
                          "via": "title", "relative": relative})
    if not cands and (doc_type or body_type):
        seen: list[tuple[date, str]] = []
        for line in lines:
            if (_NEGATE.search(line) or _SCOPE_LABEL.search(line) or _DEADLINE_LINE.search(line)
                    or _PAST_LINE.search(line)):
                continue
            dates, relative = dates_in(line, posted)
            seen += [(d, line) for d in dates if not relative]
        uniq = {d for d, _ in seen}
        if len(uniq) == 1:
            d, line = seen[0]
            cands.append({"date": d, "line": line, "type": doc_type or body_type, "via": "sole", "relative": False})

    cands = [c for c in cands if c["type"] and
             C.EXAM_MIN_DAYS_AHEAD <= (c["date"] - posted).days <= C.EXAM_MAX_DAYS_AHEAD]
    if not cands:
        hints = []
        if _ANY_TYPE.search(title + "\n" + body) and not _NEGATE.search(title):
            hints.append("시험·발표를 말하는 공지인데 날짜를 찾지 못했습니다")
        return [], hints

    # 중간·기말은 과목마다 하나다 → 후보가 여럿이면 가장 그럴듯한 하나만 남기고 신뢰도를 깎는다
    out: list[dict] = []
    hints: list[str] = []
    by_type: dict[str, list[dict]] = {}
    for c in cands:
        by_type.setdefault(c["type"], []).append(c)
    for kind, group in by_type.items():
        many = len({c["date"] for c in group}) > 1
        picks = [_best(group)] if kind in C.SINGLETON_TYPES and many else _dedup(group)
        if kind in C.SINGLETON_TYPES and many:
            hints.append(f"{C.type_label(kind)} 날짜 후보가 여럿입니다 — "
                         + ", ".join(sorted({c['date'].isoformat() for c in group})))
        for c in picks:
            out.append(_build(c, kind, many, doc_type, scope_weeks, scope_note, lines))
    out.sort(key=lambda x: (x["date"], x["type"]))
    return out, hints


_VIA_ORDER = {"keyword": 0, "label": 1, "title": 2, "sole": 3}


def _best(group: list[dict]) -> dict:
    """후보가 여럿일 때 하나 — 찾은 방법이 확실한 것, 같으면 이른 날짜."""
    return sorted(group, key=lambda c: (_VIA_ORDER[c["via"]], c["date"]))[0]


def _dedup(group: list[dict]) -> list[dict]:
    seen: dict[date, dict] = {}
    for c in group:
        cur = seen.get(c["date"])
        if cur is None or _VIA_ORDER[c["via"]] < _VIA_ORDER[cur["via"]]:
            seen[c["date"]] = c
    return [seen[d] for d in sorted(seen)]


def _build(c: dict, kind: str, many: bool, doc_type: Optional[str], scope_weeks: list[int],
           scope_note: str, lines: list[str]) -> dict:
    start, end = times_in(c["line"])
    place = place_in(c["line"])
    if not place:                                              # 시각·장소는 다른 줄에 따로 있는 경우가 많다
        for line in lines:
            if _PLACE_LABEL.search(line) and (p := place_in(line)):
                place = p
                break
    if not start:
        for line in lines:
            if _WHEN_LABEL.search(line) or classify(line) == kind:
                start, end = times_in(line)
                if start:
                    break

    conf = 1.0
    if doc_type != kind:
        conf -= 0.15                                           # 제목이 아니라 본문에서 유형을 알았다
    conf -= {"keyword": 0.0, "label": 0.05, "title": 0.10, "sole": 0.20}[c["via"]]
    if c["relative"]:
        conf -= 0.20
    if many and kind in C.SINGLETON_TYPES:
        conf -= 0.25
    if not start:
        conf -= 0.10
    if not place:
        conf -= 0.05
    if not scope_weeks and not scope_note:
        conf -= 0.05
    conf = round(max(0.2, min(1.0, conf)), 2)

    return {
        "type": kind,
        "title": _present_title(c["line"]) if kind == "presentation" else C.type_label(kind),
        "date": c["date"].isoformat(),
        "time": start, "endTime": end, "place": place,
        "scopeWeeks": scope_weeks, "scopeNote": scope_note,
        "confidence": conf,
        "status": "confirmed" if conf >= C.REVIEW_BELOW else "review",
        "quote": c["line"][:200],
        "via": c["via"],
    }


# ---------------------------------------------------------------- 전체

def load(manifest: Optional[Path] = None, root: Optional[Path] = None,
         today: Optional[date] = None) -> dict:
    """{available, stamp, posts, byCourse: {과목 id: {'exams': [...], 'hints': [...]}}}"""
    manifest = Path(manifest or C.ECLASS_MANIFEST)
    root = Path(root or C.ECLASS_ROOT)
    today = today or date.today()
    try:
        st = manifest.stat()
    except OSError:
        return {"available": False, "stamp": None, "posts": 0, "byCourse": {}}
    key = (str(manifest), st.st_mtime_ns, st.st_size, today.isoformat())
    if _cache["key"] == key:
        return _cache["value"]
    try:
        posts = (json.loads(manifest.read_text(encoding="utf-8")) or {}).get("posts") or {}
    except (OSError, ValueError):
        return {"available": False, "stamp": None, "posts": 0, "byCourse": {}}

    by: dict[str, dict] = {}
    read = 0
    for pkey, p in posts.items():
        cid = str(p.get("course_id") or "")
        # 작성일 — manifest 의 date 는 ':\r\n\t\t\t\t2026-09-6 21:30' 처럼 오고 **0 이 없는 날짜**도 있다
        m = _POSTED.search(str(p.get("date") or "")) or _POSTED.search(Path(str(p.get("path") or "")).name)
        if not cid or not m:
            continue
        try:
            posted = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            continue
        if (today - posted).days > C.NOTICE_LOOKBACK_DAYS:
            continue
        title = str(p.get("title") or "")
        body = ""
        path = root / str(p.get("path") or "").replace("\\", "/")
        try:
            title, body = _body(path.read_text(encoding="utf-8"))
        except OSError:
            pass                                               # 본문 파일이 없으면 제목만으로 본다
        if not _ANY_TYPE.search(title + "\n" + body):
            continue
        read += 1
        found, hints = exams_in(title, body, posted)
        slot = by.setdefault(cid, {"exams": [], "hints": []})
        src = {"noticeKey": pkey, "noticeUrl": str(p.get("url") or ""), "postedAt": posted.isoformat(),
               "board": str(p.get("activity") or ""), "noticeTitle": title,
               "course": str(p.get("course") or "")}
        for e in found:
            slot["exams"].append({**e, **src, "courseId": cid,
                                  "evidence": [{"quote": e.pop("quote"), "url": src["noticeUrl"]}]})
        for why in hints:
            slot["hints"].append({**src, "why": why})
    # 마이크로초까지 — 같은 밀리초 안에 두 번 쓰이면 도장이 같아 화면이 다시 부르지 않았다
    value = {"available": True, "posts": read,
             "stamp": datetime.fromtimestamp(st.st_mtime_ns / 1e9).isoformat(timespec="microseconds"),
             "byCourse": by}
    _cache.update(key=key, value=value)
    return value


__all__ = ["load", "exams_in", "classify", "dates_in", "times_in", "place_in", "scope_in"]
