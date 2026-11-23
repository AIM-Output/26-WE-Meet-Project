"""F11(notice_agent) 로 프로필 넘기기 — C2 프로필 → notice_agent/data/profile.json (scripts/schemas.py `Profile` 모양).

notice_agent 는 아직 자기 profile.json 을 읽는다. F11 을 대시보드에 붙일 때 C2 를 직접 읽게 바꾸고, 그 전까지는
    python -m student export-notice
로 같은 값을 넘긴다. 파일에 있던 C2 에 없는 값(gpa_percent·nationality 등)은 그대로 둔다.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

from . import config as C

NOTICE_PROFILE = C.PROJECT_ROOT / "notice_agent" / "data" / "profile.json"
_FLAG = {"disability": "disability", "veteranFamily": "veteran_family", "multiChild": "multi_child",
         "singleParent": "single_parent", "basicLivelihood": "basic_livelihood"}
# draft_context(초안 재료)는 넘기지 않는다 — C2 의 draftContext 항목을 2026-11-19 신청서 초안 폐기로 뺐다


def _interests(v) -> Optional[list]:
    """C2 관심사({tags, keywords, exclude} — F12) → notice_agent 의 글자 목록(태그 + 키워드)."""
    if isinstance(v, dict):
        v = [*(v.get("tags") or []), *(v.get("keywords") or [])]
    return list(v) if v else None


def to_notice(p: dict) -> dict:
    """C2 profile(화면 모양) → notice_agent Profile 필드. 값이 없는 항목은 넣지 않는다."""
    out = {
        "grade": p.get("grade"), "semesters_completed": p.get("semestersCompleted"),
        "enrollment_status": p.get("enrollmentStatus"), "college": p.get("college"),
        "department": p.get("department"), "major": p.get("major"),
        "gpa": p.get("gpa"), "last_semester_gpa": p.get("lastSemesterGpa"),
        "earned_credits": p.get("earnedCredits"), "last_semester_credits": p.get("lastSemesterCredits"),
        "income_bracket": p.get("incomeBracket"), "residence_region": p.get("residenceRegion"),
        "high_school_region": p.get("highSchoolRegion"), "interests": _interests(p.get("interests")),
        "flags": {_FLAG[k]: v for k, v in (p.get("flags") or {}).items()} or None,
    }
    if p.get("department") and re.search(r"공학|인공지능|컴퓨터|소프트웨어|전자|기계", p["department"] + (p.get("major") or "")):
        out["field_group"] = "공학계열"
    return {k: v for k, v in out.items() if v is not None}


def export(profile: dict, path: Optional[Path] = None) -> Path:
    path = path or NOTICE_PROFILE
    base = {}
    if path.exists():
        try:
            base = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            base = {}
    base.update(to_notice(profile))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")             # 쓰다 죽어도 원래 파일은 온전하게 — 다 쓴 뒤 바꿔 끼운다
    tmp.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path
