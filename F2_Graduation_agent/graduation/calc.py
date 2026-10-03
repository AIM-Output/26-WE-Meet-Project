"""졸업요건 계산기 — 순수 함수 하나 (요구사항정의서 F2 5절). 표준 라이브러리만, LLM 없음 (F2-R29).

    calculate(courses, ruleset, certs, gpa, assumptions=None) → GraduationStatus

입력
  courses     [{id, year, semester, code, name, credits, grade, rawCategory, geArea, status, source,
                areaOverride(사용자가 고른 영역|None), excludedByUser(bool)}]
  ruleset     rules.resolve() 로 펼친 룰셋 (없으면 None — 학점 합계만 낸다)
  certs       {key: {state: done|todo|unknown, memo}}  사용자 체크 (F2-R41)
  gpa         {value, scale} — 학사시스템 평점 그대로 (⑧ 임의 환산 금지)
  assumptions {areas: {영역키: 학점}, courses: [학수번호 …]}  가정 계산 (F2-R50·R51) — 가짜 과목으로 더해 같은 계산을 한 번 더

단계 (5절 표)
  ① 유효 과목  F·NP·U·W 와 포기·취소·철회 과목, 사용자가 뺀 과목 제외
  ② 재수강     같은 학수번호(없으면 과목명+학점)가 여러 번이면 성적이 가장 높은 1건만 (같으면 나중 것)
  ③ 영역 배정  사용자 지정 > 교과구분 매핑. 못 하면 미분류 (F2-R23)
  ④ 합산       영역별 배정 학점
  ⑤ 초과 이월  overflowTo 가 있으면 초과분을 넘긴다 — 1회만, 연쇄 없음 (F2-R26)
  ⑥ 부족       max(0, 기준 − 취득). 과목 목록이 있는 영역(전공필수)은 남은 과목도 (F2-R25)
  ⑦ 총계       유효 과목 학점 합(영역과 무관). '실제로 더 들어야 하는 학점' = max(총 부족, 영역 부족 합)
  ⑧ 평점       비교만. 척도가 다르면 비교하지 않는다
  ⑨ 인증       사용자 체크 그대로. required 인데 '모름'이면 확인 필요
  ⑩ 판정       기준 자체가 불확실(인접 연도·미분류·과목 목록 없음) → 확인 필요 / 부족이 있으면 부족 /
               모르는 것(인증·평점·세부 요건)이 남으면 확인 필요 / 전부 채우면 충족
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from . import config as C

SEM_ORDER = {"1": 1, "여름": 2, "2": 3, "겨울": 4}


def _norm(s: Optional[str]) -> str:
    return re.sub(r"[\s·ㆍ\-_()\[\]]", "", (s or "")).upper()


def _grade(g: Optional[str]) -> str:
    return (g or "").strip().upper().replace(" ", "")


def course_key(c: dict) -> str:
    """재수강·중복을 가리는 열쇠 — 학수번호, 없으면 과목명+학점 (5절 ②)."""
    code = _norm(c.get("code"))
    return f"code:{code}" if code else f"name:{_norm(c.get('name'))}:{float(c.get('credits') or 0):g}"


def _when(c: dict) -> tuple:
    return (int(c.get("year") or 0), SEM_ORDER.get(str(c.get("semester") or ""), 0))


def exclusion(c: dict) -> Optional[str]:
    """① 계산에서 빠지는 이유. 없으면 None."""
    if c.get("excludedByUser"):
        return "직접 제외함"
    g = _grade(c.get("grade"))
    if g in C.FAIL_GRADES:
        return f"취득하지 못한 성적({g})"
    st = c.get("status") or ""
    for w in C.DROP_WORDS:
        if w in st:
            return f"교과목상태 '{st}'"
    return None


def _map_area(c: dict, cmap: dict, keys: set) -> tuple[Optional[str], str]:
    """③ 영역과 그 출처(user|map|none)."""
    ov = c.get("areaOverride")
    if ov and ov in keys:
        return ov, "user"
    raw = (c.get("rawCategory") or "").strip()
    if raw:
        a = cmap.get(raw) or cmap.get(raw.replace(" ", ""))
        if a in keys:
            return a, "map"
    return None, "none"


def _synthetic(assumptions: Optional[dict], ruleset: Optional[dict]) -> list[dict]:
    """가정 계산 — 영역별 가정 학점 · 남은 과목 체크를 가짜 과목으로 만든다 (저장하지 않는다)."""
    if not assumptions or not ruleset:
        return []
    out: list[dict] = []
    area_keys = {a["key"] for a in ruleset.get("areas", [])}
    for key, cr in (assumptions.get("areas") or {}).items():
        try:
            cr = float(cr)
        except (TypeError, ValueError):
            continue
        if key in area_keys and cr > 0:
            out.append({"id": f"wi:area:{key}", "name": f"가정 +{cr:g}학점", "credits": cr, "grade": "P", "code": None,
                        "year": 9999, "semester": "1", "areaOverride": key, "source": "whatif"})
    wanted = {_norm(x) for x in (assumptions.get("courses") or [])}
    for a in ruleset.get("areas", []):
        for rc in a.get("courses") or []:
            if _norm(rc.get("code")) in wanted or _norm(rc.get("name")) in wanted:
                out.append({"id": f"wi:course:{rc.get('code') or rc.get('name')}", "name": rc.get("name"),
                            "code": rc.get("code"), "credits": rc.get("credits") or 0, "grade": "P", "year": 9999,
                            "semester": "1", "areaOverride": a["key"], "source": "whatif"})
    return out


def calculate(courses: list[dict], ruleset: Optional[dict], certs: Optional[dict] = None,
              gpa: Optional[dict] = None, assumptions: Optional[dict] = None, level: str = "exact") -> dict:
    certs = certs or {}
    rs = ruleset or {}
    areas_def = rs.get("areas") or []
    keys = {a["key"] for a in areas_def}
    cmap = rs.get("categoryMap") or {}
    rows = [dict(c) for c in courses] + _synthetic(assumptions, ruleset)

    # ① 유효 과목
    for c in rows:
        c["credits"] = float(c.get("credits") or 0)
        c["excludedReason"] = exclusion(c)
        c["excluded"] = c["excludedReason"] is not None
    # ② 재수강·중복 — 유효한 것끼리만 겨룬다
    groups: dict[str, list[dict]] = {}
    for c in rows:
        if not c["excluded"]:
            groups.setdefault(course_key(c), []).append(c)
    for grp in groups.values():
        if len(grp) < 2:
            continue
        best = max(grp, key=lambda c: (C.GRADE_RANK.get(_grade(c.get("grade")), 1), _when(c), c.get("source") != "manual"))
        for c in grp:
            if c is best:
                continue
            c["excluded"] = True
            same_term = _when(c) == _when(best)
            c["excludedReason"] = ("같은 과목이 두 번 들어 있음" if same_term
                                   else f"재수강 — {best.get('year')}-{best.get('semester')} 성적만 인정")
    valid = [c for c in rows if not c["excluded"]]

    # ③ 영역 배정
    for c in rows:
        c["area"], c["areaSetBy"] = _map_area(c, cmap, keys) if ruleset else (None, "none")
    unmapped = [c for c in valid if c["area"] is None and c["credits"] >= 0 and c.get("source") != "whatif"]

    # ④ 합산 · ⑤ 초과 이월(1회) · ⑥ 부족
    own = {k: 0.0 for k in keys}
    for c in valid:
        if c["area"]:
            own[c["area"]] += c["credits"]
    outflow = {k: 0.0 for k in keys}
    inflow = {k: 0.0 for k in keys}
    for a in areas_def:
        tgt = a.get("overflowTo")
        need = float(a.get("minCredits") or 0)
        if tgt in keys and need > 0 and own[a["key"]] > need:
            outflow[a["key"]] = own[a["key"]] - need
            inflow[tgt] += outflow[a["key"]]
    taken = {_norm(c.get("code")) for c in valid if c.get("code")} | {_norm(c.get("name")) for c in valid}
    areas = []
    for a in areas_def:
        k = a["key"]
        need = float(a.get("minCredits") or 0)
        earned = own[k] - outflow[k] + inflow[k]
        req_courses = a.get("courses") or []
        missing = [rc for rc in req_courses
                   if not ((rc.get("code") and _norm(rc["code"]) in taken) or _norm(rc.get("name")) in taken)]
        short = max(0.0, need - earned)
        areas.append({
            "key": k, "label": a.get("label") or k, "required": need, "own": own[k], "earned": earned,
            "outflow": outflow[k], "inflow": inflow[k], "overflowTo": a.get("overflowTo"), "short": short,
            "courses": [_brief(c) for c in valid if c["area"] == k],
            "requiredCourses": [dict(rc, done=rc not in missing) for rc in req_courses],
            "missingCourses": missing,
            "coursesSource": a.get("coursesSource"),
            "listUnknown": bool(a.get("coursesFrom")) and not req_courses,       # 교육과정 스냅숏이 없어 과목 목록을 모름
            "ok": short == 0 and not missing,
            "evidence": a.get("evidence") or "",
        })

    # ⑦ 총계
    total_earned = sum(c["credits"] for c in valid)
    total_req = rs.get("totalCredits")
    total_short = max(0.0, float(total_req) - total_earned) if total_req is not None else None
    area_short = sum(a["short"] for a in areas)
    remaining = max(total_short or 0.0, area_short) if total_req is not None else (area_short or None)

    # 세부 요건 (대학 공통 교양 영역 조건 등)
    checks = []
    for ch in rs.get("checks") or []:
        field = ch.get("field") or "geArea"
        words = [w for w in ch.get("match") or [] if w]
        hit = [c for c in valid if any(w in (c.get(field) or "") for w in words)]
        earned = sum(c["credits"] for c in hit)
        need = float(ch.get("minCredits") or 0)
        ge_like = [c for c in valid if (c.get("area") or "").startswith("ge_") and c.get("source") != "whatif"]
        known = any((c.get(field) or "").strip() for c in ge_like) if field == "geArea" else True
        short = max(0.0, need - earned)
        if short > 0 and known:
            state = "short"
        elif short > 0:
            state = "unknown"                      # 교양영역을 못 읽었다 — 모자란 건지 모른다
        elif ch.get("approximate"):
            state = "unknown"                      # 넉넉히 센 조건이라 채웠다고 단정하지 않는다
        else:
            state = "ok"
        checks.append({"key": ch["key"], "label": ch.get("label") or ch["key"], "required": need, "earned": earned,
                       "short": short, "state": state, "approximate": bool(ch.get("approximate")),
                       "courses": [_brief(c) for c in hit], "evidence": ch.get("evidence") or "",
                       "common": ch.get("common")})

    # ⑧ 평점
    g_req = rs.get("minGpa")
    g_ok: Optional[bool] = None
    g_note = ""
    if g_req and gpa:
        if float(g_req.get("scale") or 0) != float(gpa.get("scale") or 0):
            g_note = "만점 척도가 달라 비교하지 않았습니다"
        else:
            g_ok = float(gpa["value"]) >= float(g_req["value"])
    elif g_req and not gpa:
        g_note = "평점이 없습니다 — 프로필에서 학사정보시스템 가져오기"
    elif not g_req:
        g_note = "이 기준에는 최저 평점이 없습니다"
    gpa_out = {"required": g_req, "current": gpa, "ok": g_ok, "note": g_note}

    # ⑨ 인증
    valid_names = {_norm(c.get("name")) for c in valid if c.get("source") != "whatif"}
    certs_out = []
    for cd in rs.get("certifications") or []:
        u = certs.get(cd["key"]) or {}
        state = u.get("state") if u.get("state") in ("done", "todo", "unknown") else "unknown"
        hints = [h for h in cd.get("hintCourses") or [] if _norm(h) in valid_names]
        certs_out.append({"key": cd["key"], "label": cd.get("label") or cd["key"], "detail": cd.get("detail") or "",
                          "required": bool(cd.get("required", True)), "state": state, "memo": u.get("memo") or "",
                          "updatedAt": u.get("updatedAt"), "evidence": cd.get("evidence") or "", "hintFound": hints})

    # ⑩ 판정 — 이유를 같이 남긴다 (F2-R28 투명성)
    doubts, shorts, unknowns = [], [], []
    if not ruleset:
        doubts.append("졸업요건 기준이 없습니다")
    if level in ("nearest", "track"):
        doubts.append("정확한 입학년도·이수유형 기준이 아닙니다")
    if unmapped:
        doubts.append(f"분류하지 못한 과목 {len(unmapped)}건")
    if any(a["listUnknown"] for a in areas):
        doubts.append("과목 목록(교육과정)을 아직 받지 않았습니다")
    if total_short:
        shorts.append(f"총 {total_short:g}학점")
    for a in areas:
        if a["short"] > 0:
            shorts.append(f"{a['label']} {a['short']:g}학점")
        if a["missingCourses"]:
            shorts.append(f"{a['label']} {len(a['missingCourses'])}과목")
    for ch in checks:
        if ch["state"] == "short":
            shorts.append(f"{ch['label']} {ch['short']:g}학점")
        elif ch["state"] == "unknown":
            unknowns.append(f"{ch['label']} 확인")
    if g_ok is False:
        shorts.append("평점 미달")
    elif g_req and g_ok is None:
        unknowns.append("평점 확인")
    for ce in certs_out:
        if not ce["required"]:
            continue
        if ce["state"] == "todo":
            shorts.append(f"{ce['label']} 미충족")
        elif ce["state"] == "unknown":
            unknowns.append(f"{ce['label']} 확인")
    if doubts:
        verdict = "확인 필요"
    elif shorts:
        verdict = "부족"
    elif unknowns:
        verdict = "확인 필요"
    else:
        verdict = "충족"

    return {
        "verdict": verdict,
        "reasons": {"doubts": doubts, "shorts": shorts, "unknowns": unknowns},
        "total": {"required": total_req, "earned": total_earned, "short": total_short, "remaining": remaining,
                  "areaShort": area_short},
        "gpa": gpa_out,
        "areas": areas,
        "checks": checks,
        "certifications": certs_out,
        "unmapped": [_brief(c) for c in unmapped],
        "courses": [_row(c) for c in rows if c.get("source") != "whatif"],
        "headline": headline(areas, checks, certs_out, total_short),
        "computedAt": datetime.now().isoformat(timespec="seconds"),
    }


def headline(areas: list[dict], checks: list[dict], certs: list[dict], total_short: Optional[float]) -> str:
    """'전공필수 2과목 · 교양선택 3학점' — 요약·타일 한 줄 (F2-S01·S09)."""
    parts = []
    for a in areas:
        if a["missingCourses"]:
            parts.append(f"{a['label']} {len(a['missingCourses'])}과목")
        elif a["short"] > 0:
            parts.append(f"{a['label']} {a['short']:g}학점")
    for ch in checks:
        if ch["state"] == "short":
            parts.append(f"{ch['label']} {ch['short']:g}학점")
    todo = [c for c in certs if c["required"] and c["state"] == "todo"]
    if todo:
        parts.append(f"인증 {len(todo)}건")
    if not parts and total_short:
        parts.append("영역은 채움 · 총 학점만 남음")
    return " · ".join(parts[:3]) + (" 외" if len(parts) > 3 else "")


def _brief(c: dict) -> dict:
    return {"id": c.get("id"), "name": c.get("name"), "code": c.get("code"), "credits": c.get("credits"),
            "grade": c.get("grade"), "year": c.get("year"), "semester": c.get("semester"), "source": c.get("source")}


def _row(c: dict) -> dict:
    """이수 과목 탭 한 줄 — 원천 값 + 계산 결과(영역·제외 이유)."""
    keys = ("id", "year", "semester", "code", "name", "credits", "grade", "rawCategory", "geArea", "status", "retake",
            "source", "memo", "area", "areaSetBy", "excluded", "excludedReason", "excludedByUser", "areaOverride")
    return {k: c.get(k) for k in keys}


def compare(current: dict, assumed: dict) -> dict:
    """가정 계산 — 현재와 가정 후를 나란히 (F2-R52)."""
    def pick(s: dict) -> dict:
        return {"verdict": s["verdict"], "total": s["total"], "headline": s["headline"],
                "areas": [{k: a[k] for k in ("key", "label", "required", "earned", "short", "ok")}
                          | {"missing": [m.get("name") for m in a["missingCourses"]]} for a in s["areas"]]}
    return {"current": pick(current), "assumed": pick(assumed)}
