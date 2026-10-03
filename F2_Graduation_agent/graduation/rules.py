"""졸업요건 룰셋 — 읽기·검사·자동 매칭·펼치기 (F2-R10~R17, C2 6절). 표준 라이브러리만.

룰셋 파일 (저장소 rulesets/*.json, 요구사항정의서 F2 6절 `RequirementRuleset` 을 조금 넓힘)
  kind="department"  학과(부)·전공 + 입학년도 범위(admissionYear ~ admissionYearTo) + 이수유형 하나
                     총 학점 · 최저 평점 · 영역(areas) · 세부 요건(checks) · 졸업인증(certifications) · 교과구분 매핑
                     값마다 근거(evidence)를 적는다 (F2-R12)
  kind="common"      대학 공통 조건 — 입학년도 구간(appliesFrom~appliesTo)에 맞으면 학과 룰셋에 **덧붙인다**
                     (예: 2023학년도 이후 교양 영역별 이수 조건)
영역의 과목 목록은 손으로 적지 않고 `coursesFrom: "전필"` 로 두면 교육과정검색 스냅숏에서 채운다 (F2-R16).

자동 매칭 순서 (C2 6절) — level
  user     내 수정본 (그 학과·전공·입학년도·이수유형에 한해 우선, F2-R13)
  exact    전공 코드 + 입학년도 범위 + 이수유형
  dept     학부 코드 + 입학년도 범위 + 이수유형 (학부 공통 기준)
  nearest  같은 학과(전공)의 가장 가까운 이전 연도 → 경고 + 판정 '확인 필요' (F2-R17)
  track    이수유형 기준이 없어 단일전공 기준을 씀 → 경고 + '확인 필요' (복수·부전공은 1차 범위 밖, F2 8절)
  none     없음 → 빈 템플릿 + '직접 입력하기' / '비슷한 학과에서 복사' (F2-R14, F2-S11)
"""
from __future__ import annotations

import copy
import json
import re
from typing import Any, Optional

from . import config as C
from . import curriculum

TRACKS = ("single", "double", "minor")
TRACK_LABEL = {"single": "단일전공", "double": "복수전공", "minor": "부전공"}
GPA_SCALES = (4.5, 4.3, 4.0)
CERT_STATES = ("done", "todo", "unknown")

# 전남대 교과구분 → 영역. 교육과정검색은 줄임말(전필), 학사정보시스템은 풀어 쓴 말일 수 있어 둘 다 둔다.
# 여기에 없는 구분(전기·교직·군사학 …)은 '미분류'로 모아 사용자에게 묻는다 (F2-R23).
DEFAULT_CATEGORY_MAP = {
    "교필": "ge_required", "교양필수": "ge_required",
    "교선": "ge_elective", "교양선택": "ge_elective", "교양": "ge_elective",
    "전필": "major_required", "전공필수": "major_required",
    "전선": "major_elective", "전공선택": "major_elective",
    "일선": "free", "일반선택": "free",
}

TEMPLATE_AREAS = [
    {"key": "ge_required", "label": "교양필수", "minCredits": 0, "overflowTo": "ge_elective", "coursesFrom": "교필", "evidence": ""},
    {"key": "ge_elective", "label": "교양선택", "minCredits": 0, "overflowTo": "free", "evidence": ""},
    {"key": "major_required", "label": "전공필수", "minCredits": 0, "overflowTo": "major_elective", "coursesFrom": "전필", "evidence": ""},
    {"key": "major_elective", "label": "전공선택", "minCredits": 0, "overflowTo": "free", "evidence": ""},
    {"key": "free", "label": "일반선택", "minCredits": 0, "evidence": "졸업학점에서 다른 영역을 뺀 나머지"},
]

LEVEL_LABEL = {"user": "내 수정본", "exact": "정확", "dept": "학부 공통", "nearest": "인접 연도", "track": "단일전공 기준", "none": "없음"}


class Invalid(ValueError):
    pass


# ── 파일 읽기 ───────────────────────────────────────────────

