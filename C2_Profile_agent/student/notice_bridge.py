"""F11(notice_agent) 로 프로필 넘기기 — C2 프로필 → notice_agent/data/profile.json (scripts/schemas.py `Profile` 모양).

notice_agent 는 아직 자기 profile.json 을 읽는다. F11 을 대시보드에 붙일 때 C2 를 직접 읽게 바꾸고, 그 전까지는
    python -m student export-notice
로 같은 값을 넘긴다. 파일에 있던 C2 에 없는 값(gpa_percent·nationality 등)은 그대로 둔다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from . import config as C

NOTICE_PROFILE = C.PROJECT_ROOT / "notice_agent" / "data" / "profile.json"
_FLAG = {"disability": "disability", "veteranFamily": "veteran_family", "multiChild": "multi_child",
         "singleParent": "single_parent", "basicLivelihood": "basic_livelihood"}
_DRAFT = {"careerGoal": "career_goal", "activities": "activities", "hardship": "hardship"}


def to_notice(p: dict) -> dict:
    """C2 profile(화면 모양) → notice_agent Profile 필드. 값이 없는 항목은 넣지 않는다."""
    out = {
        "grade": p.get("grade"), "semesters_completed": p.get("semestersCompleted"),
        "enrollment_status": p.get("enrollmentStatus"), "college": p.get("college"),
        "department": p.get("department"), "major": p.get("major"),
        "gpa": p.get("gpa"), "last_semester_gpa": p.get("lastSemesterGpa"),
        "earned_credits": p.get("earnedCredits"), "last_semester_credits": p.get("lastSemesterCredits"),
        "income_bracket": p.get("incomeBracket"), "residence_region": p.get("residenceRegion"),
        "high_school_region": p.get("highSchoolRegion"), "interests": p.get("interests") or None,
        "flags": {_FLAG[k]: v for k, v in (p.get("flags") or {}).items()} or None,
        "draft_context": {_DRAFT[k]: v for k, v in (p.get("draftContext") or {}).items()} or None,
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
    path.write_text(json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
