"""규칙(정규식) 기반 자격 요건 사전 추출 — LLM 없이도 돌고, LLM 결과의 교차 검증에도 쓴다.

학교 공지에서 반복되는 표현을 잡는다. 모든 값에 근거 문장(Evidence)이 붙는다.
  "3학년 이상"  "1,3학년 재학생"  "2학기 이상 재학"  "평점 3.5/4.5 이상"  "직전학기 성적이 70점/100점 이상"
  "직전학기 12학점 이상 이수"  "학자금 지원 8구간 이하"  "대한민국 국적"  "신청기간: 2026. 8. 12.(수) ~ 9. 9.(수) 18:00"
  "제출서류 …"  "신청방법 …"  "문의 …"  "제외 …"

전공·학과 조건은 오탐이 나면 '비해당'으로 잘못 걸러 놓치게 되므로(false negative 가 더 나쁨),
규칙 단계에서는 구조화 필드(major_include)에 넣지 않고 other_conditions 로만 남긴다. 구조화는 LLM+근거검증이 맡는다.
"""
from __future__ import annotations

import re
from typing import Optional

from .schemas import GPA, Evidence, Period, Requirements
from .textutil import find_sentence, parse_period

NUM = r"(\d{1,2})"
LINE_HEADERS = re.compile(r"^\s*(?:\d+\.|[가-힣]\.|[○●□■▶▷◦•\-*※]|\(\d+\)|[①-⑳])\s*")


def _lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def _ev(field: str, quote: Optional[str]) -> list[Evidence]:
    return [Evidence(field=field, quote=quote[:300])] if quote else []


# ── 개별 규칙 ──────────────────────────────────────────────

