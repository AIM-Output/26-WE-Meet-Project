"""화면이 받는 모양과 사용자 조작 — 이수 과목 · 판정 · 가정 계산 · 룰셋 내 수정본 · 인증 · 내 계획. 표준 라이브러리만.

계산은 전부 calc.calculate 한 곳에서 한다 (Frontend-Route 7-5 '계산기 하나만'). 여기서는 재료를 모아 넘기기만 한다.
프로필은 C2 의 matching_view 모양을 받는다: deptCode·majorCode·admissionYear·track·gpa·department·major …
"""
from __future__ import annotations

import re
import secrets
import sqlite3
from typing import Any, Optional

from . import calc, curriculum, rules
from .rules import TRACKS
from .store import course_id, dumps, get_meta, loads, now_iso, set_meta, touch

SEMESTERS = ("1", "여름", "2", "겨울")
CERT_STATES = ("done", "todo", "unknown")


class Invalid(ValueError):
    pass


class NotFound(LookupError):
    pass


class Conflict(RuntimeError):
    pass


# ── 재료 모으기 ─────────────────────────────────────────────

def norm_semester(s: Any) -> str:
    """학사정보시스템 학기 칸 → '1'·'2'·'여름'·'겨울' ('하계 계절' → 여름, 실측 §4)."""
    t = str(s or "").strip()
    if "하계" in t or "여름" in t:
        return "여름"
    if "동계" in t or "겨울" in t:
        return "겨울"
    m = re.match(r"^([12])", t)
    return m.group(1) if m else t


def load_courses(con: sqlite3.Connection) -> list[dict]:
    """계산기 입력 — 학사정보시스템 과목 + 직접 입력 과목 + 과목별 내 지정."""
    ov = {r["course_id"]: r for r in con.execute("SELECT * FROM overrides")}
    out = []
    for r in con.execute("SELECT * FROM courses ORDER BY year, semester, seq"):
        o = ov.get(r["id"])
        out.append({"id": r["id"], "year": r["year"], "semester": r["semester"], "code": r["code"], "name": r["name"],
                    "credits": r["credits"], "grade": r["grade"], "rawCategory": r["raw_category"], "geArea": r["ge_area"],
                    "status": r["status"], "retake": r["retake"], "source": "hakstd", "memo": "",
                    "areaOverride": o["area"] if o else None, "excludedByUser": bool(o and o["excluded"])})
    for r in con.execute("SELECT * FROM manual_courses ORDER BY year, semester, created_at"):
        o = ov.get(r["id"])
        out.append({"id": r["id"], "year": r["year"], "semester": r["semester"], "code": r["code"], "name": r["name"],
                    "credits": r["credits"], "grade": r["grade"], "rawCategory": r["raw_category"], "geArea": r["ge_area"],
                    "status": None, "retake": None, "source": "manual", "memo": r["memo"] or "",
                    "areaOverride": o["area"] if o else None, "excludedByUser": bool(o and o["excluded"])})
    return out


def user_map(con: sqlite3.Connection) -> dict:
    return {r["raw"]: r["area"] for r in con.execute("SELECT raw, area FROM category_map")}


def cert_states(con: sqlite3.Connection) -> dict:
    return {r["key"]: {"state": r["state"], "memo": r["memo"], "updatedAt": r["updated_at"]}
            for r in con.execute("SELECT * FROM certs")}


def _track(profile: Optional[dict], track: Optional[str]) -> str:
    if track in TRACKS:
        return track
    t = (profile or {}).get("track")
    return t if t in TRACKS else "single"


def target_of(profile: Optional[dict], track: str) -> dict:
    p = profile or {}
    return {"deptCode": p.get("deptCode"), "majorCode": p.get("majorCode"), "admissionYear": p.get("admissionYear"),
            "track": track}


def _tkey(t: dict) -> str:
    return rules.target_key(t.get("deptCode"), t.get("majorCode"), t.get("admissionYear"), t.get("track") or "single")


