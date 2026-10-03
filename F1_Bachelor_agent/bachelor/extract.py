"""추출 — 원천의 글·표 행을 일정 후보(Candidate)로 바꾼다. 규칙 기반이 기본이고 LLM 은 선택이다 (F1-R10~R15).

학사일정 표 (from_table)
    행 하나 = 일정 하나. 신뢰도 0.95. 두 가지를 더 만든다.
      - '9. 24.(목) 추석연휴 보강' → 9/24 를 휴업일(holiday)로 (F3 이 수업 회차를 뺄 때 쓴다, F1-R01a)
      - '제2학기 수강신청(학년별): 8.7.(4학년), 8.10.(3학년) …' → 학년별 하루짜리 일정으로 쪼갠다 (F1-R11)
공지 (from_post)
    본문을 줄 단위로 보고 날짜·기간이 있는 줄에서 '이름: 날짜' 를 읽는다. 표 행('라벨 | 기간 | 대상')도 같은 방식.
    한 글에서 여러 일정이 나온다 (F1-R11). 근거는 그 줄 원문이다 (F1-R12).
    신뢰도(F1-R13): 연도가 적혀 있나 · 이름이 구체적인가 · 학사 부서 글인가 · 기간/시각이 있나 → 0.8 이상이면 자동 등록.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Optional

from . import config as C
from .classify import action_for, classify_audience, classify_type, semester_of
from .models import Audience, Candidate
from .textutil import Span, clean_post_title, find_spans, normalize_title, parse_iso_date, tidy

# ── 학사일정 표 ─────────────────────────────────────────────

_MAKEUP = re.compile(r"^\s*(\d{1,2})\s*\.\s*(\d{1,2})\s*\.?\s*\(\s*[월화수목금토일]\s*\)\s*(.+?)\s*보강\s*$")
_GRADE_LABEL = re.compile(r"\(\s*([^()]*학년[^()]*)\)")


def _grade_children(head: str, text: str, ctx: date, base: Candidate) -> list[Candidate]:
    """'8.7.(4학년), 8.10.(3학년), 8.13~14(전학년 공통)' → 학년별 일정. 날짜마다 괄호 속 학년을 이름에 붙인다."""
    out = []
    for sp in find_spans(text, ctx):
        g = _GRADE_LABEL.search(text[sp.pos:sp.pos_end + 14])
        if not g:
            continue
        label = tidy(g.group(1))
        title = f"{head} ({label})"
        aud = classify_audience(title)
        out.append(Candidate(
            title=title, start=sp.start, end=sp.end, start_time=sp.start_time, end_time=sp.end_time,
            type=base.type, audience=aud, evidence=base.evidence, confidence=round(base.confidence - 0.02, 2),
            semester=base.semester, url=base.url, action_url=base.action_url, action_label=base.action_label,
            flags=["split"],
        ))
    return out


def from_table(rows: list[dict], cfg: dict, today: Optional[date] = None) -> list[Candidate]:
    today = today or date.today()
    since = today - timedelta(days=int(C.TABLE_KEEP_MONTHS * 30.5))
    out: list[Candidate] = []
    seen: set[tuple] = set()
    for r in rows:
        s, e = parse_iso_date(r["start"]), parse_iso_date(r["end"])
        if not s:
            continue
        e = e if e and e >= s else s
        if e < since:
            continue
        title = tidy(r["title"])
        key = (title, s, e)
        if key in seen:                  # 같은 행이 두 번 실린 경우('2026학년도 입학식' ×2)
            continue
        seen.add(key)
        type_ = classify_type(title)
        aud = classify_audience(title)
        act_url, act_label = action_for(type_, aud)
        quote = f"{r['start']}{' ~ ' + r['end'] if r['end'] != r['start'] else ''}  {r['title']}"
        base = Candidate(
            title=title, start=s, end=e if e > s else None, type=type_, audience=aud,
            evidence=[{"field": "start", "quote": quote}], confidence=0.95, semester=semester_of(title, s),
            url=cfg.get("url", ""), action_url=act_url, action_label=act_label,
        )
        out.append(base)

        mk = _MAKEUP.match(title)
        if mk:                           # 보강일 행 → 원래 쉬었던 날을 휴업일로
            y = s.year
            try:
                hd = date(y, int(mk.group(1)), int(mk.group(2)))
                if hd > s:
                    hd = date(y - 1, hd.month, hd.day)
            except ValueError:
                hd = None
            if hd:
                name = tidy(mk.group(3))
                out.append(Candidate(
                    title=f"{name} (휴업)", start=hd, type="holiday", audience=Audience(),
                    evidence=[{"field": "start", "quote": quote}], confidence=0.9,
                    semester=semester_of(title, hd), url=base.url, flags=["derived"],
                ))

        if "학년별" in title and ":" in title:
            head, tail = title.split(":", 1)
            head = tidy(re.sub(r"\(\s*학년별\s*\)", "", head))
            base.title = f"{head} (학년별)"          # 긴 원문 제목은 근거(evidence)에 남아 있다
            out.extend(_grade_children(head, tail, s, base))
    return _join_holidays(out)


def _join_holidays(cands: list[Candidate]) -> list[Candidate]:
    """보강 행에서 만든 휴업일이 이어지는 날짜면 하나의 기간으로 ('추석연휴' 9/24 + 9/25 → 9/24~9/25)."""
    derived = sorted((c for c in cands if "derived" in c.flags), key=lambda c: (c.title, c.start))
    keep = [c for c in cands if "derived" not in c.flags]
    for c in derived:
        prev = keep[-1] if keep and "derived" in keep[-1].flags else None
        if prev and prev.title == c.title and (prev.end or prev.start) + timedelta(days=1) == c.start:
            prev.end = c.start
            prev.evidence = prev.evidence + c.evidence
            continue
        keep.append(c)
    return keep


# ── 공지 ────────────────────────────────────────────────────

_BULLETS = r"◾◇◆■□▶▷➣►•※○●◦▪✔✓☞❍❏❑◎◈⦁"
_MID_BULLET = re.compile(rf"\s+(?=[{_BULLETS}])")
_LEAD = re.compile(rf"^(?:\d{{1,2}}\s*[.)]|[가-하]\s*[.)]|\(\s*[0-9가-하]{{1,2}}\s*\)|[{_BULLETS}\-–*·]+|\[[^\]]*\])\s*")
_TRAIL_WORDS = re.compile(r"\s*(?:기간|일시|일정|기한|날짜|시간)\s*$")
_GENERIC = {"", "기간", "일시", "일정", "기한", "신청기간", "접수기간", "신청", "접수", "날짜", "시간", "때", "시행", "운영"}
_PARTICLE_END = re.compile(r"[은는이가을를에의와과로]$")
_ACTION_WORDS = re.compile(r"기간|신청|접수|납부|등록|마감|정정|취소|철회|제출|발급|까지|일시|일정|시험|개강|종강|휴업|보강|"
                           r"면접|배정|휴학|복학|수요조사|고지서|평가|기한|선발|공고")
# '2026. 8. 31. 까지인 자' — 날짜가 기간이 아니라 자격 조건인 경우
_CONDITION_AFTER = re.compile(r"^\s*(?:까지|이전|이후|부터)?\s*(?:인|의|에|이)?\s*(?:자|학생|분)(?:\b|[\s,.)])")
ACADEMIC_WRITERS = ("학사과", "재무과", "교육혁신정책실", "학생과")


def clean_label(s: str) -> str:
    s = tidy(s)
    for _ in range(4):
        s2 = _LEAD.sub("", s)
        if s2 == s:
            break
        s = s2
    s = re.sub(r"[\s:：\-–=(\[]+$", "", s)                 # 끝에 남은 '(' ':' 같은 찌꺼기
    s = re.sub(r"\s*및\s*(?:장소|방법|대상|절차)$", "", s)   # '일시 및 장소' → '일시'
    s = _TRAIL_WORDS.sub("", s)
    return s.strip(" :·,")


_CLAUSE = re.compile(r"경우|하여|하고|않은|않았을|않았|위하여|에서는|으로써")


def _is_fragment(label: str) -> bool:
    """이름이 아니라 문장 조각인가 — '우리 대학교에서는', '등록금 고지서 확인은', '…않았을 경우 …'."""
    return bool(_PARTICLE_END.search(label) or _CLAUSE.search(label))


def _fragment_tail(label: str) -> str:
    """'수강신청하지 않았을 경우 수강 신청 정정기간 (' → '수강 신청 정정'. 마지막 절 뒤가 이름이면 그것을 쓴다."""
    ms = list(_CLAUSE.finditer(label))
    tail = clean_label(label[ms[-1].end():]) if ms else ""
    if tail and not _PARTICLE_END.search(tail) and squash_label(tail) not in _GENERIC and len(tail) <= 30:
        return tail
    return ""


def _segments(body: str) -> list[str]:
    """본문 → 줄 → 줄 가운데 글머리 기호(◾ ■ ▶ …)에서 한 번 더 자른 조각."""
    out = []
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        for seg in _MID_BULLET.split(line):
            seg = seg.strip()
            if seg:
                out.append(seg)
    return out


def _span_in_row(cells: list[str], ctx: date) -> tuple[Optional[int], list[Span]]:
    for j, cell in enumerate(cells):
        sp = find_spans(cell, ctx)
        if sp:
            return j, sp
    return None, []


def _confidence(span: Span, label_specific: bool, label: str, official: bool, origin: str) -> tuple[float, list[str]]:
    c, flags = 0.55, []
    if span.year_explicit:
        c += 0.15
    else:
        flags.append("year_guessed")
    if label_specific:
        c += 0.10
    if official:
        c += 0.05
    if span.is_period or span.start_time or span.deadline:
        c += 0.05
    if label and _is_fragment(label):
        c -= 0.15                    # '등록금 고지서 확인은 …' 처럼 문장 조각 → 이름은 공지 제목으로, 확인 필요로
        flags.append("fragment")
    if origin == "attachment":
        c -= 0.05
        flags.append("attachment")
    if origin == "title":
        c -= 0.05
    return round(max(0.05, min(0.95, c)), 2), flags


def from_post(post, cfg: dict, extra: Optional[list[tuple[str, str]]] = None, today: Optional[date] = None) -> list[Candidate]:
    """공지 글 하나 → 일정 후보들. extra = [(origin, text)] — PDF 첨부에서 뽑은 텍스트 등."""
    today = today or date.today()
    ctx = parse_iso_date(post.posted_at) or today
    head = clean_post_title(post.title)
    official = (post.writer or "").strip() in ACADEMIC_WRITERS or cfg.get("kind") == "k2web"
    src_aud = Audience.from_dict(cfg.get("audience"))

    texts: list[tuple[str, str]] = [("body", seg) for seg in _segments(post.body)]
    for origin, t in extra or []:
        texts += [(origin, seg) for seg in _segments(t)]
    texts.append(("title", post.title))      # 제목의 '(~10.14.)' 는 본문에서 아무것도 못 찾았을 때만 쓴다

    found: dict[tuple, Candidate] = {}
    for origin, seg in texts:
        if origin == "title" and found:
            break
        aud_raw = ""
        if origin != "title" and " | " in seg:
            cells = [c.strip() for c in seg.split(" | ")]
            j, spans = _span_in_row(cells, ctx)
            if j is None:
                continue
            label = clean_label(cells[0]) if j > 0 else ""
            if j + 1 < len(cells) and not find_spans(cells[j + 1], ctx):
                aud_raw = tidy(cells[j + 1]).strip("·. ")[:60]
            spans = spans[:1]
        else:
            spans = find_spans(seg, ctx)
            if not spans:
                continue
            raw_label = seg[:spans[0].pos] if origin != "title" else ""
            if origin != "title" and not re.search(r"[가-힣A-Za-z]", raw_label):
                continue                  # 날짜로 시작하는 줄 — 서명('2026. 9. 14.')이나 조건 문장
            label = clean_label(raw_label)
            if _CONDITION_AFTER.match(seg[spans[0].pos_end:spans[0].pos_end + 12]):
                continue
            multi = [s for s in spans if _GRADE_LABEL.search(seg[s.pos:s.pos_end + 14])]
            spans = spans[:1] if len(multi) < 2 else multi
        label_specific = squash_label(label) not in _GENERIC and len(label) <= 30 and not _is_fragment(label)
        name = label if label_specific else ((_fragment_tail(label) if label else "") or head)
        if not _ACTION_WORDS.search(f"{label} {name} {head}"):
            continue
        for sp in spans:
            title = name
            g = _GRADE_LABEL.search(seg[sp.pos:sp.pos_end + 14]) if len(spans) > 1 else None
            if g:
                title = f"{name} ({tidy(g.group(1))})"
            conf, flags = _confidence(sp, label_specific, label, official, origin)
            if sp.end and sp.end < sp.start:
                conf, flags = 0.3, flags + ["reversed"]
            if abs((sp.start - ctx).days) > 400:
                conf = round(max(0.05, conf - 0.3), 2)
            type_ = classify_type(f"{title} {head}") if not label_specific else classify_type(title)
            if type_ == "etc":
                type_ = classify_type(head)
            aud = classify_audience(title, context=post.title).merged(src_aud)
            if not aud.raw and aud_raw:
                aud.raw = aud_raw
            act_url, act_label = action_for(type_, aud)
            cand = Candidate(
                title=title, start=sp.start, start_time=sp.start_time, end=sp.end, end_time=sp.end_time,
                type=type_, audience=aud, evidence=[{"field": "start", "quote": seg[:200]}], confidence=conf,
                semester=semester_of(f"{title} {head}", sp.start), url=post.url, post_id=post.post_id,
                posted_at=post.posted_at, action_url=act_url, action_label=act_label, flags=flags,
            )
            key = (normalize_title(title), sp.start, sp.end)
            if key not in found or found[key].confidence < conf:
                found[key] = cand

    out = list(found.values())
    # 문장 조각에서 나온 날짜가 같은 글의 다른 일정과 같은 날이면 그 일정의 부연 설명이다 → 버린다
    solid_starts = {c.start for c in out if "fragment" not in c.flags}
    out = [c for c in out if "fragment" not in c.flags or c.start not in solid_starts]
    if not out and post.image_only:
        out.append(Candidate(
            title=head, start=None, type=classify_type(head),
            audience=classify_audience(head).merged(src_aud), confidence=0.2,
            semester=semester_of(head, ctx), url=post.url, post_id=post.post_id, posted_at=post.posted_at, flags=["needs_ocr"],
        ))
    return out


def squash_label(s: str) -> str:
    return re.sub(r"\s+", "", s)
