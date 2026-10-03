"""규칙 기반 판정 — 유형(type) · 대상(audience) · 학기(semester) · 바로가기 링크.

LLM 을 쓰지 않는다. 학사일정 표는 제목 형식이 고정돼 있어 이 규칙만으로 충분하고(요구사항 F1 7절 '0.9 이상'),
공지에서 뽑은 일정도 같은 규칙으로 유형·대상을 붙인다.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from .models import Audience
from .textutil import nfkc

# 순서가 중요하다 — 위에서 먼저 걸리는 것이 이긴다.
_TYPE_RULES: list[tuple[str, re.Pattern]] = [
    ("holiday", re.compile(r"휴업|공휴일|대체\s*휴일|개교기념일|(?<!보)휴강")),
    ("exam", re.compile(r"중간\s*고사|기말\s*고사|중간\s*시험|기말\s*시험|시험\s*기간")),
    ("course_reg", re.compile(r"수강\s*(?:신청|정정|취소|철회|희망)|폐강|교과구분\s*정정|계절\s*(?:학기|수업).*(?:신청|수요조사)")),
    ("grade", re.compile(r"성적|이의\s*신청|학점\s*(?:인정|포기|취득)")),
    ("registration", re.compile(r"휴학|복학|전과|복수\s*전공|부\s*전공|융합\s*전공|연계\s*전공|전공\s*(?:배정|변경|선택)|제적|자퇴|유보|학적|학생증|학위연계")),
    # '(등록)' '(미등록)' 은 휴학 종류를 가르는 말이라 납부 일정이 아니다 → 괄호 바로 뒤의 '등록'은 세지 않는다
    ("tuition", re.compile(r"등록금|납부|분할\s*납부|고지서|(?:^|\s)(?:최종|추가|수료\s*후)?\s*등록(?!\s*(?:기간\s*)?내)")),
    ("vacation", re.compile(r"개강|종강|방학|계절\s*학기|계절\s*수업")),
    ("event", re.compile(r"입학식|학위\s*수여식|졸업식|축제|설명회|박람회|체육\s*대회|행사|면접")),
]

_FACULTY = re.compile(r"수업\s*계획서|강의\s*계획서\s*입력|성적\s*(?:제출|정정)\s*마감|교수\s*수업\s*개선서|CQI|강의\s*평가\s*결과")
_GRADUATE = re.compile(r"대학원|석\s*·?\s*박사|석박사|학위\s*청구\s*논문|논문\s*심사")
_UNDERGRAD_HINT = re.compile(r"학부|학\s*·\s*석|학석사|학사\s*과정")
_GRADE_N = re.compile(r"([1-6])\s*학년")
_FRESHMAN = re.compile(r"신입생|입학식|신\s*\(\s*편\s*\)\s*입생|편입생")
_GRADUATING = re.compile(r"졸업\s*(?:대상|예정)자|학위\s*수여식|졸업식|졸업\s*\(\s*수료\s*\)|졸업\s*유보")
_RETURNING = re.compile(r"복학|휴학\s*연장")

# 전남대 단과대 (홈페이지 '대학·학부' 메뉴, 2026-09 기준). 공지 제목에 이 이름이 있으면 그 단과대 대상으로 본다.
COLLEGES = ("간호대학", "경영대학", "공과대학", "농업생명과학대학", "사범대학", "사회과학대학", "생활과학대학", "수의과대학",
            "약학대학", "예술대학", "의과대학", "인문대학", "자연과학대학", "AI융합대학", "자율전공학부", "공학대학",
            "문화사회과학대학", "수산해양대학", "창의융합학부")

PORTAL = "https://portal.jnu.ac.kr"
_ACTIONS = {
    "course_reg": "포털에서 수강신청",
    "tuition": "포털에서 고지서 출력",
    "registration": "포털에서 신청",
    "grade": "포털에서 성적 확인",
}


def classify_type(title: str) -> str:
    t = nfkc(title)
    if "보강" in t:          # '10. 5.(월) 개천절 대체휴일 보강' 은 휴일이 아니라 수업하는 날
        return "etc"
    for name, pat in _TYPE_RULES:
        if pat.search(t):
            return name
    return "etc"


def classify_audience(title: str, context: str = "") -> Audience:
    """제목(+ 공지 제목 같은 맥락)에서 대상 조건을 읽는다. 못 읽으면 전교생."""
    t = nfkc(title)
    ctx = nfkc(context)
    both = f"{t} {ctx}"
    if _FACULTY.search(t):
        return Audience(roles=["faculty"], raw="교원")
    if _GRADUATE.search(both) and not _UNDERGRAD_HINT.search(both) and not re.search(r"등록\s*및", t):
        return Audience(roles=["graduate"], raw="대학원생")
    a = Audience()
    raws: list[str] = []
    grades = sorted({int(g) for g in _GRADE_N.findall(t)})
    if "전학년" in t.replace(" ", ""):
        grades = []
    if grades:
        a.grades = grades
        raws.append("·".join(str(g) for g in grades) + "학년")
    elif _FRESHMAN.search(t):
        a.grades = [1]
        raws.append("신입생")
    elif _GRADUATING.search(t):
        a.grades = [4]
        a.enrollment = ["재학", "졸업유예"]
        raws.append("졸업(예정)자")
    if _RETURNING.search(t) and not a.enrollment:
        a.enrollment = ["휴학"]
        raws.append("휴학생")
    cols = [c for c in COLLEGES if c in both]
    if cols:
        a.colleges = cols
        raws.append("·".join(cols))
    a.raw = " · ".join(raws)
    return a


def semester_of(title: str, day: Optional[date]) -> str:
    """'2026-2' 같은 학기 키. 제목에 학기가 있으면 그것을, 없으면 날짜로 정한다.

    학년도는 3월에 시작한다. 1월 = 전 학년도 2학기(성적 마감·동계 계절), 2~7월 = 1학기, 8~12월 = 2학기.
    """
    if day is None:
        return ""
    t = nfkc(title)
    y = day.year
    m = re.search(r"(20\d{2})\s*학년도", t)
    year_hint = int(m.group(1)) if m else None
    sem: Optional[int] = None
    sm = re.search(r"제?\s*([12])\s*학기", t)
    if sm:
        sem = int(sm.group(1))
    elif "동계" in t:
        sem = 2
    elif "하계" in t:
        sem = 1
    if sem is None:
        if day.month == 1:
            return f"{y - 1}-2"
        return f"{y}-1" if day.month <= 7 else f"{y}-2"
    if year_hint:
        return f"{year_hint}-{sem}"
    if sem == 1:
        return f"{y + 1}-1" if day.month >= 10 else f"{y}-1"      # 12월에 받는 다음 해 1학기 휴·복학
    return f"{y - 1}-2" if day.month <= 2 else f"{y}-2"            # 1월의 2학기 성적 마감


def action_for(type_: str, audience: Audience) -> tuple[Optional[str], Optional[str]]:
    """학생이 직접 해야 하는 일정이면 포털 바로가기 (F1 6절 actionUrl)."""
    if audience.roles and "faculty" in audience.roles:
        return None, None
    label = _ACTIONS.get(type_)
    return (PORTAL, label) if label else (None, None)
