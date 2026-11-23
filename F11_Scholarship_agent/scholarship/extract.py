"""자격 요건 추출 — 공지(제목·본문·첨부 PDF 글자) → Requirements(dict). 표준 라이브러리만, LLM 없이 돈다 (F11-R15).

notice_agent/scripts/rules_extract.py 의 규칙(학년·학기·평점·학점·소득구간·국적·학적·신청 기간·서류·방법)을 옮기고,
전남대 장학 게시판 실측(2026-10-09, 160건)에서 많이 보이는 것을 더했다:
  - 지역 장학(지자체·지역 재단)  regions.detect — 시·도/시·군 + 근거 문장
  - 계열 조건                    이공계 · 인문사회 · 예체능 · 농업(창업농) · 수산(어업인) · 의생명
  - 단과대학·캠퍼스 대상          '사회과학대학 성취장학' · '여수캠퍼스 청경나래 장학금'
  - 해당 사항(대상자 집단)        보훈·국가유공자 · 기초생활·차상위 · 장애 · 다자녀 · 한부모 (C2 해당 사항과 대조) + 북한이탈·자립준비청년 등
  - 신청 대상이 아닌 글           선발 결과 · 홍보·캠페인·박람회 · 대학원생 전용 · 외국인 유학생 전용
모든 값에 근거(원문 한 줄)를 붙인다 — 화면의 '근거' 칸이 이것이다 (F11-R12). 구조화하지 못한 조건은 otherConditions 에 원문 그대로 (F11-R14).
전공·학과 이름 조건은 오탐이면 '비해당'으로 잘못 걸러 놓치므로 규칙 단계에서는 otherConditions 로만 남긴다.
"""
from __future__ import annotations

import re
from typing import Optional

from . import config as C
from . import regions, registry
from .textutil import find_sentence, lines, nfkc, parse_period

NUM = r"(\d{1,2})"
LINE_HEADERS = re.compile(r"^\s*(?:\d+\.|[가-힣]\.|[○●□■▶▷◦•\-*※]|\(\d+\)|[①-⑳])\s*")
COND_LINE = re.compile(r"대상|자격|요건|조건|재학|해당|선발\s*기준|신청\s*가능")

# 해당 사항 — C2 프로필 flags 키와 짝 (없으면 프로필로 판단할 수 없는 집단)
GROUPS: list[tuple[str, Optional[str], str]] = [
    ("보훈", "veteranFamily", r"보훈|국가유공자|독립유공자|민주유공자|참전유공자"),
    ("기초생활·차상위", "basicLivelihood", r"기초생활\s*수급|차상위"),
    ("저소득층", None, r"저소득|가계\s*곤란"),               # 소득구간으로 가리는 경우가 많다 — 지원구간 입력을 묻는다(match)
    ("장애", "disability", r"장애(?:학생|인|의\s*정도|\s*등급)(?!\s*(?:학생\s*)?도우미)"),
    ("다자녀", "multiChild", r"다자녀"),
    ("한부모", "singleParent", r"한부모"),
    ("북한이탈주민", None, r"북한\s*이탈|탈북(?!\s*학생\s*멘토)"),
    ("자립준비청년", None, r"자립\s*준비\s*청년|보호\s*종료"),
    ("다문화가정", None, r"다문화\s*가정"),
    ("외국인 근로자 자녀", None, r"외국인\s*근로자\s*자녀"),
    ("선원 가족", None, r"선원\s*가족"),
    ("농어촌 출신", None, r"농촌\s*출신|농어촌\s*(?:출신|학생|전형)"),
    ("만학도·고졸 재직자", None, r"고졸\s*후학습|재직자"),
]
# 이 말이 같이 있으면 그 집단을 '돕는' 활동(멘토·도우미) 모집이지 대상자 조건이 아니다
HELPER = re.compile(r"멘토|도우미|튜터|봉사")

FIELDS: list[tuple[str, tuple[str, ...]]] = [
    (r"이공계|자연과학\s*(?:및|·|,|과)?\s*공학|이공\s*계열|과학기술\s*분야", ("자연과학", "공학")),
    (r"공학\s*계열|공대생", ("공학",)),
    (r"자연\s*과학\s*계열", ("자연과학",)),
    (r"인문\s*·?\s*사회\s*계열|인문사회\s*(?:분야|계열)|인문\s*100년", ("인문사회",)),
    (r"상경\s*계열", ("상경", "인문사회")),
    (r"예술\s*(?:및|·)?\s*체육|예체능|예술체육", ("예체능",)),
    (r"농업\s*계열|창업농|농업\s*관련\s*학과|농림\s*계열", ("농업",)),
    (r"수산\s*계열|어업인|수산\s*관련\s*학과", ("수산",)),
    (r"의생명|의학\s*계열|보건\s*계열|간호\s*학과|간호학\s*전공|공공\s*간호사", ("의약",)),
    (r"사범\s*계열|교원\s*양성|교육\s*계열", ("교육",)),
]
INFO_ONLY = re.compile(r"홍보|캠페인|박람회|설명회|활동\s*시간\s*연장|부정\s*수급|자진\s*신고|플랫폼|등록금\s*반환")
# 이미 신청한 사람에게 알리는 선발 절차 글 — '2단계 면접평가 안내' · '신규장학생 추천 기준 안내' · '최종 선발 공고' (2026-11-23 실측).
# 새로 신청하는 공지가 아니다
PROCESS_ONLY = re.compile(r"면접\s*(?:평가|심사|전형)?\s*(?:대상자?|일정|안내)|[12]\s*단계\s*면접|추천\s*기준\s*안내|심사\s*기준\s*안내|"
                          r"최종\s*선발")