def user_ruleset(con: sqlite3.Connection, target: dict) -> Optional[sqlite3.Row]:
    return con.execute("SELECT * FROM rulesets WHERE target = ?", (_tkey(target),)).fetchone()


def context(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str] = None) -> dict:
    """이 사람에게 맞는 룰셋 — 매칭 결과 + 펼친 룰셋 + 편집용 원본."""
    trk = _track(profile, track)
    tgt = target_of(profile, trk)
    row = user_ruleset(con, tgt) if tgt["deptCode"] and tgt["admissionYear"] else None
    mine = loads(row["data"]) if row else None
    m = rules.match(tgt["deptCode"], tgt["majorCode"], tgt["admissionYear"], trk, user=mine)
    eff = rules.resolve(m["ruleset"], profile, user_map(con))
    base = None
    base_changed = False
    if row and row["base_id"]:
        b = rules.by_id(row["base_id"])
        if b:
            base = {"id": b["id"], "version": b.get("version"), "label": rules.basis_label(b)}
            base_changed = (b.get("version") or 0) > (row["base_version"] or 0)
    elif m["ruleset"] and m["level"] != "user":
        base = {"id": m["ruleset"].get("id"), "version": m["ruleset"].get("version"), "label": rules.basis_label(m["ruleset"])}
    return {"track": trk, "target": tgt, "level": m["level"], "warnings": m["warnings"], "ruleset": eff,
            "editable": m["ruleset"], "edited": row is not None, "editedAt": row["updated_at"] if row else None,
            "base": base, "baseChanged": base_changed}


def _ruleset_meta(ctx: dict) -> dict:
    r = ctx["ruleset"]
    return {
        "id": (r or {}).get("id"), "label": rules.basis_label(r) if r else "기준 없음",
        "level": ctx["level"], "levelLabel": rules.LEVEL_LABEL[ctx["level"]], "warnings": ctx["warnings"],
        "edited": ctx["edited"], "baseChanged": ctx["baseChanged"], "verified": bool((r or {}).get("verified")),
        "track": ctx["track"], "trackLabel": rules.TRACK_LABEL[ctx["track"]],
        "totalCredits": (r or {}).get("totalCredits"),
        "areas": [{"key": a["key"], "label": a.get("label") or a["key"]} for a in (r or {}).get("areas", [])]
        or [{"key": a["key"], "label": a["label"]} for a in rules.TEMPLATE_AREAS],
        "notes": (r or {}).get("notes") or [], "source": (r or {}).get("source"),
        "commonSources": (r or {}).get("commonSources") or [], "curriculum": (r or {}).get("curriculum"),
        "totalEvidence": (r or {}).get("totalEvidence") or "", "minGpaEvidence": (r or {}).get("minGpaEvidence") or "",
    }


def _data_meta(con: sqlite3.Connection) -> dict:
    n_auto = con.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
    n_manual = con.execute("SELECT COUNT(*) FROM manual_courses").fetchone()[0]
    return {"importedAt": get_meta(con, "imported_at"), "hakstdCount": n_auto, "manualCount": n_manual,
            "count": n_auto + n_manual}


def missing_profile(profile: Optional[dict]) -> list[str]:
    p = profile or {}
    return [k for k in ("deptCode", "admissionYear") if not p.get(k)]


def status(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str] = None,
           assumptions: Optional[dict] = None) -> dict:
    """GET /api/graduation/status — 판정 + 영역별 + 인증 + 이수 과목 + 어떤 기준으로 계산했는지."""
    ctx = context(con, profile, track)
    res = calc.calculate(load_courses(con), ctx["ruleset"], cert_states(con), (profile or {}).get("gpa"),
                         assumptions, level=ctx["level"])
    p = profile or {}
    return {
        **res,
        "ruleset": _ruleset_meta(ctx),
        "profile": {"department": p.get("department"), "major": p.get("major"), "admissionYear": p.get("admissionYear"),
                    "track": p.get("track"), "deptCode": p.get("deptCode"), "majorCode": p.get("majorCode")},
        "profileMissing": missing_profile(profile),
        "data": _data_meta(con),
        "updatedAt": get_meta(con, "updated_at"),
    }