_cache: dict[str, Any] = {"sig": None, "items": []}


def _bundled() -> list[dict]:
    """저장소의 룰셋 전부 (파일이 바뀌면 다시 읽는다)."""
    files = sorted(C.BUNDLED_RULESETS.glob("*.json")) if C.BUNDLED_RULESETS.exists() else []
    sig = tuple((str(p), p.stat().st_mtime) for p in files)
    if sig != _cache["sig"]:
        items = []
        for p in files:
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                continue
            doc.setdefault("kind", "department")
            doc["_file"] = p.name
            items.append(doc)
        _cache.update(sig=sig, items=items)
    return _cache["items"]


def departments() -> list[dict]:
    return [r for r in _bundled() if r.get("kind") == "department"]


def commons() -> list[dict]:
    return [r for r in _bundled() if r.get("kind") == "common"]


def by_id(rid: str) -> Optional[dict]:
    return next((copy.deepcopy(r) for r in departments() if r.get("id") == rid), None)


def listing() -> list[dict]:
    """'비슷한 학과에서 복사'용 목록."""
    return [{"id": r["id"], "department": r.get("department"), "major": r.get("major"), "deptCode": r.get("deptCode"),
             "majorCode": r.get("majorCode"), "admissionYear": r.get("admissionYear"), "admissionYearTo": r.get("admissionYearTo"),
             "track": r.get("track", "single"), "totalCredits": r.get("totalCredits"), "label": year_label(r)}
            for r in departments()]


# ── 표시 ────────────────────────────────────────────────────

def year_label(r: dict) -> str:
    a, b = r.get("admissionYear"), r.get("admissionYearTo")
    if a and b and b != a:
        return f"{a}~{b}"
    return f"{a}" if a else "연도 미상"


def basis_label(r: Optional[dict]) -> str:
    """'2021~2022 입학 · 인공지능학부 기준' (C2 6절 화면 표시)"""
    if not r:
        return "기준 없음"
    who = r.get("major") or r.get("department") or "학과"
    return f"{year_label(r)} 입학 · {who} 기준"


def target_key(dept: Optional[str], major: Optional[str], year: Optional[int], track: str) -> str:
    return f"{dept or ''}|{major or ''}|{year or ''}|{track}"


# ── 자동 매칭 (C2 6절) ──────────────────────────────────────

def _in_range(r: dict, year: int) -> bool:
    a = r.get("admissionYear")
    b = r.get("admissionYearTo") or a
    return bool(a) and a <= year <= b


def match(dept: Optional[str], major: Optional[str], year: Optional[int], track: str = "single",
          user: Optional[dict] = None) -> dict:
    """반환 {ruleset, level, warnings[]}. user = 이 대상(학과·전공·연도·이수유형)에 저장된 내 수정본."""
    track = track if track in TRACKS else "single"
    if user is not None:
        return {"ruleset": user, "level": "user", "warnings": []}
    if not dept or not year:
        return {"ruleset": None, "level": "none", "warnings": ["프로필에 학과·입학년도가 없어 기준을 고를 수 없습니다"]}

    def find(trk: str) -> tuple[Optional[dict], str]:
        rs = [r for r in departments() if r.get("track", "single") == trk]
        for r in rs:                                                     # ① 전공 + 연도 + 이수유형
            if major and r.get("majorCode") == major and _in_range(r, year):
                return r, "exact"
        for r in rs:                                                     # ② 학부 공통 + 연도
            if r.get("deptCode") == dept and not r.get("majorCode") and _in_range(r, year):
                return r, "exact" if not major else "dept"
        same = [r for r in rs if (major and r.get("majorCode") == major)
                or (r.get("deptCode") == dept and not r.get("majorCode"))]
        earlier = [r for r in same if (r.get("admissionYearTo") or r.get("admissionYear") or 9999) < year]
        if earlier:                                                      # ③ 가장 가까운 이전 연도 (전공 기준 우선)
            best = max(earlier, key=lambda r: ((r.get("admissionYearTo") or r["admissionYear"]), bool(r.get("majorCode"))))
            return best, "nearest"
        return None, "none"

    r, level = find(track)
    warnings: list[str] = []
    if r is None and track != "single":
        r, lv = find("single")
        if r is not None:
            level = "track"
            warnings.append(f"{TRACK_LABEL[track]} 기준이 없어 {TRACK_LABEL['single']} 기준으로 계산합니다 — "
                            f"{TRACK_LABEL[track]} 학점은 따로 확인하세요")
            if lv == "nearest":
                warnings.append(f"{year}학년도 입학 기준이 없어 가장 가까운 {year_label(r)} 기준을 씁니다")
    elif level == "nearest":
        warnings.append(f"{year}학년도 입학 기준이 없어 가장 가까운 해({year_label(r)}) 기준으로 계산 중입니다 — "
                        "기준 보기에서 확인하고 저장하면 이 경고가 사라집니다")
    if r is None:
        return {"ruleset": None, "level": "none", "warnings": []}
    return {"ruleset": copy.deepcopy(r), "level": level, "warnings": warnings}


