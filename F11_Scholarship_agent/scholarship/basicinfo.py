"""초안 기본 정보 — 이름 · 학번 · 학과(소속) · 학년 · 연락처 · 이메일 + 작성일. 표준 라이브러리만. F12 대외활동도 이것을 쓴다.

2026-10-25 사용자 결정: 초안 재료는 기본 정보(학과·학번·이름·날짜 …)부터 적는다. 그전에는 이름·학번을 아예 받지 않고
초안에 `{{이름}}`·`{{학번}}` 빈칸만 두었다(F11-R44). 이제는
  - 기능마다의 **초안 재료**(F11·F12 DB 의 meta.materials — 따로 저장·따로 지움)에 `basic` 으로 둔다.
    C2 프로필에는 넣지 않는다(C2-D5 그대로 — 프로필은 여러 기능·판정에 넘어간다).
  - **LLM 프롬프트에는 보내지 않는다.** 문단은 지금처럼 `{{이름}}` 빈칸으로 만들고, 다 만든 뒤 이 PC 에서 채운다(fill).
  - 비어 있으면 다른 기능(장학 ↔ 대외활동)에 적어 둔 기본 정보, 그다음 프로필의 소속·학년으로 미리 채운다(resolve).
  - 작성일은 초안을 만든 날.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

KEYS = ("name", "studentId", "department", "grade", "phone", "email")
LIMITS = {"name": 40, "studentId": 20, "department": 80, "grade": 10, "phone": 30, "email": 80}
LABELS = {"name": "이름", "studentId": "학번", "department": "학과(소속)", "grade": "학년", "phone": "연락처", "email": "이메일"}
# 초안 빈칸 → 기본 정보 (LLM·템플릿·이전 초안이 남긴 빈칸을 채운다)
FILL = {"이름": "name", "학번": "studentId", "연락처": "phone", "이메일": "email", "소속": "department"}


def clean(v: Optional[dict]) -> dict:
    v = v if isinstance(v, dict) else {}
    return {k: " ".join(str(v.get(k) or "").split())[:LIMITS[k]] for k in KEYS}


def from_profile(profile: Optional[dict]) -> dict:
    """프로필에서 미리 채울 수 있는 것 — 소속(단과대학 · 학부(과) · 전공)과 학년."""
    p = profile or {}
    dept = " ".join(dict.fromkeys(x for x in (p.get("college"), p.get("department"), p.get("major")) if x))
    return {"department": dept, "grade": str(p["grade"]) if p.get("grade") else ""}


def resolve(own: Optional[dict], profile: Optional[dict], other: Optional[dict] = None,
            other_label: str = "") -> tuple[dict, Optional[str]]:
    """저장한 기본 정보 + 빈 칸은 다른 기능의 기본 정보 → 프로필 순으로 채운다. 반환 (기본 정보, 미리 채운 출처 또는 None)."""
    out = clean(own)
    other = clean(other)
    prof = from_profile(profile)
    src: Optional[str] = None
    for k in KEYS:
        if out[k]:
            continue
        if other[k]:
            out[k] = other[k]
            src = src or other_label or "other"
        elif prof.get(k):
            out[k] = prof[k]
            src = src or "profile"
    return out, src


def grade_text(g: str) -> str:
    g = (g or "").strip()
    return f"{g}학년" if g.isdigit() else g


def fmt_date(d: date) -> str:
    return f"{d.year}. {d.month}. {d.day}."


def lines(basic: dict, profile: Optional[dict], today: Optional[date] = None, *, contact: bool = True) -> list[str]:
    """초안 '1. 기본 정보' 줄들. 모르는 값은 `{{빈칸}}`. contact=False 면 연락처·이메일은 적었을 때만."""
    b = clean(basic)
    p = profile or {}
    grade = grade_text(b["grade"]) or (f"{p['grade']}학년" if p.get("grade") else "{{학년}}")
    out = [f"- 이름: {b['name'] or '{{이름}}'}",
           f"- 학번: {b['studentId'] or '{{학번}}'}",
           f"- 소속: {b['department'] or '{{소속}}'}",
           f"- 학년·학적: {grade} · {p.get('enrollmentStatus') or '{{학적}}'}"]
    if contact or b["phone"]:
        out.append(f"- 연락처: {b['phone'] or '{{연락처}}'}")
    if b["email"]:
        out.append(f"- 이메일: {b['email']}")
    out.append(f"- 작성일: {fmt_date(today or date.today())}")
    return out


def fill(text: str, basic: dict) -> str:
    """초안 글의 `{{이름}}`·`{{학번}}`·`{{연락처}}`·`{{이메일}}`·`{{소속}}` 빈칸을 적어 둔 값으로 — 이 PC 에서만."""
    b = clean(basic)
    for label, k in FILL.items():
        if b[k]:
            text = text.replace("{{" + label + "}}", b[k])
    return text