# 게시판 편집기가 줄 앞에 넣는 보이지 않는 글자(U+200B …) — 남겨 두면 '5. 선발제외대상' 같은 번호 줄을 머리 줄로 알아보지 못한다
_ZERO_WIDTH = re.compile("[​‌‍⁠﻿]")
# 조건이 아닌 줄 — 우대·가산점(있으면 좋은 것) · 동의서 표 · 지급 시기·인원·문의 같은 안내
_PREFERENCE = re.compile(r"우대|가산점")
_NOT_CONDITION = re.compile(r"개인\s*\(?\s*신용\s*\)?\s*정보|개인\s*정보|수집\s*[·‧ㆍ.]?\s*이용|제공\s*[·‧ㆍ.]?\s*조회|동의서|"
                            r"^\s*(?:\d+\s*[.)]|[가-힣]\s*[.)]|[○●□■▶▷◦•\-*※])?\s*\(?\s*(?:지급\s*(?:시기|일|방법)|시상|수여식|문의|예시|유의|"
                            r"안내\s*사항|(?:추천|선발|모집)\s*인원)")
_DOC_LINE = re.compile(r"제출(?:하|바랍|해\s*주|\s*$|\s*\()|확인서|상장\s*사본|증빙")
_LIST_BULLET = re.compile(r"^\s*[-·•‧∙*○◦]")
_OTHER_COND = re.compile(r"(?:학부|학과|전공|계열)\s*(?:재학생|학생|소속|재학)|추천을\s*받은|추천\s*받은|봉사\s*(?:활동|시간|실적|점수|경력)|수상|(?<!다)자녀|"
                         r"납부자|여자\s*대학생|여학생|남학생|여성\s*(?:만|대상)|참여\s*학생(?![이은의가을])|이수\s*(?:학생|자)|"
                         r"융합전공\s*(?:학생|참여|이수)")
# 상시 장학 안내의 수혜자격 첫 줄 중 '누구나'에 가까운 말 — 이것만 있으면 기타 조건으로 남기지 않는다
GENERIC_QUAL = re.compile(r"^(?:▷\s*)?(?:성적이\s*우수하고\s*품행이\s*단정한\s*자|품행이\s*단정하고.*모범학생.*|"
                          r"성실하고\s*도전적이며.*|선발자격\s*:\s*성적이\s*우수하고.*)$")


def _ev(evs: dict, field: str, quote: Optional[str]) -> None:
    if quote and field not in evs:
        evs[field] = quote.strip()[:300]


# ── 개별 규칙 ──────────────────────────────────────────────

def grades(text: str) -> tuple[Optional[list[int]], Optional[str]]:
    # '신청대상: 신입생, 재학생, 복학생 … 등 모든 대학생' 이면 학년 조건이 없다. 지원 학년을 해마다 넓히는 일정 줄
    # ('27년 1학년 → '28년 1~2학년 → …)은 신청 대상 학년이 아니다 — 국가장학금 1차 신청 공지가 '1,2학년'으로 읽혀 3학년에게
    # 비해당으로 숨던 것 (2026-11-23 실측).
    if re.search(r"(?:대상|자격)[^\n]{0,40}(?:모든\s*(?:대학생|학생|학년)|전\s*학년|학년\s*(?:무관|제한\s*없음))", text):
        return None, None
    text = "\n".join(ln for ln in text.splitlines() if not re.search(r"→|단계적|확대\s*예정", ln))
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
    # '1학년 및 3학년' · '신입생 및 3학년' (국가우수장학금·대통령과학장학금 — 신규 선발 학년)
    m = re.search(rf"(?:{NUM}\s*학년|신입생)\s*(?:및|과|와|또는|,)\s*{NUM}\s*학년", text)
    if m:
        lo = int(m.group(1)) if m.group(1) else 1
        hi = int(m.group(2))
        if 1 <= lo <= 6 and 1 <= hi <= 6:
            return sorted({lo, hi}), find_sentence(text, re.escape(m.group(0)))
    m = re.search(rf"(?<![\d~∼～\-,，·])\s{NUM}\s*학년\s*(?:[12]\s*학기\s*)?(?:재학생|학생|만|에\s*한함|대상|재학\s*중)", text)
    if m:
        g = int(m.group(1))
        if 1 <= g <= 6:
            return [g], find_sentence(text, re.escape(m.group(0).strip()))
    if re.search(r"신입생\s*(?:만|에\s*한함|대상)", text) and not re.search(r"재학생", text):
        return [1], find_sentence(text, r"신입생\s*(?:만|에\s*한함|대상)")
    return None, None