def summary(con: sqlite3.Connection, profile: Optional[dict]) -> dict:
    """대시보드 타일 (F2-S09) — '졸업까지 32학점 · 전공필수 2과목'."""
    s = status(con, profile)
    return {"verdict": s["verdict"], "remaining": s["total"]["remaining"], "earned": s["total"]["earned"],
            "required": s["total"]["required"], "headline": s["headline"], "level": s["ruleset"]["level"],
            "hasData": s["data"]["count"] > 0, "unmapped": len(s["unmapped"]), "profileMissing": s["profileMissing"],
            "importedAt": s["data"]["importedAt"]}


def simulate(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str], assumptions: dict) -> dict:
    """POST /api/graduation/simulate — 같은 계산기를 가정을 더해 한 번 더 (F2-R50~R52). 저장하지 않는다."""
    a = _assumptions(assumptions)
    cur = status(con, profile, track)
    after = status(con, profile, track, a)
    return {**calc.compare(cur, after), "assumptions": a}


def _assumptions(v: Any) -> dict:
    if not isinstance(v, dict):
        raise Invalid("가정은 {areas: {영역: 학점}, courses: [학수번호]} 입니다")
    areas = {}
    for k, x in (v.get("areas") or {}).items():
        if isinstance(x, bool) or not isinstance(x, (int, float)) or not 0 <= x <= 60:
            raise Invalid(f"가정 학점은 0~60 입니다: {k}")
        if x:
            areas[str(k)] = x
    courses = [str(c)[:80] for c in (v.get("courses") or []) if str(c).strip()][:50]
    return {"areas": areas, "courses": courses}


# ── 이수 과목 (F2-R04·R05) ───────────────────────────────────

def _course_fields(body: dict, partial: bool) -> dict:
    out: dict[str, Any] = {}
    if "name" in body or not partial:
        name = str(body.get("name") or "").strip()
        if not 1 <= len(name) <= 80:
            raise Invalid("과목명은 1~80자입니다")
        out["name"] = name
    if "credits" in body or not partial:
        cr = body.get("credits")
        if isinstance(cr, bool) or not isinstance(cr, (int, float)) or not 0 <= cr <= 30:
            raise Invalid("학점은 0~30 사이 숫자입니다")
        out["credits"] = float(cr)
    if "year" in body:
        y = body.get("year")
        if y is not None and (isinstance(y, bool) or not isinstance(y, int) or not 1990 <= y <= 2100):
            raise Invalid("년도가 올바르지 않습니다")
        out["year"] = y
    if "semester" in body:
        s = norm_semester(body.get("semester")) if body.get("semester") is not None else None
        if s is not None and s not in SEMESTERS:
            raise Invalid("학기는 1·2·여름·겨울 중 하나입니다")
        out["semester"] = s
    for k, n in (("code", 20), ("grade", 5), ("memo", 300), ("rawCategory", 20), ("geArea", 40)):
        if k in body:
            v = body.get(k)
            v = str(v).strip() if v is not None else ""
            if len(v) > n:
                raise Invalid(f"{k} 는 {n}자 이내입니다")
            out[k] = (v.upper() if k in ("code", "grade") else v) or None
    return out


def _check_area(area: Any, keys: set) -> Optional[str]:
    if area in (None, ""):
        return None
    if area not in keys:
        raise Invalid(f"이 기준에 없는 영역입니다: {area}")
    return str(area)


def area_keys(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str] = None) -> set:
    r = context(con, profile, track)["ruleset"]
    return {a["key"] for a in (r or {}).get("areas", [])} or {a["key"] for a in rules.TEMPLATE_AREAS}