def template(profile: Optional[dict] = None, track: str = "single") -> dict:
    """룰셋 없음 → 빈 템플릿 (F2-R14). 전남대 교과구분 매핑과 영역 틀만 채워 둔다."""
    p = profile or {}
    return {
        "id": None, "kind": "department", "university": "전남대학교",
        "collegeCode": p.get("collegeCode"), "college": p.get("college"),
        "deptCode": p.get("deptCode"), "department": p.get("department"),
        "majorCode": p.get("majorCode"), "major": p.get("major"),
        "admissionYear": p.get("admissionYear"), "admissionYearTo": p.get("admissionYear"), "track": track,
        "totalCredits": None, "totalEvidence": "", "minGpa": None, "minGpaEvidence": "",
        "areas": copy.deepcopy(TEMPLATE_AREAS), "checks": [], "certifications": [],
        "categoryMap": dict(DEFAULT_CATEGORY_MAP), "notes": [],
        "source": {"docName": "직접 입력", "url": "", "checkedAt": None}, "version": 0, "verified": False,
    }


# ── 펼치기 — 계산에 쓰는 최종 룰셋 ───────────────────────────

def resolve(ruleset: Optional[dict], profile: Optional[dict], user_map: Optional[dict] = None) -> Optional[dict]:
    """과목 목록(coursesFrom → 교육과정 스냅숏) · 대학 공통 조건 · 교과구분 매핑(내가 지정한 것 우선)을 붙인다."""
    if ruleset is None:
        return None
    r = copy.deepcopy(ruleset)
    p = profile or {}
    year = p.get("admissionYear") or r.get("admissionYear")
    dept, major = p.get("deptCode") or r.get("deptCode"), p.get("majorCode") or r.get("majorCode")
    cur_meta = {"sources": [], "missing": [], "year": year}
    for a in r.get("areas", []):
        if a.get("courses") is None and a.get("coursesFrom"):
            lst, meta = curriculum.courses_for(dept, major, year, a["coursesFrom"])
            a["courses"] = [{"code": c["code"], "name": c["name"], "credits": c["credits"], "grade": c.get("grade"),
                             "term": c.get("term")} for c in lst]
            a["coursesSource"] = "curriculum"
            cur_meta["sources"] = meta["sources"] or cur_meta["sources"]
            cur_meta["missing"] = sorted(set(cur_meta["missing"]) | set(meta["missing"]))
        elif a.get("courses") is not None:
            a["coursesSource"] = a.get("coursesSource") or "ruleset"
    r["curriculum"] = cur_meta
    checks = list(r.get("checks") or [])
    notes = list(r.get("notes") or [])
    for c in commons():
        if c.get("university") and r.get("university") and c["university"] != r["university"]:
            continue
        lo, hi = c.get("appliesFrom") or 0, c.get("appliesTo") or 9999
        if year and lo <= year <= hi:
            have = {x["key"] for x in checks}
            checks += [{**x, "common": c.get("id")} for x in c.get("checks", []) if x["key"] not in have]
            notes += c.get("notes", [])
            r.setdefault("commonSources", []).append({"id": c.get("id"), **(c.get("source") or {})})
    r["checks"] = checks
    r["notes"] = notes
    cmap = dict(r.get("categoryMap") or DEFAULT_CATEGORY_MAP)
    for k, v in (user_map or {}).items():
        if v is None:
            cmap.pop(k, None)
        else:
            cmap[k] = v
    r["categoryMap"] = cmap
    return r


