"""학과 마스터 — 읽기·찾기·갱신 (C2 4절 departments.json, C2-R01·R02·R10). 표준 라이브러리만.

파일 두 개
  master/departments.json       저장소에 넣어 두는 스냅숏 (처음 실행에도 네트워크 없이 뜬다, 5-2 '오프라인')
  data/master/departments.json  '학과 목록 갱신'으로 내려받은 것 — 있으면 이것을 쓴다
갱신할 때 새 목록에서 사라진 학과·전공은 지우지 않고 retired=true 로 남긴다 (C2-R10 — 옛 코드로 저장된 프로필이 깨지지 않게).

화면(학과 선택기)에는 계층을 펼친 목록(entries)을 준다. 한 줄 = 고를 수 있는 한 곳.
  - 전공이 여러 개인 학부: '인공지능학부 (전공 배정 전)' 한 줄 + 전공마다 한 줄
  - 전공이 학과 이름과 같은 하나뿐(융합전공 등): 한 줄 (전공 코드는 저장하되 이름은 한 번만)
  - 전공이 없는 학과: 한 줄
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Optional

from . import config as C

NOT_DEPARTMENT = re.compile(r"사업단|센터|공장|연구소|연구원|위원회|\(주\)|교직부")
_lock = threading.Lock()
_cache: dict = {"mtime": None, "path": None, "data": None, "entries": None}


def _path() -> Path:
    return C.LOCAL_MASTER if C.LOCAL_MASTER.exists() else C.BUNDLED_MASTER


def load() -> dict:
    """마스터 dict (파일이 바뀌었으면 다시 읽는다). 둘 다 없으면 빈 마스터."""
    p = _path()
    try:
        mtime = p.stat().st_mtime
    except OSError:
        return {"updatedAt": None, "year": None, "colleges": []}
    with _lock:
        if _cache["path"] != p or _cache["mtime"] != mtime:
            _cache.update(path=p, mtime=mtime, data=json.loads(p.read_text(encoding="utf-8")), entries=None)
        return _cache["data"]


def source() -> str:
    return "local" if C.LOCAL_MASTER.exists() else ("bundled" if C.BUNDLED_MASTER.exists() else "none")


def entries() -> list[dict]:
    """학과 선택기용 펼친 목록."""
    data = load()
    with _lock:
        if _cache["entries"] is not None and _cache["data"] is data:
            return _cache["entries"]
    out: list[dict] = []
    for col in data.get("colleges", []):
        for d in col.get("departments", []):
            if NOT_DEPARTMENT.search(d["name"]) and not d.get("majors"):
                continue            # 교육과정 DB 에 섞여 있는 조직('국책사업단', '○○산학협력센터', '부속공장') — 학생 소속이 아니다
            majors = d.get("majors", [])
            base = {"collegeCode": col["code"], "college": col["name"], "deptCode": d["code"], "department": d["name"]}
            retired_d = bool(d.get("retired") or col.get("retired"))
            if len(majors) == 1 and majors[0]["name"] == d["name"]:
                m = majors[0]
                out.append({**base, "code": m["code"], "majorCode": m["code"], "major": None,
                            "retired": retired_d or bool(m.get("retired"))})
                continue
            out.append({**base, "code": d["code"], "majorCode": None, "major": None, "retired": retired_d,
                        "note": "전공 배정 전" if majors else None})
            for m in majors:
                out.append({**base, "code": m["code"], "majorCode": m["code"], "major": m["name"],
                            "retired": retired_d or bool(m.get("retired"))})
    for e in out:
        e["path"] = " › ".join(x for x in (e["college"], e["department"], e["major"]) if x)
    with _lock:
        _cache["entries"] = out
    return out


def find(dept_code: Optional[str], major_code: Optional[str] = None) -> Optional[dict]:
    """코드로 한 줄 찾기. 전공 코드가 있으면 그 전공, 없으면 학과(전공 배정 전) 줄."""
    if not dept_code:
        return None
    for e in entries():
        if e["deptCode"] == dept_code and (e["majorCode"] == major_code or (major_code is None and e["majorCode"] is None)):
            return e
    if major_code is None:           # 전공이 하나뿐인 학과는 학과 줄이 따로 없다 → 그 한 줄
        rows = [e for e in entries() if e["deptCode"] == dept_code]
        if len(rows) == 1:
            return rows[0]
    return None


def by_code(code: Optional[str]) -> Optional[dict]:
    """학과든 전공이든 선택기 한 줄의 코드로 (옛 화면은 전공 코드를 deptCode 칸에 저장했다)."""
    return next((e for e in entries() if e["code"] == code), None) if code else None


def find_by_names(college: Optional[str], department: Optional[str]) -> Optional[dict]:
    """학사정보시스템의 '주전공 : AI융합대학 / 인공지능학부' 를 마스터 한 줄로 (학과 줄, 폐지 제외)."""
    if not department:
        return None
    norm = lambda s: "".join((s or "").split())          # noqa: E731
    rows = [e for e in entries() if norm(e["department"]) == norm(department) and not e["retired"]
            and (e["majorCode"] is None or e["major"] is None)]
    if college:
        by_col = [e for e in rows if norm(e["college"]) == norm(college)]
        rows = by_col or rows
    return rows[0] if len(rows) == 1 else None


def merge_retired(new: dict, old: Optional[dict]) -> dict:
    """새 목록에 없는 옛 단과대·학과·전공을 retired=true 로 덧붙인다 (C2-R10)."""
    if not old:
        return new
    cols = {c["code"]: c for c in new["colleges"]}
    for oc in old.get("colleges", []):
        nc = cols.get(oc["code"])
        if nc is None:
            cols[oc["code"]] = {**oc, "retired": True}
            new["colleges"].append(cols[oc["code"]])
            continue
        depts = {d["code"]: d for d in nc["departments"]}
        for od in oc.get("departments", []):
            nd = depts.get(od["code"])
            if nd is None:
                nc["departments"].append({**od, "retired": True})
                continue
            have = {m["code"] for m in nd.get("majors", [])}
            for om in od.get("majors", []):
                if om["code"] not in have:
                    nd.setdefault("majors", []).append({**om, "retired": True})
    return new


def save_local(data: dict) -> None:
    C.LOCAL_MASTER.parent.mkdir(parents=True, exist_ok=True)
    tmp = C.LOCAL_MASTER.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(C.LOCAL_MASTER)


def summary() -> dict:
    data = load()
    es = entries()
    return {"updatedAt": data.get("updatedAt"), "year": data.get("year"), "source": source(),
            "colleges": len(data.get("colleges", [])), "count": len(es)}