def add_manual(con: sqlite3.Connection, body: dict, keys: set) -> str:
    """직접 입력 과목 — 출처 manual, 가져오기에도 남는다."""
    f = _course_fields(body, partial=False)
    area = _check_area(body.get("area"), keys)
    cid = "gm:" + secrets.token_hex(6)
    t = now_iso()
    con.execute("INSERT INTO manual_courses(id, year, semester, code, name, credits, grade, raw_category, ge_area, memo,"
                " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (cid, f.get("year"), f.get("semester"), f.get("code"), f["name"], f["credits"], f.get("grade"),
                 f.get("rawCategory"), f.get("geArea"), f.get("memo") or "", t, t))
    if area:
        _set_override(con, cid, area=area)
    touch(con)
    return cid


def _set_override(con: sqlite3.Connection, cid: str, **kw: Any) -> None:
    r = con.execute("SELECT * FROM overrides WHERE course_id = ?", (cid,)).fetchone()
    area = kw["area"] if "area" in kw else (r["area"] if r else None)
    excluded = kw["excluded"] if "excluded" in kw else (r["excluded"] if r else None)
    if area is None and not excluded:
        con.execute("DELETE FROM overrides WHERE course_id = ?", (cid,))
        return
    con.execute("INSERT INTO overrides(course_id, area, excluded, updated_at) VALUES (?,?,?,?) "
                "ON CONFLICT(course_id) DO UPDATE SET area = excluded.area, excluded = excluded.excluded, "
                "updated_at = excluded.updated_at", (cid, area, int(bool(excluded)), now_iso()))


def _find(con: sqlite3.Connection, cid: str) -> tuple[str, sqlite3.Row]:
    r = con.execute("SELECT * FROM courses WHERE id = ?", (cid,)).fetchone()
    if r:
        return "hakstd", r
    r = con.execute("SELECT * FROM manual_courses WHERE id = ?", (cid,)).fetchone()
    if r:
        return "manual", r
    raise NotFound("과목이 없습니다")


def patch_course(con: sqlite3.Connection, cid: str, body: dict, keys: set) -> dict:
    """구분 지정·계산 제외·(직접 입력 과목이면) 내용 수정.
    applyToCategory=true 면 그 과목의 교과구분 전체를 그 영역으로 매핑한다 — 한 번 지정하면 다음부터 자동 (F2 8절)."""
    src, row = _find(con, cid)
    res = {"source": src, "mapped": None}
    if "area" in body:
        area = _check_area(body.get("area"), keys)
        raw = (row["raw_category"] or "").strip()
        if body.get("applyToCategory") and raw and area:
            con.execute("INSERT INTO category_map(raw, area, updated_at) VALUES (?,?,?) ON CONFLICT(raw) DO UPDATE SET "
                        "area = excluded.area, updated_at = excluded.updated_at", (raw, area, now_iso()))
            _set_override(con, cid, area=None)
            res["mapped"] = {"raw": raw, "area": area}
        else:
            _set_override(con, cid, area=area)
    if "excluded" in body:
        _set_override(con, cid, excluded=bool(body.get("excluded")))
    edit = {k: v for k, v in body.items() if k in ("name", "credits", "year", "semester", "code", "grade", "memo",
                                                   "rawCategory", "geArea")}
    if edit:
        if src != "manual":
            raise Conflict("학사정보시스템에서 가져온 과목은 내용을 고칠 수 없습니다 — 구분 지정·계산 제외만 됩니다")
        f = _course_fields(edit, partial=True)
        cols = {"name": "name", "credits": "credits", "year": "year", "semester": "semester", "code": "code",
                "grade": "grade", "memo": "memo", "rawCategory": "raw_category", "geArea": "ge_area"}
        sets = ", ".join(f"{cols[k]} = ?" for k in f)
        con.execute(f"UPDATE manual_courses SET {sets}, updated_at = ? WHERE id = ?",
                    (*[("" if k == "memo" and v is None else v) for k, v in f.items()], now_iso(), cid))
    touch(con)
    return res