# ── 검사 (PUT 으로 받은 내 수정본) ─────────────────────────────

_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")


def _num(v: Any, lo: float, hi: float, what: str, allow_none: bool = False) -> Optional[float]:
    if v is None and allow_none:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise Invalid(f"{what}: 숫자여야 합니다")
    if not lo <= v <= hi:
        raise Invalid(f"{what}: {lo}~{hi} 사이여야 합니다")
    return int(v) if float(v).is_integer() else float(v)


def _text(v: Any, n: int, what: str) -> str:
    if v is None:
        return ""
    if not isinstance(v, str):
        raise Invalid(f"{what}: 글자여야 합니다")
    v = v.strip()
    if len(v) > n:
        raise Invalid(f"{what}: {n}자 이내로 적어 주세요")
    return v


def _courses(v: Any, what: str) -> Optional[list]:
    if v is None:
        return None
    if not isinstance(v, list) or len(v) > 200:
        raise Invalid(f"{what}: 과목 목록은 200개 이내입니다")
    out = []
    for c in v:
        if not isinstance(c, dict) or not (c.get("name") or c.get("code")):
            raise Invalid(f"{what}: 과목마다 이름이나 학수번호가 있어야 합니다")
        out.append({"code": (_text(c.get("code"), 20, "학수번호") or None) and str(c["code"]).strip().upper(),
                    "name": _text(c.get("name"), 80, "과목명") or str(c.get("code")),
                    "credits": _num(c.get("credits", 0) or 0, 0, 30, "과목 학점")})
    return out