def semesters(text: str) -> tuple[Optional[int], Optional[str]]:
    m = re.search(rf"{NUM}\s*학기\s*이상\s*(?:재학|이수|등록|수료)", text)
    if m:
        return int(m.group(1)), find_sentence(text, re.escape(m.group(0)))
    m = re.search(rf"{NUM}\s*학기\s*(?:진학|등록)\s*예정", text)
    if m:
        return max(int(m.group(1)) - 1, 0), find_sentence(text, re.escape(m.group(0)))
    return None, None


def gpa(text: str) -> tuple[Optional[dict], Optional[str]]:
    basis = "직전학기" if re.search(r"직전\s*학기", text) else ("전체" if re.search(r"전\s*학년|전체\s*학기|누적", text) else None)
    m = re.search(r"(\d\.\d{1,2})\s*(?:점)?\s*/\s*(4\.5|4\.3|4\.0)\s*(?:만점)?\s*(?:점)?\s*이상", text)
    if m:
        return {"value": float(m.group(1)), "scale": float(m.group(2)), "basis": basis}, find_sentence(text, re.escape(m.group(0)))
    m = re.search(r"(?:평점|평량|성적|GPA)[^\n\d]{0,14}(\d\.\d{1,2})\s*(?:\([^)\n]{0,20}\))?\s*(?:점)?\s*(?:수준\s*)?이상", text)
    if m:
        return {"value": float(m.group(1)), "scale": 4.5, "basis": basis}, find_sentence(text, re.escape(m.group(0)))
    m = re.search(r"(\d{2,3})\s*(?:점)?\s*/\s*100\s*(?:점)?\s*(?:만점)?\s*(?:의\s*)?(?:\d{2,3}\s*점\s*)?이상", text)
    if m:
        return {"value": float(m.group(1)), "scale": 100.0, "basis": basis}, find_sentence(text, re.escape(m.group(0)))
    m = re.search(r"100\s*점\s*만점(?:의|에)?\s*(\d{2,3})\s*점\s*이상", text)
    if m:
        return {"value": float(m.group(1)), "scale": 100.0, "basis": basis}, find_sentence(text, re.escape(m.group(0)))
    # '성적 70점 이상' · '백분위 점수가 70점 이상' (국가근로장학금 신청 자격, 2026-11-23)
    m = re.search(r"(?:백분위|백분율|환산점수|성적)\s*(?:점수|성적)?\s*(?:이|가|는|은)?\s*(\d{2,3})\s*점\s*이상", text)
    if m and 50 <= float(m.group(1)) <= 100:
        return {"value": float(m.group(1)), "scale": 100.0, "basis": basis}, find_sentence(text, re.escape(m.group(0)))
    return None, None


def credits(text: str, evs: dict) -> tuple[Optional[int], Optional[int]]:
    total = last = None
    for m in re.finditer(r"(\d{1,3})\s*학점\s*(?:이상\s*)?(?:을\s*)?(?:이수|취득)", text):
        line = find_sentence(text, re.escape(m.group(0))) or m.group(0)
        n = int(m.group(1))
        if not re.search(r"이상|이수한|취득한", line):
            continue
        if re.search(r"직전\s*학기|전\s*학기|해당\s*학기|매\s*학기", line) or n <= 24:
            if last is None:
                last = n; _ev(evs, "minCreditsLast", line)
        elif total is None:
            total = n; _ev(evs, "minCredits", line)
    return total, last


def income(text: str) -> tuple[Optional[int], Optional[str]]:
    m = re.search(r"(?:학자금\s*지원\s*|소득\s*)?(\d{1,2})\s*(?:구간|분위)\s*(?:이하|이내|까지)", text)
    if m and int(m.group(1)) <= 10:
        return int(m.group(1)), find_sentence(text, re.escape(m.group(0)))
    return None, None


def nationality(text: str) -> tuple[Optional[str], Optional[str]]:
    m = re.search(r"대한민국\s*국적", text)
    return ("대한민국", find_sentence(text, re.escape(m.group(0)))) if m else (None, None)


def enrollment(text: str) -> tuple[Optional[list[str]], Optional[str]]:
    if re.search(r"휴학생\s*(?:도\s*)?(?:포함|가능|신청\s*가능)", text):
        return ["재학", "휴학"], find_sentence(text, r"휴학생\s*(?:도\s*)?(?:포함|가능|신청\s*가능)")
    if re.search(r"재학생|재학\s*중|재학중인", text):
        return ["재학"], find_sentence(text, r"재학생|재학\s*중|재학중인")
    return None, None