def delete_course(con: sqlite3.Connection, cid: str) -> None:
    src, _ = _find(con, cid)
    if src != "manual":
        raise Conflict("학사정보시스템에서 가져온 과목은 지울 수 없습니다 — '계산에서 빼기'를 쓰세요 (원본은 학사시스템)")
    con.execute("DELETE FROM manual_courses WHERE id = ?", (cid,))
    con.execute("DELETE FROM overrides WHERE course_id = ?", (cid,))
    touch(con)


def apply_import(con: sqlite3.Connection, fetched: list[dict]) -> dict:
    """hakstd.py 가 읽어 온 과목 → courses 표를 통째로 바꾼다. 내 지정(overrides)·직접 입력은 그대로 (F2-R05)."""
    rows, seen = [], set()
    t = now_iso()
    for i, c in enumerate(fetched):
        name = str(c.get("name") or "").strip()
        try:
            credits = float(c.get("credits"))
        except (TypeError, ValueError):
            continue
        if not name:
            continue
        year = int(c["year"]) if str(c.get("year") or "").isdigit() else None
        sem = norm_semester(c.get("semester"))
        code = (str(c.get("code") or "").strip().upper()) or None
        cid = course_id(year, sem, code, name)
        n = 2
        while cid in seen:                                  # 같은 학기에 같은 과목이 두 줄 — 드물지만 id 는 달라야 한다
            cid = course_id(year, sem, code, f"{name}#{n}")
            n += 1
        seen.add(cid)
        rows.append((cid, year, sem, code, name, credits, (str(c.get("grade") or "").strip().upper() or None),
                     (str(c.get("rawCategory") or "").strip() or None), (str(c.get("geArea") or "").strip() or None),
                     (str(c.get("status") or "").strip() or None), (str(c.get("retake") or "").strip() or None), i, t))
    before = {r[0] for r in con.execute("SELECT id FROM courses")}
    con.execute("DELETE FROM courses")
    con.executemany("INSERT INTO courses(id, year, semester, code, name, credits, grade, raw_category, ge_area, status,"
                    " retake, seq, fetched_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    after = {r[0] for r in rows}
    set_meta(con, "imported_at", t)
    set_meta(con, "import_count", str(len(rows)))
    touch(con)
    return {"count": len(rows), "added": len(after - before), "removed": len(before - after), "importedAt": t}


# ── 교과구분 매핑 (F2-R22) ─────────────────────────────────

def category_view(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str] = None) -> dict:
    """룰셋 기본 매핑 + 내 지정 + 내 이수 과목에 실제로 나온 구분(몇 과목인지)."""
    ctx = context(con, profile, track)
    base = dict((ctx["editable"] or {}).get("categoryMap") or rules.DEFAULT_CATEGORY_MAP)
    mine = user_map(con)
    seen: dict[str, int] = {}
    for c in load_courses(con):
        raw = (c.get("rawCategory") or "").strip()
        if raw:
            seen[raw] = seen.get(raw, 0) + 1
    names = sorted(set(base) | set(mine) | set(seen), key=lambda k: (-seen.get(k, 0), k))
    return {"rows": [{"raw": k, "base": base.get(k), "mine": mine.get(k), "area": mine.get(k) or base.get(k),
                      "courses": seen.get(k, 0)} for k in names],
            "areas": _ruleset_meta(ctx)["areas"]}


def set_category(con: sqlite3.Connection, raw: str, area: Optional[str], keys: set) -> None:
    raw = (raw or "").strip()
    if not raw or len(raw) > 20:
        raise Invalid("교과구분 이름이 올바르지 않습니다")
    if area in (None, ""):
        con.execute("DELETE FROM category_map WHERE raw = ?", (raw,))
    else:
        con.execute("INSERT INTO category_map(raw, area, updated_at) VALUES (?,?,?) ON CONFLICT(raw) DO UPDATE SET "
                    "area = excluded.area, updated_at = excluded.updated_at", (raw, _check_area(area, keys), now_iso()))
    touch(con)


