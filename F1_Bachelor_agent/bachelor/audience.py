"""대상 조건 판정 `appliesToMe` (F1-R40~R43, F1 7절 표).

결과는 셋 중 하나: True(내 해당) / False(해당 없음) / None(판단 불가 — 프로필에 그 항목이 없음).
저장하지 않고 **읽을 때마다 계산**한다 → 프로필을 바꾸면 바로 다시 판정된다(F1-R43).

프로필(C2, 대시보드가 PUT /api/profile 로 저장)에서 쓰는 값:
    grade(int) · enrollment('재학'|'휴학'|'졸업유예') · college · department · major (이름 문자열)
"""
from __future__ import annotations

from typing import Optional

from .models import Audience
from .textutil import squash


def _name_match(wanted: list[str], mine: list[Optional[str]]) -> Optional[bool]:
    mine_n = [squash(m) for m in mine if m]
    if not mine_n:
        return None
    for w in wanted:
        wn = squash(w)
        if any(wn and (wn in m or m in wn) for m in mine_n):
            return True
    return False


def applies_to_me(aud: Audience, profile: Optional[dict]) -> Optional[bool]:
    p = profile or {}
    roles = aud.roles or []
    if roles and "faculty" in roles and "graduate" not in roles:
        return False                      # 교원 일정(수업계획서 입력·성적 제출)은 학생에게 해당하지 않는다
    results: list[Optional[bool]] = []
    if roles and "graduate" in roles:
        results.append(False if p else None)   # 프로필은 학부생 기준 — 대학원 과정 표시가 없다
    if aud.grades:
        g = p.get("grade")
        results.append(None if not g else int(g) in aud.grades)
    if aud.enrollment:
        e = p.get("enrollment")
        results.append(None if not e else e in aud.enrollment)
    if aud.colleges:
        results.append(_name_match(aud.colleges, [p.get("college")]))
    if aud.departments:
        results.append(_name_match(aud.departments, [p.get("department"), p.get("major")]))
    if not results:
        return True                       # 조건 없음 = 전교생
    if any(r is False for r in results):
        return False
    if any(r is None for r in results):
        return None
    return True