def grades(text: str) -> tuple[Optional[list[int]], Optional[str]]:
    # "3학년 이상" / "2학년 이상 4학년 이하" / "1,3학년" / "1~3학년" / "3, 4학년 재학생"
    m = re.search(rf"{NUM}\s*학년\s*이상(?:\s*{NUM}\s*학년\s*이하)?", text)
    if m:
        lo = int(m.group(1)); hi = int(m.group(2)) if m.group(2) else 4
        if 1 <= lo <= hi <= 6:
            return list(range(lo, hi + 1)), find_sentence(text, re.escape(m.group(0)))
    m = re.search(rf"{NUM}\s*학년\s*이하", text)
    if m:
        hi = int(m.group(1))
        return list(range(1, hi + 1)), find_sentence(text, re.escape(m.group(0)))
    m = re.search(r"((?:\d\s*[,，·]\s*)+\d)\s*학년", text)
    if m:
        nums = sorted({int(x) for x in re.findall(r"\d", m.group(1))})
        if nums and max(nums) <= 6:
            return nums, find_sentence(text, re.escape(m.group(0)))
    m = re.search(rf"{NUM}\s*[~∼～\-]\s*{NUM}\s*학년", text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 1 <= lo <= hi <= 6:
            return list(range(lo, hi + 1)), find_sentence(text, re.escape(m.group(0)))
    m = re.search(rf"(?<![\d~∼～\-,，·])\s{NUM}\s*학년\s*(?:[12]\s*학기\s*)?(?:재학생|학생|만|에\s*한함|대상|재학\s*중)", text)
    if m:
        g = int(m.group(1))
        if 1 <= g <= 6:
            return [g], find_sentence(text, re.escape(m.group(0).strip()))
    if re.search(r"신입생\s*(?:만|에\s*한함|대상)", text):
        return [1], find_sentence(text, r"신입생\s*(?:만|에\s*한함|대상)")
    return None, None


def semesters(text: str) -> tuple[Optional[int], Optional[str]]:
    m = re.search(rf"{NUM}\s*학기\s*이상\s*(?:재학|이수|등록|수료)", text)
    if m:
        return int(m.group(1)), find_sentence(text, re.escape(m.group(0)))
    m = re.search(rf"{NUM}\s*학기\s*(?:진학|등록)\s*예정", text)     # "5학기 진학예정자" → 4학기 이수
    if m:
        return max(int(m.group(1)) - 1, 0), find_sentence(text, re.escape(m.group(0)))
    return None, None


def gpa(text: str) -> tuple[Optional[GPA], Optional[str]]:
    basis = None
    if re.search(r"직전\s*학기", text):
        basis = "직전학기"
    elif re.search(r"전\s*학년|전체\s*학기|누적", text):
        basis = "전체"
    # 3.5/4.5 이상 · 평점 3.0 이상 · 평점평균 3.5점 이상
    m = re.search(r"(\d\.\d{1,2})\s*(?:점)?\s*/\s*(4\.5|4\.3|4\.0)\s*(?:만점)?\s*(?:점)?\s*이상", text)
    if m:
        return GPA(value=float(m.group(1)), scale=float(m.group(2)), basis=basis), find_sentence(text, re.escape(m.group(0)))
    m = re.search(r"(?:평점|평량|성적|GPA)[^\n\d]{0,12}(\d\.\d{1,2})\s*(?:점)?\s*이상", text)
    if m:
        return GPA(value=float(m.group(1)), scale=4.5, basis=basis), find_sentence(text, re.escape(m.group(0)))
    # 70점/100점 이상 · B학점(80/100점) 이상 · 백분위 85점 이상
    m = re.search(r"(\d{2,3})\s*(?:점)?\s*/\s*100\s*(?:점)?\s*(?:만점)?\s*이상", text)
    if m:
        return GPA(value=float(m.group(1)), scale=100, basis=basis), find_sentence(text, re.escape(m.group(0)))
    m = re.search(r"(?:백분위|환산점수|성적)\s*(?:이)?\s*(\d{2,3})\s*점\s*이상", text)
    if m:
        v = float(m.group(1))
        if 50 <= v <= 100:
            return GPA(value=v, scale=100, basis=basis), find_sentence(text, re.escape(m.group(0)))
    return None, None


def credits(text: str) -> tuple[Optional[int], Optional[int], list[Evidence]]:
    """(누적 최소학점, 직전학기 최소학점, 근거)"""
    total = last = None
    evs: list[Evidence] = []
    for m in re.finditer(r"(\d{1,3})\s*학점\s*이상\s*(?:을\s*)?(?:이수|취득)", text):
        line = find_sentence(text, re.escape(m.group(0))) or m.group(0)
        n = int(m.group(1))
        if re.search(r"직전\s*학기|전\s*학기|해당\s*학기", line):
            if last is None:
                last = n; evs += _ev("min_credits_last_semester", line)
        else:
            if total is None:
                total = n; evs += _ev("min_credits_total", line)
    return total, last, evs


def income(text: str) -> tuple[Optional[int], Optional[str]]:
    m = re.search(r"(?:학자금\s*지원\s*)?(\d{1,2})\s*구간\s*이하", text)
    if m:
        return int(m.group(1)), find_sentence(text, re.escape(m.group(0)))
    return None, None


def nationality(text: str) -> tuple[Optional[str], Optional[str]]:
    m = re.search(r"대한민국\s*국적", text)
    if m:
        return "대한민국", find_sentence(text, re.escape(m.group(0)))
    return None, None


def enrollment(text: str) -> tuple[Optional[list[str]], Optional[str]]:
    if re.search(r"휴학생\s*(?:도\s*)?(?:포함|가능|신청\s*가능)", text):
        return ["재학", "휴학"], find_sentence(text, r"휴학생\s*(?:도\s*)?(?:포함|가능|신청\s*가능)")
    if re.search(r"재학생|재학\s*중|재학중인", text):
        return ["재학"], find_sentence(text, r"재학생|재학\s*중|재학중인")
    return None, None


def period(text: str, title: str = "") -> tuple[Optional[Period], Optional[str]]:
    """신청/접수 기간 줄을 찾아 파싱. 없으면 제목의 '(~9/18까지)' 같은 표기라도 쓴다."""
    # 1순위: '신청/접수/모집 기간' 이 명시된 줄. 2순위: '기간:' '마감:' '까지' 가 있는 줄.
    # '유효기간·근로기간·파견기간·지급기간' 은 신청 기간이 아니다 (첨부 요강에 자주 섞여 있음).
    noise = re.compile(r"유효\s*기간|근로\s*기간|파견\s*기간|지급\s*기간|사업\s*기간|수혜\s*기간|장학\s*기간|활동\s*기간|학기\s*기간")
    strong, weak = [], []
    for ln in _lines(text):
        if not re.search(r"\d", ln) or noise.search(ln):
            continue
        if re.search(r"(?:신청|접수|모집|지원|제출)\s*(?:기간|기한|마감|일정)", ln):
            strong.append(ln)
        elif re.search(r"기간\s*[:：]|마감\s*[:：]|까지", ln):
            weak.append(ln)
    for ln in strong + weak:
        s, e = parse_period(ln)
        if s or e:
            return Period(start=s, end=e, raw=ln[:200]), ln
    if title:
        m = re.search(r"[~∼～]\s*[\d./월 ]+일?\s*(?:\([^)]*\))?\s*(?:까지)?", title)
        if m:
            s, e = parse_period(m.group(0))
            if e:
                return Period(start=None, end=e, raw=m.group(0)), title
    return None, None


def section_lines(text: str, header_pat: str, max_lines: int = 8) -> list[str]:
    """'제출서류' 같은 헤더 줄 다음의 항목들을 모은다 (다음 번호 헤더 전까지)."""
    out: list[str] = []
    lines = _lines(text)
    for i, ln in enumerate(lines):
        if re.search(header_pat, ln):
            same_line = re.split(header_pat, ln, maxsplit=1)[-1].strip(" :：-")
            if len(same_line) > 3:
                out.append(same_line)
            for nxt in lines[i + 1:i + 1 + max_lines]:
                if re.match(r"^\s*\d+\s*[.)]\s*\S", nxt) and not re.match(r"^\s*\d+\s*[.)]\s*[가-힣]{0,6}\s*(서|증|본|부)\b", nxt):
                    break
                if re.search(header_pat, nxt):
                    break
                out.append(LINE_HEADERS.sub("", nxt))
            break
    return [o for o in out if o]


def bracket_provider(title: str) -> Optional[str]:
    for m in re.finditer(r"\[([^\]]{2,40})\]", title):
        s = m.group(1).strip()
        if s in ("장학안내", "장학", "공지", "안내", "학사안내"):
            continue
        return s
    return None


def guess_kind(title: str, text: str, provider: Optional[str]) -> Optional[str]:
    blob = f"{title} {provider or ''}"
    if re.search(r"국가장학금|국가근로|한국장학재단|국가\s*우수|국가이공계|대통령과학", blob):
        return "국가"
    if re.search(r"재단|장학회|시\]|군\]|구\]|시장학|진흥원|기업|은행", blob):
        return "교외"
    if re.search(r"사업단|AICOSS|SW중심|소프트웨어중심", blob):
        return "사업단"
    if re.search(r"교내|학생과|학사정보시스템|동창장학|성적우수", blob + text[:200]):
        return "교내"
    return None


# ── 진입점 ────────────────────────────────────────────────

def extract_rules(title: str, text: str) -> Requirements:
    """제목+본문(+첨부 텍스트) → Requirements (extractor='rules')."""
    full = f"{title}\n{text}"
    req = Requirements(extractor="rules")
    evs: list[Evidence] = []

    req.provider = bracket_provider(title)
    req.kind = guess_kind(title, text, req.provider)     # type: ignore[assignment]
    req.scholarship_name = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", title).strip() or title

    g, q = grades(full);         req.grades_allowed = g;             evs += _ev("grades_allowed", q)
    s, q = semesters(full);      req.min_semesters_completed = s;    evs += _ev("min_semesters_completed", q)
    gp, q = gpa(full);           req.min_gpa = gp;                   evs += _ev("min_gpa", q)
    ct, cl, e2 = credits(full);  req.min_credits_total = ct; req.min_credits_last_semester = cl; evs += e2
    ib, q = income(full);        req.income_bracket_max = ib;        evs += _ev("income_bracket_max", q)
    na, q = nationality(full);   req.nationality = na;               evs += _ev("nationality", q)
    en, q = enrollment(full);    req.enrollment_status = en;         evs += _ev("enrollment_status", q)
    pd, q = period(text, title); req.application_period = pd;        evs += _ev("application_period", q)

    docs = section_lines(text, r"제출\s*서류|구비\s*서류|신청\s*서류|첨부\s*서류")
    # 표에서 떨어져 나온 '본인' '필수서류' 같은 셀 제목은 서류가 아니다 — 서류처럼 생긴 항목만 남긴다
    doc_like = re.compile(r"증명|사본|확인서|계획서|추천서|소개서|지원서|신청서|동의서|통지서|등본|초본|카드|양식|서류|서\s*\d*\s*부|부$|파일|성적표|증$")
    cell_header = re.compile(r"^(?:필수|기타|선택|공통|추가|본인|가족|해당자만|제출)\s*(?:서류)?\s*[:：]?$")
    docs = [re.sub(r"^[√·•○●\-*]\s*", "", d).strip() for d in docs]
    docs = [d for d in docs if len(d) >= 4 and doc_like.search(d) and not cell_header.match(d)]
    req.required_documents = docs[:10]
    if docs:
        evs += _ev("required_documents", docs[0])
    meth = section_lines(text, r"신청\s*방법|접수\s*방법|지원\s*방법|신청\s*절차|접수\s*처|지원\s*접수|온라인\s*지원|제출\s*방법|제출\s*처", max_lines=3)
    meth = [re.sub(r"^[√·•○●\-*]\s*", "", x) for x in meth if len(x) > 3 and x not in ("및 문의", "문의")]
    if meth:
        req.apply_method = " / ".join(meth)[:300]
        evs += _ev("apply_method", meth[0])
    url = re.search(r"https?://[^\s)\]>\"']+", text) or re.search(r"(?<![A-Za-z0-9.])www\.[A-Za-z0-9.\-]+\.[a-z]{2,}(?:/[^\s)\]>\"']*)?", text)
    if url:
        u = url.group(0).rstrip(".,")
        req.apply_url = u if u.startswith("http") else "https://" + u
    contact = next((ln for ln in _lines(text) if re.search(r"문의|연락처|☎", ln) and re.search(r"\d{2,4}[-.)]\s*\d{3,4}", ln)), None)
    if contact:
        req.contact = contact[:200]
    amount = next((ln for ln in _lines(text) if re.search(r"(?:지원|장학|지급)\s*(?:금액|액)|만\s*원|백만원", ln)), None)
    if amount:
        req.amount = amount[:200]
        evs += _ev("amount", amount)
    cnt = re.search(r"(?:선발|모집)\s*인원[^\n]{0,20}?(\d{1,4})\s*명|(\d{1,4})\s*명\s*(?:내외|이내|선발|모집)", text)
    if cnt:
        req.selection_count = (cnt.group(1) or cnt.group(2)) + "명"
        evs += _ev("selection_count", find_sentence(text, re.escape(cnt.group(0))))

    # 제외 사유: '3. 제외사유' 헤더 아래 항목들 + 한 줄짜리 '… 제외' 문장
    header_only = re.compile(r"^\s*(?:\d+\s*[.)]|[가-힣]\s*[.)])?\s*(?:신청\s*)?제외\s*(?:사유|대상|자)?\s*[:：]?\s*$")
    req.exclusions += section_lines(text, r"제외\s*(?:사유|대상|자)\s*[:：]?\s*$|신청\s*제외자?\s*[:：]", max_lines=6)
    for ln in _lines(text):
        if header_only.match(ln) or len(ln) >= 200:
            continue
        if re.search(r"제외\s*(?:대상|자|사유)|신청\s*(?:불가|제외)|지원\s*불가", ln):
            req.exclusions.append(LINE_HEADERS.sub("", ln))
        elif re.search(r"(?:학부|학과|전공|계열)\s*(?:재학생|학생|소속|재학)|추천을\s*받은|봉사|수상|거주|출신|자녀|납부자"
                       r"|여자\s*대학생|여학생|남학생|여성\s*(?:만|대상|지도자)|장애|국가유공|기초생활|차상위|다자녀|한부모", ln) and len(ln) < 160:
            req.other_conditions.append(re.sub(r"^[√·•○●\-*]\s*", "", LINE_HEADERS.sub("", ln)))
    req.exclusions = list(dict.fromkeys(e for e in req.exclusions if e and not header_only.match(e)))[:8]
    req.other_conditions = list(dict.fromkeys(req.other_conditions))[:8]

    req.evidence = evs
    structured = sum(x is not None for x in (req.grades_allowed, req.min_semesters_completed, req.min_gpa,
                                              req.min_credits_total, req.min_credits_last_semester,
                                              req.income_bracket_max, req.enrollment_status))
    if not structured and not req.other_conditions:
        req.unknown_fields = ["grades_allowed", "min_gpa", "major", "income_bracket_max"]
    # 규칙만으로는 0.6(자동 판정 문턱)을 넘기지 않는다 — 구조화 필드가 여럿 잡혀도 사람이 한 번 보게 한다.
    req.confidence = round(min(0.3 + 0.06 * structured + (0.05 if pd else 0), 0.6), 2)
    if not text.strip():
        req.confidence = 0.0
        req.notes.append("본문 텍스트 없음")
    return req