# ── 졸업인증 (F2-R40·R41) ───────────────────────────────────

def set_cert(con: sqlite3.Connection, key: str, body: dict) -> dict:
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key or ""):
        raise Invalid("인증 key 가 올바르지 않습니다")
    cur = cert_states(con).get(key) or {"state": "unknown", "memo": ""}
    state = body.get("state", cur["state"])
    if state not in CERT_STATES:
        raise Invalid("상태는 done·todo·unknown 중 하나입니다")
    memo = str(body.get("memo", cur["memo"]) or "").strip()
    if len(memo) > 300:
        raise Invalid("메모는 300자 이내입니다")
    t = now_iso()
    con.execute("INSERT INTO certs(key, state, memo, updated_at) VALUES (?,?,?,?) ON CONFLICT(key) DO UPDATE SET "
                "state = excluded.state, memo = excluded.memo, updated_at = excluded.updated_at", (key, state, memo, t))
    touch(con)
    return {"key": key, "state": state, "memo": memo, "updatedAt": t}


# ── 룰셋 내 수정본 (F2-R13·R14, F2-S10·S11) ───────────────────

def ruleset_view(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str] = None,
                 target: Optional[dict] = None) -> dict:
    """GET /api/graduation/ruleset — 매칭 결과 + 펼친 룰셋(보기) + 편집용 원본 + (없으면) 빈 템플릿·복사 후보."""
    prof = dict(profile or {})
    if target:                                           # 다른 학과·연도를 골라 볼 때 (설정 화면 상단 선택)
        prof.update({k: v for k, v in target.items() if k in ("deptCode", "majorCode", "admissionYear") and v})
    ctx = context(con, prof, track or (target or {}).get("track"))
    editable = ctx["editable"] or rules.template(prof, ctx["track"])
    return {
        "target": {**ctx["target"], "label": _target_label(prof, ctx["track"])},
        "level": ctx["level"], "levelLabel": rules.LEVEL_LABEL[ctx["level"]], "warnings": ctx["warnings"],
        "edited": ctx["edited"], "editedAt": ctx["editedAt"], "base": ctx["base"], "baseChanged": ctx["baseChanged"],
        "ruleset": ctx["ruleset"], "editable": editable, "isTemplate": ctx["editable"] is None,
        "similar": rules.listing(), "categoryMapMine": user_map(con),
        "label": rules.basis_label(ctx["ruleset"]) if ctx["ruleset"] else "기준 없음",
    }


def _target_label(p: dict, track: str) -> str:
    who = " · ".join(x for x in (p.get("department"), p.get("major")) if x) or "학과 미입력"
    year = f"{p['admissionYear']} 입학" if p.get("admissionYear") else "입학년도 미입력"
    return f"{year} · {who} · {rules.TRACK_LABEL[track]}"