def period(text: str, title: str = "", default_year: Optional[int] = None) -> tuple[Optional[dict], Optional[str]]:
    """신청/접수 기간 줄을 찾아 파싱. 없으면 제목의 '(~9/18까지)' 같은 표기라도 쓴다.
    period["strong"] = '신청기간' 같은 이름표가 붙은 줄에서 읽었고, 그런 줄이 여럿이어도 마감이 한 가지다 — 조건을 얼마나 뽑았는지와
    상관없이 마감일은 믿을 수 있다 (match 가 지난 마감을 '마감'으로 접는 데 쓴다)."""
    noise = re.compile(r"유효\s*기간|근로\s*기간|파견\s*기간|지급\s*기간|사업\s*기간|수혜\s*기간|장학\s*기간|활동\s*기간|"
                       r"학기\s*기간|교육\s*기간|운영\s*기간|연수\s*기간|인정\s*기간|실적|발표|결과|면접|"
                       r"평점|평균|만점|학점|백분위|성적")          # '평점 3.5/4.5 이상' 의 3.5 를 3월 5일로 읽지 않게
    # 날짜처럼 생긴 것 — 연도 · 'N월 N일' · '9. 14.(월)' · '~9/16' · 두 자리 연도 '’26. 10.'
    datey = re.compile(r"20\d{2}\s*[.\-/년]|\d{1,2}\s*월\s*\d{1,2}\s*일|\d{1,2}\s*[./]\s*\d{1,2}\s*\.?\s*\([월화수목금토일]|"
                       r"[~∼～]\s*\d{1,2}\s*[./]\s*\d{1,2}|['’‘`]\s*\d{2}\s*[.년]\s*\d{1,2}")
    label = re.compile(r"(?:신청|접수|모집|지원|제출|추천)\s*(?:기간|기한|마감|일정|일시)")
    strong: list[tuple[str, str]] = []        # (파싱할 글자, 근거로 보일 원문 한 줄)
    weak: list[tuple[str, str]] = []
    ls = lines(text)
    for i, ln in enumerate(ls):
        if noise.search(ln):
            continue
        if label.search(ln) and not datey.search(ln) and len(ln) < 40:
            # 이름표만 있는 줄 — 날짜는 다음 줄에 ('□ 신청 및 서류 제출 기간' / 'ㅇ ’26. 10. 22.(수) 9시 ∼ ’26. 11. 12.(목) 18시')
            nxt = next((x for x in ls[i + 1:i + 3] if datey.search(x) and not noise.search(x) and not label.search(x)), None)
            if nxt:
                strong.append((f"{ln} {nxt}", nxt))
            continue
        if not re.search(r"\d", ln) or not datey.search(ln):
            continue
        if label.search(ln):
            strong.append((ln, ln))
        elif re.search(r"기간\s*[:：]|마감\s*[:：]|까지", ln):
            weak.append((ln, ln))
    parsed = [(parse_period(src, default_year), src, quote) for src, quote in strong]
    ends = {e[:10] for (s, e), _, _ in parsed if e}
    for k, ((s, e), src, quote) in enumerate(parsed + [(parse_period(src, default_year), src, quote) for src, quote in weak]):
        if s or e:
            return {"start": s, "end": e, "raw": src[:200], "strong": k < len(parsed) and len(ends) == 1}, quote
    if title:
        m = re.search(r"[~∼～]\s*[\d./월 ]+일?\s*(?:\([^)]*\))?\s*(?:까지)?", title)
        if m:
            s, e = parse_period(m.group(0), default_year)
            if e:
                return {"start": None, "end": e, "raw": m.group(0), "strong": False}, title
    return None, None


def section_lines(text: str, header_pat: str, max_lines: int = 8, list_only: bool = False) -> list[str]:
    """'제출서류' 같은 헤더 줄 다음의 항목들 (다음 번호 헤더 전까지).
    list_only = 항목이 글머리표('- 휴학생 …')로 시작했으면 글머리표가 끊기는 줄에서 멈춘다 — 목록 아래의 설명 문단까지 항목으로 읽지 않게."""
    out: list[str] = []
    ls = lines(text)
    for i, ln in enumerate(ls):
        if re.search(header_pat, ln):
            same = re.split(header_pat, ln, maxsplit=1)[-1].strip(" :：-")
            if len(same) > 3:
                out.append(same)
            bulleted = False
            for nxt in ls[i + 1:i + 1 + max_lines]:
                if re.match(r"^\s*\d+\s*[.)]\s*\S", nxt) and not re.match(r"^\s*\d+\s*[.)]\s*[가-힣]{0,6}\s*(서|증|본|부)\b", nxt):
                    break
                if re.search(header_pat, nxt):
                    break
                if list_only:
                    if _LIST_BULLET.match(nxt):
                        bulleted = True
                    elif bulleted:
                        break
                out.append(LINE_HEADERS.sub("", nxt))
            break
    return [o for o in out if o]


_RES_GPA = re.compile(r"(?:직전\s*학기|전체\s*학기|전\s*학년)?\s*(?:까지\s*)?(?:의\s*)?(?:누계\s*)?(?:평균\s*평점|평점\s*평균|평점|성적)\s*"
                      r"(?:이|은)?\s*\d(?:\.\d{1,2})?\s*(?:\([^)]*\))?\s*(?:점)?\s*이상")
_RES_CREDIT = re.compile(r"\d{1,3}\s*학점\s*(?:이상\s*)?(?:을\s*)?(?:이수|취득)(?:한|하고)?")
_RES_DOCS = re.compile(r"(?:[가-힣A-Za-z·‧]+\s*){1,4}(?:계획서|보고서)(?:\s*(?:및|와|과)\s*(?:[가-힣A-Za-z·‧]+\s*){0,3}(?:계획서|보고서))?"
                       r"\s*(?:를|을)?\s*제출(?:한\s*자|자)")


