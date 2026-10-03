"""내 소속 → 홈페이지 찾기 (원천 ③ 내 단과대학 · ④ 내 학부). 표준 라이브러리만 — 백엔드도 import 한다.

목록: directory/homepages.json (저장소에 넣어 둔 스냅숏) — `python -m bachelor directory-sync` 로 다시 받으면
data/directory/homepages.json 이 이긴다. 목록의 원천은 전남대 대표 홈페이지 '대학·학부(과)' 안내 표다.

이름 맞추기
  프로필(C2)의 단과대학·학과 이름은 교육과정검색 기준이고, 목록은 대표 홈페이지 기준이라 표기가 조금 다르다
  ('공학대학' ↔ '공학대학(여수)', '전자컴퓨터공학부' 처럼 옛 이름). 괄호·공백을 빼고 맞춘 뒤,
  학부(과)는 같은 단과대학 안에서 이름 그대로 → '학부/학과/전공' 꼬리를 뗀 이름 → 전공 이름 순으로 찾는다.
  C2 학과 마스터에는 없어진 학과·연구소도 섞여 있어 다 맞지는 않는다 — 못 찾으면 화면에서 게시판을 직접 지정한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from . import config as C

_cache: dict = {"path": None, "mtime": None, "data": None}


def _path() -> Path:
    return C.LOCAL_DIRECTORY if C.LOCAL_DIRECTORY.exists() else C.BUNDLED_DIRECTORY


def load() -> dict:
    p = _path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {"colleges": []}
    if _cache["path"] != p or _cache["mtime"] != mtime:
        _cache.update(path=p, mtime=mtime, data=json.loads(p.read_text(encoding="utf-8")))
    return _cache["data"]


def _norm(s: Optional[str]) -> str:
    s = re.sub(r"\(.*?\)", "", s or "")
    return re.sub(r"[\s·・.]+", "", s)


def _cores(s: Optional[str]) -> set[str]:
    """꼬리를 뗀 이름들. '기계공학부' 는 '기계공학'+'부' 도 '기계공'+'학부' 도 되므로 둘 다 만든다
    → '기계공학전공'(→ 기계공학) · '전자컴퓨터공학과'(→ 전자컴퓨터공학) 와 맞는다."""
    n = _norm(s)
    return {x for x in (n, re.sub(r"(학부|학과|전공|계열)$", "", n), re.sub(r"[과부]$", "", n)) if len(x) >= 2}


def find_college(name: Optional[str]) -> Optional[dict]:
    n = _norm(name)
    if not n:
        return None
    cols = load().get("colleges", [])
    return next((c for c in cols if _norm(c["name"]) == n), None) \
        or next((c for c in cols if _norm(c["name"]).startswith(n) or n.startswith(_norm(c["name"]))), None)


def find_department(college: Optional[str], names: list[Optional[str]]) -> Optional[tuple[dict, dict]]:
    """(단과대학, 학부(과)) — names 는 [학과, 전공] 순서의 후보.
    단과대학을 목록에서 찾았으면 **그 안에서만** 찾는다 — 여수 '경영학과'가 광주 '경영학부'로 가는 식의 엉뚱한 연결을 막는다.
    단과대학이 목록에 없을 때('직할학부' 등)만 전체에서 찾는다."""
    cols = load().get("colleges", [])
    home = find_college(college)
    ordered = [home] if home else cols
    for n in [x for x in names if x]:
        for c in ordered:                          # 1) 이름이 같은 곳
            for d in c.get("departments", []):
                if d.get("homepage") and _norm(d["name"]) == _norm(n):
                    return c, d
        cores = _cores(n)
        for c in ordered:                          # 2) '학부/학과/전공' 을 뗀 이름이 같은 곳
            for d in c.get("departments", []):
                if d.get("homepage") and cores & _cores(d["name"]):
                    return c, d
        for c in cols:                             # 3) 학부 자체가 단과대학급인 곳 ('창의융합학부(여수)')
            if c.get("homepage") and _norm(c["name"]) == _norm(n):
                return c, {"name": c["name"], "homepage": c["homepage"]}
    return None


def resolve(scope: str, profile: Optional[dict]) -> dict:
    """원천 ③·④ 가 읽을 곳.
    반환 {status: ok|needs_profile|not_found, target(소속 이름), homepage, listedAs(목록의 이름)}"""
    p = profile or {}
    if scope == "college":
        if not p.get("college"):
            return {"status": "needs_profile", "target": None, "homepage": None, "listedAs": None}
        c = find_college(p["college"])
        if not c or not c.get("homepage"):
            return {"status": "not_found", "target": p["college"], "homepage": None, "listedAs": None}
        return {"status": "ok", "target": p["college"], "homepage": c["homepage"], "listedAs": c["name"]}
    if not p.get("department"):
        return {"status": "needs_profile", "target": None, "homepage": None, "listedAs": None}
    hit = find_department(p.get("college"), [p.get("department"), p.get("major")])
    if not hit:
        return {"status": "not_found", "target": p["department"], "homepage": None, "listedAs": None}
    return {"status": "ok", "target": p["department"], "homepage": hit[1]["homepage"], "listedAs": hit[1]["name"]}


def summary() -> dict:
    d = load()
    return {"updatedAt": d.get("updatedAt"), "colleges": len(d.get("colleges", [])),
            "departments": sum(len(c.get("departments", [])) for c in d.get("colleges", [])),
            "source": "local" if C.LOCAL_DIRECTORY.exists() else "bundled"}
