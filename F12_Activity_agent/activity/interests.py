"""관심사 — 태그·자유 키워드·제외 키워드 → '내 관심사 / 관련 있음 / 관심 밖' (요구사항정의서 F12 5절). 표준 라이브러리만.

관심사는 C2 프로필의 interests 칸에 있다(F12-R13) — {tags, keywords, exclude}. 예전 모양(글자 목록)도 받는다(아는 태그면 태그, 아니면 키워드).

등급 규칙 (위에서부터 처음 걸리는 것)
  ① 제외 키워드가 제목·본문에 있다                 → 관심 밖 (사용자 의사가 우선, F12-R22)
  ② 자유 키워드가 제목·본문에 있다                 → 내 관심사 (어떤 키워드인지 남긴다, F12-R20)
  ③ 고른 태그의 어휘가 제목(말머리 포함)에 있다      → 내 관심사
     고른 태그의 어휘가 본문에만 있다               → 관련 있음
     (단, 신청하는 글이 아닌 안내·소식 — 분류가 기타이고 모집·신청 말이 없는 글 — 은 태그만 걸리면 관련 있음까지.
      'AICOSS 레터' 같은 소식지가 '내 관심사' 알림으로 가지 않게, 2026-10-10 실측)
  ④ 아무것도 안 걸림 — LLM 판단이 있으면 그것(높음 → 내 관심사 · 중간 → 관련 있음 · 낮음 → 관심 밖, F12-R21)
  ⑤ LLM 이 없으면 — 내 학과와 관련된 원천(관련 사업단·내 단과대학·학과 게시판)의 모집 글이면 관련 있음, 아니면 관심 밖
     (2026-10-10 구현 결정: F12 가 장학 외 전부를 다루게 되어 '키워드 없음 = 관련 있음'(F12-R24)이면 목록 전체가 '관련 있음'이 된다.
      관심 밖도 목록에서 접혀 있을 뿐 '더보기'로 볼 수 있다)
관심사가 비어 있으면 등급을 매기지 않는다 — 목록은 전부 보이고 알림은 안 간다 (F12-R14).

매칭: 공백·대소문자 무시, 부분 일치. 영문 3자 이하(AI·SW·IR)는 앞 글자가 영문이 아닐 때만, 뒤에 영문이 붙으면 대문자 그대로일 때만 — 'AICOSS' 는 걸리고 'RAIN'·'Iron' 은 안 걸린다.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from typing import Any, Optional

from . import config as C
from scholarship.jsonfile import JsonFile
from scholarship.textutil import nfkc, semester_of

_cache: dict = {"data": None, "cats": None}


def _compile(data: dict) -> dict:
    """사전을 다시 읽을 때 한 번만 — 분류 정규식."""
    ac = next((c for c in data["categories"] if c["key"] == "academic"), None)
    return {"cats": [(c["key"], c["label"], re.compile(c["pattern"], re.I)) for c in data["categories"] if not c.get("drop")],
            "academic": (ac, re.compile(ac["pattern"]), re.compile(ac["keep"], re.I)) if ac else None}


_file = JsonFile(lambda: C.INTERESTS_FILE, _compile)     # 바뀌었는지는 2초에 한 번만 본다 (공지마다 stat 하면 느리다)


def catalog() -> dict:
    data = _file.get()
    if _cache["data"] is not data:
        _cache.update(data=data, **_file.extra())
    return data


def tag_keys() -> list[str]:
    return [t["key"] for t in catalog()["tags"]]


def tag_words(key: str) -> list[str]:
    return next((t["words"] for t in catalog()["tags"] if t["key"] == key), [])


def category_labels() -> dict[str, str]:
    """화면의 분류 이름 — 빼는 분류(학사 일정 안내)는 목록에 나오지 않으므로 넣지 않는다."""
    cat = catalog()
    return {**{c["key"]: c["label"] for c in cat["categories"] if not c.get("drop")}, "other": cat.get("otherLabel", "기타 안내")}


def dropped_categories() -> set[str]:
    """대외활동에서 빼는 분류 — 학사 일정 안내 (2026-11-19 사용자 결정)."""
    return {c["key"] for c in catalog()["categories"] if c.get("drop")}


def is_academic(title: str) -> bool:
    """학사 일정 안내인가 — 학사 일정(F1)에서 이미 모았을 법한 제목(수강신청·등록·고지서·휴학·졸업·성적·계절학기 운영·폐강·교과구분·전과 …).
    2026-11-19 사용자 결정: 그것만 뺀다. 작성 부서(학사과·재무과·교무과)로는 빼지 않고, 제목에 기자재·공간 대여 · 연구 · 행사 ·
    프로그램 · 취업 말이 있거나 학점교류·교류수학·교류학생(2026-10-25)이면 남긴다. 말머리 '학사'만으로는 빼지 않는다.
    본문은 보지 않는다 — 본문의 '학점 인정' 한 마디로 캡스톤·설문 공지가 빠지지 않게."""
    catalog()
    if not _cache.get("academic"):
        return False
    _, pat, keep = _cache["academic"]
    t = nfkc(title)
    return not keep.search(t) and bool(pat.search(t))


def academic_label() -> str:
    catalog()
    return (_cache.get("academic") or ({"label": "학사 일정 안내"},))[0]["label"]


def categorize(text: str) -> tuple[str, str]:
    """제목(말머리 포함) → (분류 키, 이름). 순서가 우선순위다 — '창업 아이템 경진대회'는 공모전. 학사 일정 안내는 is_academic 이 따로 가른다."""
    catalog()
    t = nfkc(text)
    for key, label, pat in _cache["cats"]:
        if pat.search(t):
            return key, label
    return "other", catalog().get("otherLabel", "기타 안내")


_SEMESTER = re.compile(r"(20\d{2})\s*(?:학년도|년)?\s*[-.]?\s*(?:제\s*)?([12])\s*학기")


def semester_long(title: str, today: date, category: Optional[str] = None) -> bool:
    """학기 내내 유효한 대여 안내인가 — 기자재·공간 대여이고 제목이 이번(또는 다음) 학기를 가리킨다
    ('실험실습 기자재 대여 안내(2026년 2학기)'). 학기 초에 한 번 올라와 학기 내내 받으므로 45일이 지나도 끝난 글이 아니다 —
    수집의 '오래된 글'·목록의 '지난 공지'에서 빼 준다 (2026-11-19 — 8월 중순에 올라온 사업단 대여 안내 3건이 한 번도 모이지 않았다)."""
    if (category or categorize(title)[0]) != "rental":
        return False
    m = _SEMESTER.search(nfkc(title))
    if not m:
        return False
    cur = semester_of(today)                       # 3~8월 1학기 · 9~2월 2학기 — 8월에 올라오는 2학기 안내는 '다음 학기'
    y, n = int(cur[:4]), int(cur[-1])
    return f"{m.group(1)}-{m.group(2)}" in (cur, f"{y}-2" if n == 1 else f"{y + 1}-1")


# ── 관심사 모양 ─────────────────────────────────────────────

def _clean_list(v: Any, limit: int) -> list[str]:
    out: list[str] = []
    for x in v if isinstance(v, list) else []:
        s = re.sub(r"\s+", " ", str(x or "")).strip()[:30]
        if len(s) >= 2 and s not in out:
            out.append(s)
    return out[:limit]


def normalize(raw: Any) -> dict:
    """프로필의 interests → {tags, keywords, exclude}. 모르는 태그는 버린다(사전이 바뀌었을 때)."""
    known = tag_keys()
    if isinstance(raw, list):                       # 예전 모양 — 글자 목록
        items = _clean_list(raw, 40)
        return {"tags": [x for x in items if x in known], "keywords": [x for x in items if x not in known][:C.MAX_KEYWORDS],
                "exclude": []}
    if not isinstance(raw, dict):
        return {"tags": [], "keywords": [], "exclude": []}
    return {"tags": [t for t in _clean_list(raw.get("tags"), 20) if t in known],
            "keywords": _clean_list(raw.get("keywords"), C.MAX_KEYWORDS),
            "exclude": _clean_list(raw.get("exclude"), C.MAX_KEYWORDS)}


def from_profile(profile: Optional[dict]) -> dict:
    return normalize((profile or {}).get("interests"))


def is_set(i: dict) -> bool:
    return bool(i.get("tags") or i.get("keywords"))


def ihash(i: dict) -> str:
    """LLM 판단 캐시 키 — 관심사가 바뀌면 다시 판단한다."""
    blob = json.dumps({k: sorted(i.get(k) or []) for k in ("tags", "keywords", "exclude")}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]


# ── 매칭 ────────────────────────────────────────────────────

_SHORT = re.compile(r"[A-Za-z0-9]{1,3}")
_short_cache: dict[str, re.Pattern] = {}


def _squash(s: str) -> str:
    return re.sub(r"\s+", "", nfkc(s)).lower()


class Text:
    """한 공지의 매칭용 글자 — 제목(말머리 포함)과 본문을 따로, 공백을 뺀 소문자도 미리 만들어 둔다."""

    def __init__(self, title: str, body: str = ""):
        self.title = nfkc(title)
        self.body = nfkc(body)
        self.title_sq = _squash(title)
        self.body_sq = _squash(body)

    def where(self, term: str) -> Optional[str]:
        """'title' · 'body' · None"""
        if _SHORT.fullmatch(term):
            pat = _short_cache.get(term)
            if pat is None:
                # 낱말 하나로 서 있으면 대소문자 무시('the ai class'), 뒤에 영문이 붙으면 대문자 그대로일 때만('AICOSS' — 'Iron' 의 Ir 은 아니다)
                esc = re.escape(term)
                pat = _short_cache[term] = re.compile(rf"(?<![A-Za-z])(?:(?i:{esc})(?![A-Za-z])|{re.escape(term.upper())}(?=[A-Za-z]))")
            if pat.search(self.title):
                return "title"
            return "body" if pat.search(self.body) else None
        t = _squash(term)
        if not t:
            return None
        if t in self.title_sq:
            return "title"
        return "body" if t in self.body_sq else None


def grade(text: Text, i: dict, *, llm: Optional[dict] = None, affiliated: bool = False,
          participation: bool = True, informational: bool = False) -> dict:
    """→ {grade: match|related|other|None, hits: [{type, label, word?, where?}], by}. 관심사가 비면 grade None."""
    if not is_set(i):
        return {"grade": None, "hits": [], "by": None}
    for kw in i.get("exclude") or []:
        w = text.where(kw)
        if w:
            return {"grade": "other", "hits": [{"type": "exclude", "label": kw, "where": w}], "by": "exclude"}
    hits: list[dict] = []
    for kw in i.get("keywords") or []:
        w = text.where(kw)
        if w:
            hits.append({"type": "keyword", "label": kw, "where": w})
    weak: list[dict] = []
    for tag in i.get("tags") or []:
        best = None
        for word in tag_words(tag):
            w = text.where(word)
            if w == "title":
                best = {"type": "tag", "label": tag, "word": word, "where": "title"}
                break
            if w == "body" and best is None:
                best = {"type": "tag", "label": tag, "word": word, "where": "body"}
        if best and best["where"] == "title":
            hits.append(best)
        elif best:
            weak.append(best)
    if hits:
        strong = any(h["type"] == "keyword" for h in hits) or not informational
        return {"grade": "match" if strong else "related", "hits": hits + weak, "by": "keyword"}
    if weak:
        return {"grade": "related", "hits": weak, "by": "keyword"}
    if llm and llm.get("grade") in ("match", "related", "other"):
        return {"grade": llm["grade"], "hits": [{"type": "llm", "label": "LLM 판단", "reason": llm.get("reason")}], "by": "llm"}
    if affiliated and participation:
        return {"grade": "related", "hits": [{"type": "affiliation", "label": "내 학과 관련 원천"}], "by": "affiliation"}
    return {"grade": "other", "hits": [], "by": "none"}


def chips(hits: list[dict]) -> list[str]:
    """화면의 이유 칩 — 태그는 그대로, 키워드는 따옴표. 본문에서만 걸린 태그는 뒤에 (본문)."""
    out: list[str] = []
    for h in hits:
        if h["type"] == "tag":
            c = h["label"] + (" (본문)" if h.get("where") == "body" else "")
        elif h["type"] == "keyword":
            c = f"“{h['label']}”"
        elif h["type"] == "exclude":
            c = f"제외 “{h['label']}”"
        else:
            c = h["label"]
        if c not in out:
            out.append(c)
    return out
