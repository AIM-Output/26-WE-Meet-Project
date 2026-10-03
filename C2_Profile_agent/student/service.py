"""프로필 읽기·쓰기 — 화면이 받는 모양, 검사, '자동/내가 입력' 구분, 다른 기능에 넘기는 모양. 표준 라이브러리만.

쓰기 규칙 (C2-R05)
  by="user"  사용자가 고친 값. 자동으로 채워졌던 항목을 고치면 edited=1 → 화면에 '수정함' 칩
  by="auto"  학사정보시스템에서 가져온 값. **사용자가 입력·수정한 항목은 건드리지 않는다**(skipped 로 알려 준다)
소속은 학과 마스터에서 고른 코드만 받는다(C2-D1). 이름은 마스터에서 붙이고, 옛 코드(폐지·개편)도 마스터에 남아 있어 깨지지 않는다.
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from . import master
from .schema import (AFFILIATION, ENROLLMENT, FIELDS, FORBIDDEN, IMPORTABLE, REGIONS, REQUIRED, SENSITIVE, Invalid)
from .store import dumps, get_meta, loads, now_iso, rows, set_meta

AFFIL_KEY = "affiliation"


# ── 읽기 ────────────────────────────────────────────────────

def get(con: sqlite3.Connection) -> dict:
    """GET /api/profile — 항목 값 + 항목별 출처(자동/내가 입력) + 필수 항목 채움 여부."""
    rs = rows(con)
    prof: dict[str, Any] = {k: None for k in (*AFFILIATION, "college", "department", "major", "deptPath", *FIELDS)}
    prof["affiliationRetired"] = False
    aff = loads(rs[AFFIL_KEY]["value"]) if AFFIL_KEY in rs else None
    if aff:
        e = master.find(aff.get("deptCode"), aff.get("majorCode"))
        names = e or aff                                   # 마스터에서 못 찾으면 저장할 때의 이름
        prof.update(collegeCode=aff.get("collegeCode"), deptCode=aff.get("deptCode"), majorCode=aff.get("majorCode"),
                    college=names.get("college"), department=names.get("department"), major=names.get("major"),
                    affiliationRetired=bool(e and e.get("retired")))
        prof["deptPath"] = " › ".join(x for x in (prof["college"], prof["department"], prof["major"]) if x)
    for k in FIELDS:
        if k in rs:
            prof[k] = loads(rs[k]["value"])
    filled = {("deptCode" if k == AFFIL_KEY else k): r["filled_by"] for k, r in rs.items()}
    edited = [("deptCode" if k == AFFIL_KEY else k) for k, r in rs.items() if r["edited"]]
    missing = [k for k in REQUIRED if prof.get(k) in (None, "")]
    return {
        "exists": bool(rs),
        "profile": prof,
        "filledBy": filled,
        "edited": edited,
        "complete": not missing,
        "missing": missing,
        "onboardingSkipped": get_meta(con, "onboarding_skipped") == "1",
        "updatedAt": get_meta(con, "updated_at"),
        "importedAt": get_meta(con, "imported_at"),
    }


def matching_view(con: sqlite3.Connection) -> Optional[dict]:
    """다른 기능이 쓰는 모양. F1 대상 판정(audience.py)이 grade·enrollment·college·department·major 를 읽는다."""
    doc = get(con)
    if not doc["exists"]:
        return None
    p = doc["profile"]
    return {
        "grade": p["grade"], "enrollment": p["enrollmentStatus"],
        "college": p["college"], "department": p["department"], "major": p["major"],
        "collegeCode": p["collegeCode"], "deptCode": p["deptCode"], "majorCode": p["majorCode"],
        "admissionYear": p["admissionYear"], "track": p["track"],
        "gpa": p["gpa"], "earnedCredits": p["earnedCredits"], "semestersCompleted": p["semestersCompleted"],
        "lastSemesterGpa": p["lastSemesterGpa"],       # F3 학사경고 안내 (F3-R40)
        "updatedAt": doc["updatedAt"],
    }


# ── 쓰기 ────────────────────────────────────────────────────

def _put(con: sqlite3.Connection, key: str, value: Any, by: str) -> str:
    """한 항목 저장. 반환: changed / same / skipped(자동값이 사용자 값을 덮으려 함)."""
    r = con.execute("SELECT * FROM fields WHERE key = ?", (key,)).fetchone()
    if by == "auto" and r is not None and r["filled_by"] == "user":
        return "skipped"
    if value is None:
        if r is None:
            return "same"
        con.execute("DELETE FROM fields WHERE key = ?", (key,))
        return "changed"
    if r is not None and loads(r["value"]) == value:
        return "same"
    edited = int(by == "user" and r is not None and (r["filled_by"] == "auto" or bool(r["edited"])))
    con.execute(
        "INSERT INTO fields(key, value, filled_by, edited, updated_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, filled_by = excluded.filled_by, "
        "edited = excluded.edited, updated_at = excluded.updated_at",
        (key, dumps(value), by, edited, now_iso()))
    return "changed"


def _affiliation(v: Any) -> Optional[dict]:
    if v is None:
        return None
    if not isinstance(v, dict) or not v.get("deptCode"):
        raise Invalid("소속은 {deptCode, majorCode} 로 보냅니다")
    e = master.find(str(v["deptCode"]), (str(v["majorCode"]) if v.get("majorCode") else None))
    if e is None:
        raise Invalid("학과 목록에 없는 코드입니다 — 학과 선택기에서 골라 주세요")
    return {"collegeCode": e["collegeCode"], "deptCode": e["deptCode"], "majorCode": e["majorCode"],
            "college": e["college"], "department": e["department"], "major": e["major"]}


def patch(con: sqlite3.Connection, data: dict, by: str = "user") -> dict:
    """PATCH /api/profile. 값이 null 이면 그 항목을 지운다. 알 수 없는 항목·식별정보는 거절한다."""
    if not isinstance(data, dict):
        raise Invalid("JSON 객체를 보내 주세요")
    bad = [k for k in data if k in FORBIDDEN]
    if bad:
        raise Invalid("이름·학번 같은 식별정보는 저장하지 않습니다 (C2-D5)")
    work: list[tuple[str, Any]] = []
    for k, v in data.items():
        if k == "onboardingSkipped":
            continue
        if k == AFFIL_KEY:
            work.append((AFFIL_KEY, _affiliation(v)))
        elif k in FIELDS:
            try:
                work.append((k, None if v is None else FIELDS[k][1](v)))
            except Invalid as e:
                raise Invalid(f"{FIELDS[k][3]}: {e}") from e
        else:
            raise Invalid(f"알 수 없는 항목입니다: {k}")
    result = {"changed": [], "skipped": []}
    for k, v in work:
        st = _put(con, k, v, by)
        name = "deptCode" if k == AFFIL_KEY else k
        if st == "changed":
            result["changed"].append(name)
        elif st == "skipped":
            result["skipped"].append(name)
    if "onboardingSkipped" in data:
        set_meta(con, "onboarding_skipped", "1" if data["onboardingSkipped"] else None)
    if result["changed"]:
        set_meta(con, "updated_at", now_iso())
    return result


def delete_all(con: sqlite3.Connection) -> None:
    """'내 정보 전부 지우기' (C2-S07)."""
    con.execute("DELETE FROM fields")
    con.execute("DELETE FROM meta WHERE key IN ('imported_at', 'onboarding_skipped')")
    set_meta(con, "updated_at", now_iso())


def delete_sensitive(con: sqlite3.Connection) -> None:
    """장학용 민감정보만 지우기 (C2-R07)."""
    con.execute(f"DELETE FROM fields WHERE key IN ({','.join('?' * len(SENSITIVE))})", SENSITIVE)
    set_meta(con, "updated_at", now_iso())


# ── 학사정보시스템 가져오기 결과 반영 (C2-R04) ───────────────

_IMPORT_MAP = {"grade": "grade", "enrollment_status": "enrollmentStatus", "gpa": "gpa",
               "earned_credits": "earnedCredits", "semesters_completed": "semestersCompleted",
               "last_semester_credits": "lastSemesterCredits"}


def apply_import(con: sqlite3.Connection, fetched: dict) -> dict:
    """hakstd.py 가 읽어 온 값 → 자동(auto)으로 저장. 사용자가 고친 항목은 건너뛴다.
    소속이 비어 있으면 '주전공 : AI융합대학 / 인공지능학부' 를 학과 마스터에서 찾아 채운다(전공은 사용자가 고른다)."""
    data: dict[str, Any] = {}
    invalid: list[str] = []
    for src, key in _IMPORT_MAP.items():
        v = fetched.get(src)
        if v is None:
            continue
        if key == "enrollmentStatus" and v not in ENROLLMENT:
            invalid.append(key)                     # '졸업'·'제적' 등은 프로필 선택지가 아니다
            continue
        try:
            data[key] = FIELDS[key][1](v)
        except Invalid:
            invalid.append(key)
    result = patch(con, data, by="auto") if data else {"changed": [], "skipped": []}
    matched = None
    rs = rows(con)
    if AFFIL_KEY not in rs or rs[AFFIL_KEY]["filled_by"] == "auto":
        e = master.find_by_names(fetched.get("college"), fetched.get("department"))
        if e is not None:
            aff = {"collegeCode": e["collegeCode"], "deptCode": e["deptCode"], "majorCode": e["majorCode"],
                   "college": e["college"], "department": e["department"], "major": e["major"]}
            cur = loads(rs[AFFIL_KEY]["value"]) if AFFIL_KEY in rs else None
            if not (cur and cur.get("deptCode") == aff["deptCode"]):   # 같은 학과면 사용자가 고른 전공을 두고 간다
                if _put(con, AFFIL_KEY, aff, "auto") == "changed":
                    result["changed"].append("deptCode")
                    set_meta(con, "updated_at", now_iso())
            matched = e["path"]
    elif fetched.get("department"):
        result["skipped"].append("deptCode")
    now = now_iso()
    set_meta(con, "imported_at", now)
    return {**result, "invalid": invalid, "affiliationFound": matched,
            "found": sorted(k for k in IMPORTABLE if k in data), "importedAt": now}


# ── 옛 저장 방식에서 옮기기 ──────────────────────────────────

def migrate_legacy(con: sqlite3.Connection, legacy: dict) -> dict:
    """브라우저 저장(univus:profile)·옛 /api/profile(univus.db kv) 모양 → 이 저장소. 이미 프로필이 있으면 하지 않는다."""
    if rows(con) or not isinstance(legacy, dict):
        return {"migrated": False}
    auto = set(legacy.get("auto") or [])
    edited = set(legacy.get("edited") or [])
    pairs = {"admissionYear": legacy.get("admissionYear"), "track": legacy.get("track"),
             "grade": legacy.get("grade"), "enrollmentStatus": legacy.get("enrollment") or legacy.get("enrollmentStatus"),
             "earnedCredits": legacy.get("credits"), "semestersCompleted": legacy.get("semesters")}
    g = legacy.get("gpa")
    if isinstance(g, (int, float)):
        pairs["gpa"] = {"value": g, "scale": 4.5, "basis": "전체"}
    elif isinstance(g, dict):
        pairs["gpa"] = g
    sens = legacy.get("sensitive") or {}
    try:
        pairs["incomeBracket"] = int(str(sens.get("income", "")).strip()) if str(sens.get("income", "")).strip() else None
    except ValueError:
        pass
    for src, key in (("region", "residenceRegion"), ("school", "highSchoolRegion")):
        v = str(sens.get(src) or "").strip()
        if v in REGIONS:
            pairs[key] = v
    user, auto_d, dropped = {}, {}, []
    alias = {"enrollmentStatus": "enrollment", "earnedCredits": "credits", "semestersCompleted": "semesters"}
    for k, v in pairs.items():
        if v is None:
            continue
        try:
            v = FIELDS[k][1](v)
        except Invalid:
            dropped.append(k)
            continue
        src = alias.get(k, k)
        (auto_d if src in auto and src not in edited else user)[k] = v
    e = master.find(legacy.get("deptCode"), legacy.get("majorCode")) if legacy.get("deptCode") else None
    if e is None:
        e = master.by_code(legacy.get("majorCode") or legacy.get("deptCode"))
    if e is None:
        e = master.find_by_names(legacy.get("college"), legacy.get("department"))
    if e is not None:
        user[AFFIL_KEY] = {"deptCode": e["deptCode"], "majorCode": e["majorCode"]}
    elif legacy.get("deptCode"):
        dropped.append("deptCode")
    if user:
        patch(con, user, by="user")
    if auto_d:
        patch(con, auto_d, by="auto")
    if legacy.get("onboardingSkipped"):
        set_meta(con, "onboarding_skipped", "1")
    return {"migrated": bool(user or auto_d), "dropped": dropped}