def save_ruleset(con: sqlite3.Connection, profile: Optional[dict], body: dict) -> dict:
    """PUT — 내 수정본으로 저장. 기본 룰셋 파일은 건드리지 않는다. 저장한 학과·연도에 한해 이것이 우선한다."""
    if not isinstance(body, dict) or "ruleset" not in body:
        raise Invalid("{ruleset, track?, target?} 을 보내 주세요")
    prof = dict(profile or {})
    tgt_in = body.get("target") or {}
    prof.update({k: v for k, v in tgt_in.items() if k in ("deptCode", "majorCode", "admissionYear") and v})
    trk = _track(prof, body.get("track") or tgt_in.get("track"))
    tgt = target_of(prof, trk)
    if not tgt["deptCode"] or not tgt["admissionYear"]:
        raise Invalid("학과·입학년도가 있어야 저장할 수 있습니다 — 프로필을 먼저 입력하세요")
    doc = rules.validate(body["ruleset"])
    base_id = doc.get("id") if doc.get("id") and rules.by_id(doc["id"]) else None
    base = rules.by_id(base_id) if base_id else None
    doc.update({"deptCode": tgt["deptCode"], "majorCode": tgt["majorCode"], "admissionYear": tgt["admissionYear"],
                "admissionYearTo": tgt["admissionYear"], "track": trk,
                "department": prof.get("department") or doc.get("department"),
                "major": prof.get("major") or doc.get("major"),
                "id": f"user:{_tkey(tgt)}", "editedByUser": True})
    con.execute("INSERT INTO rulesets(target, data, base_id, base_version, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(target) DO UPDATE SET data = excluded.data, base_id = COALESCE(excluded.base_id, rulesets.base_id), "
                "base_version = COALESCE(excluded.base_version, rulesets.base_version), updated_at = excluded.updated_at",
                (_tkey(tgt), dumps(doc), base_id, (base or {}).get("version"), now_iso()))
    touch(con)
    return ruleset_view(con, prof, trk)


def reset_ruleset(con: sqlite3.Connection, profile: Optional[dict], track: Optional[str] = None,
                  target: Optional[dict] = None) -> dict:
    """DELETE — '기본값으로 되돌리기'. 내 수정본만 지운다."""
    prof = dict(profile or {})
    if target:
        prof.update({k: v for k, v in target.items() if k in ("deptCode", "majorCode", "admissionYear") and v})
    trk = _track(prof, track)
    con.execute("DELETE FROM rulesets WHERE target = ?", (_tkey(target_of(prof, trk)),))
    touch(con)
    return ruleset_view(con, prof, trk)


# ── 내 계획 (F2-R53) ────────────────────────────────────────

def plans(con: sqlite3.Connection) -> list[dict]:
    return [{"id": r["id"], "name": r["name"], "track": r["track"], "assumptions": loads(r["assumptions"]),
             "createdAt": r["created_at"]} for r in con.execute("SELECT * FROM plans ORDER BY created_at DESC")]


def save_plan(con: sqlite3.Connection, body: dict) -> dict:
    name = str(body.get("name") or "").strip()[:40] or "내 계획"
    a = _assumptions(body.get("assumptions") or {})
    trk = body.get("track") if body.get("track") in TRACKS else "single"
    pid = "pl:" + secrets.token_hex(5)
    t = now_iso()
    con.execute("INSERT INTO plans(id, name, track, assumptions, created_at) VALUES (?,?,?,?,?)",
                (pid, name, trk, dumps(a), t))
    return {"id": pid, "name": name, "track": trk, "assumptions": a, "createdAt": t}


def delete_plan(con: sqlite3.Connection, pid: str) -> None:
    if not con.execute("DELETE FROM plans WHERE id = ?", (pid,)).rowcount:
        raise NotFound("계획이 없습니다")


# ── 초기화 ──────────────────────────────────────────────────

def clear_all(con: sqlite3.Connection) -> None:
    """이수 내역·내 지정·인증·수정본·계획 전부 지우기 (프로필 '내 정보 전부 지우기'와 함께)."""
    for t in ("courses", "manual_courses", "overrides", "category_map", "certs", "rulesets", "plans"):
        con.execute(f"DELETE FROM {t}")
    set_meta(con, "imported_at", None)
    set_meta(con, "import_count", None)
    touch(con)


def curriculum_state(profile: Optional[dict]) -> dict:
    """내 학과·전공·입학년도의 교육과정 스냅숏이 있는지 (없으면 '받기' 버튼)."""
    p = profile or {}
    codes = curriculum.targets(p.get("deptCode"), p.get("majorCode"))
    have = [c for c in codes if curriculum.load(c, p.get("admissionYear"))]
    return {"codes": codes, "year": p.get("admissionYear"), "have": have, "missing": [c for c in codes if c not in have],
            "collegeCode": p.get("collegeCode")}