def qualification_residue(line: str) -> str:
    """상시 안내의 수혜자격 한 줄에서 이미 구조화한 것(평점·이수학점)과 선발 문구를 걷어낸 나머지 — 비면 따로 확인할 조건이 없다.
        '재학생: 위 해당자 중 직전 학기 평균평점이 1.75(실점 72.5점) 이상이고, 12학점 이상 이수한 자 중에서 선발'  → ''
        '… 12학점 이상 이수한 자로서 취업계획서 제출자 중에서 선발'  → ''   (서류를 내는 것은 자격이 아니라 절차)
        '… 12학점 이상 이수한 자로 학군단장이 추천한 자 중에서 선발'  → '자로 학군단장이 추천한 자'"""
    r = re.sub(r"^(?:재학생|신입생|편입생)\s*[:：]\s*", "", line.strip())
    r = re.sub(r"위\s*(?:해당자|대상자)\s*(?:중|로서|로)?", " ", r)
    r = _RES_CREDIT.sub(" ", _RES_GPA.sub(" ", r))
    r = re.sub(r"\s*(?:중에서|가운데)\s*선발(?:함|한다)?\.?\s*$", "", r.strip())
    keep = []
    for part in re.split(r"자로서|으로서|로서|이고|이며|,", r):
        p = re.sub(r"^(?:인|한)?\s*자$", "", part.strip(" ·‧")).strip()
        if p and not _RES_DOCS.fullmatch(p):
            keep.append(p)
    return " ".join(keep)


def bracket_provider(title: str) -> Optional[str]:
    for m in re.finditer(r"\[([^\]]{2,40})\]", title):
        s = m.group(1).strip()
        if s in ("장학안내", "장학", "공지", "안내", "학사안내", "장학관련", "모집공고", "대학생활", "일반공지"):
            continue
        return s
    return None


def guess_kind(title: str, provider: Optional[str], unit: Optional[dict]) -> str:
    blob = f"{title} {provider or ''}"
    if re.search(r"국가장학금|국가근로|한국장학재단|국가\s*우수|이공계|대통령과학|인문100년|희망사다리|푸른등대|주거안정", blob):
        return "국가"
    if unit and unit.get("group") == "project" or re.search(r"사업단|AICOSS|SW중심|소프트웨어중심|HUSS|RISE|COSS", blob):
        return "사업단"
    if re.search(r"재단|장학회|시\]|군\]|구\]|진흥원|기업|은행|협회|재단법인|보훈지청|연구원\]", blob):
        return "교외"
    return "교내"


def target_groups(title: str, text: str, first_only: bool = False) -> tuple[list[dict], Optional[str], bool]:
    """대상자 집단 — 제목 또는 조건 줄에서 → (집단들, 근거, 제목에서 찾았나).
    '멘토·도우미 모집'처럼 돕는 활동이면 조건이 아니다. 본문에서만 찾은 집단은 여러 세부 유형 중 하나일 수 있다
    (푸른등대 기부장학금: 기부처마다 대상이 다르다) — 그래서 제목에서 찾았을 때만 '미달'로 단정한다(match)."""
    found: list[dict] = []
    quote = None
    in_title = False
    if first_only:      # 상시 안내 — 수혜자격 첫 줄만 ('기초생활수급자~9분위 이내' 같은 범위 줄을 대상 집단으로 읽지 않게)
        body = [ln for ln in lines(text) if not ln.startswith(("[", "※"))][:1]
    else:
        body = [ln for ln in lines(text) if COND_LINE.search(ln) and len(ln) < 220][:25]
    for i, ln in enumerate([title] + body):
        if HELPER.search(ln) or re.search(r"(?:수급|차상위)[^\n]{0,6}[~∼～][^\n]{0,6}(?:분위|구간)", ln):
            continue
        for label, key, pat in GROUPS:
            if re.search(pat, ln) and all(g["label"] != label for g in found):
                found.append({"label": label, "profileKey": key})
                quote = quote or ln
                in_title = in_title or i == 0
    return found, quote, in_title


def fields_required(title: str, text: str) -> tuple[list[str], Optional[str]]:
    cand = [title] + [ln for ln in lines(text) if COND_LINE.search(ln) and len(ln) < 220][:25]
    out: list[str] = []
    quote = None
    for ln in cand:
        for pat, groups in FIELDS:
            if re.search(pat, ln):
                for g in groups:
                    if g not in out:
                        out.append(g)
                quote = quote or ln
        if out:
            break
    return out, quote


def colleges_in_title(title: str) -> list[str]:
    """'사회과학대학 2026학년도 성취·성장 장학사업' → ['사회과학대학']. 단과대학 이름이 제목에 있으면 그 단과대학 학생 대상으로 본다."""
    t = nfkc(title)
    hits = []
    for name in registry.college_names():
        if re.search(re.escape(name) + r"(?!원)", t) and not any(name in h for h in hits):
            hits.append(name)
    return hits