def validate(doc: Any) -> dict:
    """내 수정본으로 저장할 룰셋을 검사하고 깨끗한 모양으로 돌려준다. 틀리면 Invalid."""
    if not isinstance(doc, dict):
        raise Invalid("룰셋은 JSON 객체입니다")
    areas_in = doc.get("areas")
    if not isinstance(areas_in, list) or not 1 <= len(areas_in) <= 20:
        raise Invalid("영역(areas)은 1~20개입니다")
    areas, keys = [], set()
    for a in areas_in:
        if not isinstance(a, dict) or not _KEY.match(str(a.get("key", ""))):
            raise Invalid("영역 key 는 영문 소문자·숫자·_ 입니다 (예: major_required)")
        if a["key"] in keys:
            raise Invalid(f"영역 key 가 겹칩니다: {a['key']}")
        keys.add(a["key"])
        label = _text(a.get("label"), 20, "영역 이름") or a["key"]
        item = {"key": a["key"], "label": label,
                "minCredits": _num(a.get("minCredits", 0) or 0, 0, 200, f"{label} 최소 학점"),
                "evidence": _text(a.get("evidence"), 300, f"{label} 근거")}
        if a.get("overflowTo"):
            item["overflowTo"] = str(a["overflowTo"])
        if a.get("coursesFrom"):
            item["coursesFrom"] = _text(a.get("coursesFrom"), 10, "교과구분")
        courses = _courses(a.get("courses"), f"{label} 과목") if a.get("coursesSource") != "curriculum" else None
        if courses is not None:
            item["courses"] = courses
            item.pop("coursesFrom", None)
        areas.append(item)
    for a in areas:
        if a.get("overflowTo") and (a["overflowTo"] not in keys or a["overflowTo"] == a["key"]):
            raise Invalid(f"{a['label']}: 초과분을 넘길 영역이 없습니다 ({a['overflowTo']})")
    certs, ckeys = [], set()
    for c in doc.get("certifications") or []:
        if not isinstance(c, dict) or not _KEY.match(str(c.get("key", ""))):
            raise Invalid("졸업인증 key 는 영문 소문자·숫자·_ 입니다")
        if c["key"] in ckeys:
            raise Invalid(f"졸업인증 key 가 겹칩니다: {c['key']}")
        ckeys.add(c["key"])
        certs.append({"key": c["key"], "label": _text(c.get("label"), 30, "인증 이름") or c["key"],
                      "detail": _text(c.get("detail"), 300, "인증 설명"), "required": bool(c.get("required", True)),
                      "evidence": _text(c.get("evidence"), 300, "인증 근거"),
                      "hintCourses": [str(x)[:40] for x in (c.get("hintCourses") or [])][:10]})
    if len(certs) > 20:
        raise Invalid("졸업인증은 20개 이내입니다")
    checks = []
    for c in doc.get("checks") or []:
        if c.get("common"):
            continue                           # 대학 공통 조건은 펼칠 때 다시 붙는다 — 저장하지 않는다
        if not isinstance(c, dict) or not _KEY.match(str(c.get("key", ""))):
            raise Invalid("세부 요건 key 는 영문 소문자·숫자·_ 입니다")
        match_ = [str(x).strip()[:30] for x in (c.get("match") or []) if str(x).strip()]
        if not match_:
            raise Invalid(f"세부 요건 {c['key']}: 찾을 말(match)이 없습니다")
        checks.append({"key": c["key"], "label": _text(c.get("label"), 30, "세부 요건 이름") or c["key"],
                       "minCredits": _num(c.get("minCredits", 0) or 0, 0, 200, "세부 요건 학점"),
                       "field": c.get("field") if c.get("field") in ("geArea", "rawCategory", "name") else "geArea",
                       "match": match_, "approximate": bool(c.get("approximate")),
                       "evidence": _text(c.get("evidence"), 300, "세부 요건 근거")})
    cmap = {}
    for k, v in (doc.get("categoryMap") or {}).items():
        if v not in keys:
            raise Invalid(f"교과구분 '{k}' 을(를) 없는 영역({v})에 연결했습니다")
        cmap[_text(k, 20, "교과구분")] = v
    g = doc.get("minGpa")
    if g is not None:
        if not isinstance(g, dict) or float(g.get("scale") or 0) not in GPA_SCALES:
            raise Invalid("최저 평점은 {value, scale(4.5·4.3·4.0)} 입니다")
        g = {"value": _num(g.get("value"), 0, float(g["scale"]), "최저 평점"), "scale": float(g["scale"])}
    track = doc.get("track") if doc.get("track") in TRACKS else "single"
    return {
        "id": doc.get("id"), "kind": "department", "university": _text(doc.get("university"), 40, "대학") or "전남대학교",
        "collegeCode": doc.get("collegeCode"), "college": doc.get("college"),
        "deptCode": doc.get("deptCode"), "department": doc.get("department"),
        "majorCode": doc.get("majorCode"), "major": doc.get("major"),
        "admissionYear": doc.get("admissionYear"), "admissionYearTo": doc.get("admissionYearTo"), "track": track,
        "totalCredits": _num(doc.get("totalCredits"), 1, 300, "졸업 학점", allow_none=True),
        "totalEvidence": _text(doc.get("totalEvidence"), 300, "졸업 학점 근거"),
        "minGpa": g, "minGpaEvidence": _text(doc.get("minGpaEvidence"), 300, "최저 평점 근거"),
        "areas": areas, "checks": checks, "certifications": certs, "categoryMap": cmap,
        "notes": [str(x)[:300] for x in (doc.get("notes") or [])][:20],
        "source": doc.get("source") if isinstance(doc.get("source"), dict) else {},
        "version": doc.get("version") or 0, "verified": bool(doc.get("verified")),
    }
