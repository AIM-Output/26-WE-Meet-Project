"""원천 목록 + 프로필 → '내 장학 원천'. 표준 라이브러리만 (백엔드도 import 한다).

directory/sources.json 에 학교 전체·부서·사업단·내 소속 원천이 있다. 프로필(C2)의 단과대학·학과·전공으로
  - 학교 전체(scope=all)            모두에게 켠다
  - 캠퍼스(scope=campus)            그 캠퍼스 학생에게 켠다 (여수: 공학대학·문화사회과학대학·수산해양대학·창의융합학부)
  - 관련 사업단(scope=related)       단과대학·학과·전공 이름·계열이 맞으면 켠다. 안 맞아도 open(전공 무관 참여)이면 '켤 수 있음'
  - 내 소속(scope=mine)             프로필 단과대학·학과 홈페이지에서 장학 게시판을 찾아 읽는다 (homepages — F1 목록)
사용자가 켜고 끈 것(store.sources.enabled)이 이 기본값을 이긴다.

학교 공지의 '작성 부서'(학생과·인문사회융합인재양성사업단·사회과학대학 …)로 그 글이 어느 사업단·단과대학 것인지도 여기서 찾는다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from . import config as C

_cache: dict = {"mtime": None, "data": None}
_home_cache: dict = {"path": None, "mtime": None, "data": None}


def load() -> dict:
    p = C.SOURCES_FILE
    mtime = p.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache.update(mtime=mtime, data=json.loads(p.read_text(encoding="utf-8")))
    return _cache["data"]


def sources() -> list[dict]:
    return load()["sources"]


def get(key: str) -> Optional[dict]:
    return next((s for s in sources() if s["key"] == key), None)


def norm(s: Optional[str]) -> str:
    s = re.sub(r"\(.*?\)", "", s or "")
    return re.sub(r"[\s·・.,]+", "", s)


def _core(s: Optional[str]) -> str:
    """'기계공학부' → '기계공학' · '인공지능전공' → '인공지능' (꼬리를 뗀 이름)."""
    n = norm(s)
    return re.sub(r"(학부|학과|전공|계열|융합전공)$", "", n) or n


# ── 프로필에서 읽는 것 ────────────────────────────────────

def campus_of(profile: Optional[dict]) -> Optional[str]:
    p = profile or {}
    college = norm(p.get("college"))
    if not college:
        return None
    for campus, names in load().get("campus", {}).items():
        if any(norm(n) == college for n in names):
            return campus
    return "광주"


def fields_of(profile: Optional[dict]) -> list[str]:
    """계열 — 학과 예외 → 단과대학 기본값. 모르면 []."""
    p = profile or {}
    f = load().get("fields", {})
    for name in (p.get("major"), p.get("department")):
        n = norm(name)
        for dept, groups in f.get("departments", {}).items():
            if n and norm(dept) == n:
                return list(groups)
    college = norm(p.get("college"))
    for col, groups in f.get("colleges", {}).items():
        if college and norm(col) == college:
            return list(groups)
    return []


def affiliation_names(profile: Optional[dict]) -> list[str]:
    p = profile or {}
    return [x for x in (p.get("college"), p.get("department"), p.get("major")) if x]


# ── 원천이 나에게 맞는가 ────────────────────────────────────

def relevance(src: dict, profile: Optional[dict]) -> dict:
    """{level: all|campus|related|open|other|mine|needs_profile, why, default(켤지)}"""
    aud = src.get("audience") or {"scope": "all"}
    scope = aud.get("scope", "all")
    p = profile or {}
    if scope == "all":
        return {"level": "all", "why": "전남대 학생 모두", "default": True}
    if scope == "mine":
        target = p.get("college") if src.get("level") == "college" else (p.get("department") or p.get("major"))
        if not target:
            return {"level": "needs_profile", "why": "프로필에 소속을 넣으면 찾습니다", "default": True}
        return {"level": "mine", "why": target, "default": True}
    if scope == "campus":
        mine = campus_of(p)
        if mine is None:
            return {"level": "needs_profile", "why": f"{aud.get('campus')}캠퍼스 학생", "default": True}
        if mine == aud.get("campus"):
            return {"level": "campus", "why": f"{mine}캠퍼스 학생", "default": True}
        return {"level": "other", "why": f"{aud.get('campus')}캠퍼스 학생 대상", "default": False}
    # related
    names = affiliation_names(p)
    if not names:
        return {"level": "needs_profile", "why": "프로필에 소속을 넣으면 관련 여부를 봅니다",
                "default": bool(aud.get("open"))}
    cores = {_core(n) for n in names} | {norm(n) for n in names}
    for col in aud.get("colleges", []):
        if norm(col) == norm(p.get("college")):
            return {"level": "related", "why": f"{p.get('college')} 학생 대상", "default": True}
    for dept in aud.get("departments", []):
        if norm(dept) in cores or _core(dept) in cores:
            return {"level": "related", "why": f"{dept} 참여", "default": True}
    joined = "".join(norm(n) for n in names)
    for kw in aud.get("keywords", []):
        if norm(kw) and norm(kw) in joined:
            return {"level": "related", "why": f"'{kw}' 분야 — 내 학과와 가까운 사업단", "default": True}
    mine_fields = set(fields_of(p))
    if aud.get("fields") and mine_fields & set(aud["fields"]):
        return {"level": "related", "why": f"{'·'.join(sorted(mine_fields & set(aud['fields'])))} 계열 대상", "default": True}
    if aud.get("open"):
        return {"level": "open", "why": "다른 전공 중심 · 전공 무관 참여 가능(융합전공·마이크로디그리)", "default": False}
    return {"level": "other", "why": "다른 전공 대상", "default": False}


def resolve(profile: Optional[dict], overrides: Optional[dict[str, bool]] = None) -> list[dict]:
    """모든 원천 + 나에게 맞는지 + 켜져 있는지. overrides = {key: enabled} (사용자가 바꾼 것만)."""
    overrides = overrides or {}
    out = []
    for s in sources():
        rel = relevance(s, profile)
        enabled = overrides.get(s["key"], rel["default"])
        out.append({**s, "relevance": rel, "enabled": bool(enabled), "userSet": s["key"] in overrides})
    return out


def collectable(rows: list[dict]) -> list[dict]:
    """수집기가 실제로 읽을 원천 — 켜져 있고 게시판이 있는 것(relay 는 학교 공지로 들어온다)."""
    return [r for r in rows if r["enabled"] and r["kind"] != "relay"]


def unit_for(writer: Optional[str], title: str = "", category: Optional[str] = None) -> Optional[dict]:
    """학교 공지의 작성 부서·제목 말머리 → 원천(사업단·부서). 학생과는 학교 전체 원천이라 None."""
    w = norm(writer)
    blob = norm(f"{category or ''}{title[:40]}")
    for s in sources():
        for name in s.get("writers", []):
            n = norm(name)
            if not n:
                continue
            if w and (w == n or w.startswith(n)) and s["key"] != "jnu_scholarship":
                return s
            if len(n) >= 6 and n in blob:
                return s
    return None


# ── 단과대학·학과 홈페이지 (F1_Bachelor_agent 가 모아 둔 목록을 같이 쓴다) ───

def _homepages() -> dict:
    for p in C.HOMEPAGES_FILES:
        try:
            mtime = p.stat().st_mtime
        except OSError:
            continue
        if _home_cache["path"] != p or _home_cache["mtime"] != mtime:
            _home_cache.update(path=p, mtime=mtime, data=json.loads(p.read_text(encoding="utf-8")))
        return _home_cache["data"]
    return {"colleges": []}


def homepage(level: str, profile: Optional[dict]) -> Optional[dict]:
    """프로필 소속 → {name, homepage, listedAs}. 단과대학이 목록에 있으면 그 안에서만 학과를 찾는다
    (여수 '경영학과'가 광주 '경영학부'로 가는 식의 엉뚱한 연결을 막는다 — F1 homepages.py 와 같은 규칙)."""
    p = profile or {}
    cols = _homepages().get("colleges", [])
    college = norm(p.get("college"))
    home = next((c for c in cols if norm(c["name"]) == college), None) if college else None
    if home is None and college:
        home = next((c for c in cols if norm(c["name"]).startswith(college) or college.startswith(norm(c["name"]))), None)
    if level == "college":
        if home and home.get("homepage"):
            return {"name": p.get("college"), "homepage": home["homepage"], "listedAs": home["name"]}
        return None
    ordered = [home] if home else cols
    for name in [x for x in (p.get("department"), p.get("major")) if x]:
        n, core = norm(name), _core(name)
        for c in ordered:
            for d in c.get("departments", []):
                if d.get("homepage") and (norm(d["name"]) == n or _core(d["name"]) == core):
                    return {"name": name, "homepage": d["homepage"], "listedAs": d["name"]}
        for c in cols:                     # 학부 자체가 단과대학급인 곳 ('창의융합학부')
            if c.get("homepage") and norm(c["name"]) == n:
                return {"name": name, "homepage": c["homepage"], "listedAs": c["name"]}
    return None


def college_names() -> list[str]:
    """제목에서 '○○대학' 대상 장학을 알아보는 데 쓰는 단과대학 이름들 (원천 목록 계열표 + 홈페이지 목록)."""
    names = set(load().get("fields", {}).get("colleges", {}))
    names |= {c["name"] for c in _homepages().get("colleges", []) if c.get("name")}
    return sorted((n for n in names if n.endswith("대학") and "대학원" not in n), key=len, reverse=True)