def campus_in(title: str) -> Optional[str]:
    m = re.search(r"(여수|광주|화순)\s*캠퍼스", nfkc(title))
    return {"여수": "여수", "광주": "광주", "화순": "광주"}[m.group(1)] if m else None


def grad_only(title: str) -> bool:
    t = nfkc(title)
    return bool(re.search(r"대학원|석사|박사", t)) and not re.search(r"대학\s*\(\s*원\s*\)|학부|대학생|학사|학ㆍ석사|학·석사", t)


def foreign_only(title: str) -> bool:
    return bool(re.search(r"(?:외국인\s*)?유학생(?:\s*대상|\s*장학|\s*모집|\s*선발)|international\s+students", nfkc(title), re.I))


# ── 진입점 ────────────────────────────────────────────────

def extract(title: str, text: str, *, unit: Optional[dict] = None, image_only: bool = False,
            attachments_unread: int = 0, default_year: Optional[int] = None, catalog: bool = False, ocr: bool = False,
            ocr_text: Optional[str] = None) -> dict:
    """제목 + 본문(+첨부 글자) → Requirements. unit = 이 글을 올린 사업단·부서(registry.unit_for).
    ocr = 글자 일부를 이미지에서 OCR 로 읽었다(attachments.has_ocr) — 신뢰도를 OCR_CONFIDENCE_CAP 까지로, 판정은 확인 필요로 (match).
    ocr_text = OCR 로 읽은 덩어리를 따로 넘기면(collect.build_req) text 는 글자로 읽힌 원문(본문·HWP·PDF)만이다. 규칙은 원문을 먼저 보고,
    OCR 에서만 찾은 값(req["ocrFields"])이 있거나 원문이 OCR_MAIN_ENOUGH 보다 짧을 때만 신뢰도를 묶는다 — 본문에 조건이 다 있고
    스캔한 신청 매뉴얼만 OCR 로 읽은 공지까지 묶던 것(2026-11-23)."""
    title = _ZERO_WIDTH.sub("", nfkc(title))
    text = _ZERO_WIDTH.sub("", nfkc(text))
    main_text: Optional[str] = None           # None = 원문·OCR 을 가르지 않고 받았다 (F12 · 예전 방식) — OCR 이 있으면 전부 묶는다
    if ocr_text:
        main_text = text
        text = f"{text}\n\n{_ZERO_WIDTH.sub('', nfkc(ocr_text))}".strip()
        ocr = True
    full = f"{title}\n{text}"
    evs: dict[str, str] = {}
    req: dict = {"extractor": "rules"}
    req["provider"] = bracket_provider(title) or (unit or {}).get("org")
    req["kind"] = "교내" if catalog else guess_kind(title, req["provider"], unit)
    req["scholarshipName"] = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", title).strip() or title

    g, q = grades(full); req["grades"] = g; _ev(evs, "grades", q)
    s, q = semesters(full); req["minSemesters"] = s; _ev(evs, "minSemesters", q)
    gp, q = gpa(full); req["minGpa"] = gp; _ev(evs, "minGpa", q)
    req["minCredits"], req["minCreditsLast"] = credits(full, evs)
    ib, q = income(full); req["incomeMax"] = ib; _ev(evs, "incomeMax", q)
    na, q = nationality(full); req["nationality"] = na; _ev(evs, "nationality", q)
    en, q = enrollment(full); req["enrollment"] = en; _ev(evs, "enrollment", q)
    pd, q = (None, None) if catalog else period(text, title, default_year)
    req["period"] = pd; _ev(evs, "period", q)

    reg = regions.detect(title, text)
    req["residency"] = reg
    if reg:
        _ev(evs, "residency", reg.get("quote"))
    fl, q = fields_required(title, text); req["fields"] = fl or None; _ev(evs, "fields", q)
    tg, q, tg_title = target_groups(title, text, first_only=catalog)
    req["groups"] = tg or None
    req["groupsSure"] = bool(tg) and (tg_title or catalog)        # 제목·상시 안내 한 줄에서 찾은 대상 → 미달을 단정해도 된다
    _ev(evs, "groups", q)
    req["colleges"] = colleges_in_title(title) or None
    if req["colleges"]:
        _ev(evs, "colleges", title)
    req["campus"] = campus_in(title)
    if req["campus"]:
        _ev(evs, "campus", title)
    req["gradOnly"] = grad_only(title)
    req["foreignOnly"] = foreign_only(title)
    process = bool(PROCESS_ONLY.search(title)) and not catalog
    req["infoOnly"] = process or (bool(INFO_ONLY.search(title)) and not re.search(r"신청\s*안내|선발\s*안내|모집\s*안내", title))
    req["infoKind"] = "process" if process else ("info" if req["infoOnly"] else None)

    docs = section_lines(text, r"제출\s*서류|구비\s*서류|신청\s*서류|첨부\s*서류")
    doc_like = re.compile(r"증명|사본|확인서|계획서|추천서|소개서|지원서|신청서|동의서|통지서|등본|초본|카드|양식|서류|서\s*\d*\s*부|부$|파일|성적표|증$")
    cell_header = re.compile(r"^(?:필수|기타|선택|공통|추가|본인|가족|해당자만|제출)\s*(?:서류)?\s*[:：]?$")
    docs = [re.sub(r"^[√·•○●\-*]\s*", "", d).strip() for d in docs]
    split: list[str] = []
    for d in docs:                                   # '장학금 신청서 1부, 재학증명서 1부' — 한 줄에 여럿이면 나눠 체크리스트 칸마다 하나씩
        parts = [x.strip() for x in re.split(r"\s*[,，]\s*(?![^()]*\))", d) if x.strip()]
        split += parts if len(parts) > 1 and all(doc_like.search(x) for x in parts) else [d]
    req["documents"] = list(dict.fromkeys(d for d in split if 4 <= len(d) <= 120 and doc_like.search(d)
                                          and not cell_header.match(d)))[:10]
    if req["documents"]:
        _ev(evs, "documents", req["documents"][0])
    meth = section_lines(text, r"신청\s*방법|접수\s*방법|지원\s*방법|신청\s*절차|접수\s*처|지원\s*접수|온라인\s*지원|제출\s*방법|제출\s*처", max_lines=3)
    meth = [re.sub(r"^[√·•○●\-*]\s*", "", x) for x in meth if len(x) > 3 and x not in ("및 문의", "문의")]
    req["applyMethod"] = " / ".join(meth)[:300] if meth else None
    if meth:
        _ev(evs, "applyMethod", meth[0])
    url = re.search(r"https?://[^\s)\]>\"'<]+", text) or re.search(r"(?<![A-Za-z0-9.])www\.[A-Za-z0-9.\-]+\.[a-z]{2,}(?:/[^\s)\]>\"'<]*)?", text)
    req["applyUrl"] = None
    if url:
        u = url.group(0).rstrip(".,")
        req["applyUrl"] = u if u.startswith("http") else "https://" + u
    contact = next((ln for ln in lines(text) if re.search(r"문의|연락처|☎", ln) and re.search(r"\d{2,4}[-.)]\s*\d{3,4}", ln)), None)
    req["contact"] = contact[:200] if contact else None
    amount = next((ln for ln in lines(text) if re.search(r"(?:지원|장학|지급)\s*(?:금액|액|내용)|만\s*원|백만원|등록금\s*전액|수업료", ln)
                   and len(ln) < 200), None)
    req["amount"] = amount[:200] if amount else None
    if amount:
        _ev(evs, "amount", amount)
    cnt = re.search(r"(?:선발|모집)\s*인원[^\n]{0,20}?(\d{1,4})\s*명|(\d{1,4})\s*명\s*(?:내외|이내|선발|모집)", text)
    req["selectionCount"] = ((cnt.group(1) or cnt.group(2)) + "명") if cnt else None

    excl: list[str] = []
    others: list[str] = []
    header_only = re.compile(r"^\s*(?:\d+\s*[.)]|[가-힣]\s*[.)])?\s*(?:신청\s*|선발\s*)?제외\s*(?:사유|대상|자)?\s*[:：]?\s*$")
    if not catalog:        # 상시 안내의 '… 지원 제외자' 는 그 장학의 대상을 말하는 줄이다 — 아래 줄(지급액 …)을 제외 사유로 읽지 않는다
        excl += section_lines(text, r"제외\s*(?:사유|대상|자)\s*[:：]?\s*$|신청\s*제외자?\s*[:：]", max_lines=6, list_only=True)
    pref_block = False     # '우대사항 … 가산점 부여' 아래에 글머리표로 이어지는 줄들 ('- 대한민국인재상 수상')
    for ln in lines(text):
        if header_only.match(ln) or len(ln) >= 200:
            continue
        if _NOT_CONDITION.search(ln):                       # 동의서 표 · 지급 시기 · 추천 인원 · 예시 — 조건도 제외 사유도 아니다
            pref_block = False
            continue
        if re.search(r"제외\s*(?:대상|자|사유)|신청\s*(?:불가|제외)|지원\s*불가|중복\s*수혜", ln):
            excl.append(LINE_HEADERS.sub("", ln))
            pref_block = False
            continue
        if _PREFERENCE.search(ln):                          # 우대·가산점은 있으면 좋은 것 — 신청 자격이 아니다
            pref_block = True
            continue
        if pref_block and _LIST_BULLET.match(ln):
            continue
        pref_block = False
        # '학부 재학생 2명' 의 '학부'는 학과 조건이 아니다(학부생이라는 말) — 앞에 학과 이름이 붙은 '인공지능학부 재학생'만 조건
        probe = re.sub(r"(?<![가-힣])학부\s*(?:재학생|학생|재학)", "", ln)
        if not catalog and _OTHER_COND.search(probe) and len(ln) < 160 and not _DOC_LINE.search(ln):
            others.append(re.sub(r"^[√·•○●\-*]\s*", "", LINE_HEADERS.sub("", ln)))
    if catalog:
        # 상시 안내의 수혜자격 줄 — 평점·학점만 말하는 줄과 '누구나' 문구를 빼고 남는 것이 진짜 조건이다
        # ('학군단 장학생으로 선발된 자' · '형제·자매·부모 중 3명 이상 재적' · '기관장의 추천을 받은 자')
        special = re.compile(r"자로서|대상자|해당자|추천|선발된|계획서|보고서|외국어|봉사|가계|합격|당선|수상|임원|재적|교류|"
                             r"입학자|전형|보호|장애|이탈|유공|재직|취업|창업|신청한\s*자")
        kept = 0
        for ln in lines(text):
            s = re.sub(r"^[▷\-•·○‧]\s*", "", ln).strip()
            if re.match(r"(?:계속\s*지원|지원\s*유형|지원\s*기간)", s) or ln.startswith("※"):
                break                                   # 이 아래는 계속지원·유형 설명 — 신청 자격이 아니다
            if (not s or len(s) < 8 or ln.startswith(("[", "(장학기본성적)", "지급액")) or GENERIC_QUAL.match(ln.strip())
                    or s.startswith(("신입생", "성적기준", "학적사항"))):
                continue
            if (re.search(r"평점|학점|성적|백분위", s) and not special.search(s)) or                     (req.get("fields") and "계열" in s and not special.search(s)) or (req.get("incomeMax") and "소득" in s):
                continue
            if re.search(r"평점|학점|성적", s) and not qualification_residue(s):
                continue                                # 평점·학점(이미 구조화)과 '… 중에서 선발'·계획서 제출뿐인 줄 — 따로 확인할 조건이 없다
            others.append(s[:150])
            kept += 1
            if kept >= 2:
                break
    # 같은 제외 사유가 머리 줄 아래 항목과 '… 제외자: …' 한 줄로 두 번 잡힌다 — 글자가 포함 관계면 하나만
    uniq_excl: list[str] = []
    for e in excl:
        key = re.sub(r"[\s\W_]+", "", e)
        if not e or header_only.match(e) or not key:
            continue
        if any(key in k or k in key for k in (re.sub(r"[\s\W_]+", "", u) for u in uniq_excl)):
            continue
        uniq_excl.append(e)
    req["exclusions"] = uniq_excl[:8]
    excl_keys = {re.sub(r"[\s\W_]+", "", e) for e in uniq_excl}
    req["otherConditions"] = [o for o in dict.fromkeys(others) if re.sub(r"[\s\W_]+", "", o) not in excl_keys][:8]

    req["evidence"] = evs
    structured_keys = ("grades", "minSemesters", "minGpa", "minCredits", "minCreditsLast",
                       "incomeMax", "enrollment", "residency", "fields", "groups", "colleges")
    structured = sum(req[k] is not None for k in structured_keys)
    req["structured"] = structured
    # OCR 에서만 찾은 값 — 근거 줄이 제목·원문(글자로 읽힌 본문·첨부)에 없으면 OCR 덩어리에서 온 것이다
    ocr_fields: Optional[list[str]] = None
    capped = bool(ocr)
    if ocr and main_text is not None:
        hay = f"{title}\n{main_text}"
        ocr_fields = [k for k in (*structured_keys, "period") if req.get(k) is not None and evs.get(k) and evs[k] not in hay]
        capped = bool(ocr_fields) or len(main_text.strip()) < C.OCR_MAIN_ENOUGH
    unread_heavy = attachments_unread > 0 and len(text) < 300           # 본문은 짧고 조건은 HWP 첨부에 있는 흔한 경우
    req["needsOcr"] = bool(image_only) and len(text.strip()) < 60
    req["attachmentsUnread"] = attachments_unread
    conf = 0.35 + 0.08 * structured + (0.1 if pd else 0) + (0.05 if not req["otherConditions"] else 0)
    if catalog:
        conf = 0.55 + 0.05 * structured                                   # 학교가 표로 정리한 안내 — 문구가 정형이다
    if unread_heavy:
        conf = min(conf, 0.4)
    req["ocr"] = bool(ocr)
    req["ocrFields"] = ocr_fields                   # None = 가르지 않고 받음(전부 OCR 일 수 있다) · [] = OCR 에서 뽑은 값 없음
    req["ocrCapped"] = capped
    if capped:
        conf = min(conf, C.OCR_CONFIDENCE_CAP)
    if req["needsOcr"]:
        conf = 0.0
    req["confidence"] = round(min(conf, 0.8), 2)
    req["unknownFields"] = [] if structured or req["otherConditions"] else ["grades", "minGpa", "incomeMax"]
    notes = []
    if capped:
        notes.append("이미지 속 글자를 OCR 로 읽었습니다 — 숫자·날짜가 틀릴 수 있으니 원문에서 확인하세요")
    elif ocr:
        notes.append("첨부 일부(스캔 문서·이미지)를 OCR 로 읽었습니다 — 조건과 날짜는 글자로 읽힌 본문에서 뽑았습니다")
    if req["needsOcr"]:
        notes.append("본문이 이미지라 자동으로 읽지 못했습니다")
    if attachments_unread:
        notes.append(f"첨부 {attachments_unread}개를 읽지 못했습니다(엑셀·스캔 문서·암호 문서 등) — 원문에서 조건을 확인하세요")
    req["notes"] = notes
    return req
