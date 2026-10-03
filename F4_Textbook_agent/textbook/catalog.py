"""자료 목록 만들기 — F6 수집 결과(manifest.json) + 직접 추가한 파일 → materials 표 (F4-R01·R02·R05~R08).

내려받는 일은 하지 않는다. e클래스에서 파일을 가져오는 것은 F6_Eclass_agent 몫이고(로그인은 C3),
여기서는 **그 결과를 이 폴더의 보관함(`data/materials/`)으로 들여놓고** 과목별 자료 목록으로 세운다.

한 번의 스캔이 하는 일
  0. 수집분을 보관함으로 들여놓는다 — **하드링크 우선, 안 되면 복사**(`place`). 같은 드라이브면 디스크를 더 쓰지 않는다.
     들여놓지 못하면 F6 자리를 그대로 가리킨 채 사유를 남긴다(자료가 안 보이는 것보다 낫다).
  1. manifest.json 의 파일 + data/uploads 의 파일을 모은다 (허용 확장자만).
  2. 파일 크기·수정 시각이 그대로면 **다시 읽지 않는다**(쪽수·해시 캐시). 바뀌었으면 다시 읽는다 (F4-R07).
  3. 같은 내용(해시)이 여럿이면 먼저 들어온 하나만 남기고 나머지는 `duplicate` 로 표시한다 (F4 8절).
  4. 붙여도 소용없는 것을 미리 가른다 — 암호(`locked`) · 텍스트 없음(`ocr_needed`) · 확장자(`unsupported`) (F4-R06).
  5. 파일이 사라졌으면 지우지 않고 `missing` 으로 둔다 — 목록에서 갑자기 없어지면 사용자가 더 헷갈린다.
  6. e클래스 목록에서 내려간 자료도 **보관본이 있으면 남긴다**(`detached`). 이때만 사용자가 지울 수 있다.
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Optional

from . import config as C
from . import docmeta, store


# ---------------------------------------------------------------- 경로

def root_dir(root: str) -> Path:
    """자료가 실제로 있는 폴더. `library` 보관함 · `upload` 직접 추가 · `eclass` 들여놓지 못한 예외."""
    if root == "library":
        return C.LIBRARY_DIR
    if root == "upload":
        return C.UPLOAD_DIR
    return C.ECLASS_ROOT


def abs_path(root: str, rel: str) -> Path:
    """root 기준 상대경로 → 실제 경로. **밖으로 나가는 경로는 거부한다**(자료 id 로 남의 파일을 읽지 못하게)."""
    base = root_dir(root).resolve()
    p = (base / str(rel).replace("\\", "/")).resolve()
    if not p.is_relative_to(base):
        raise ValueError(f"자료 폴더 밖의 경로입니다: {rel}")
    return p


def material_path(row: Any) -> Path:
    return abs_path(row["root"], row["rel_path"])


def material_id(key: str) -> str:
    return "mt:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------- e클래스 수집 결과 읽기

def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def manifest_stamp() -> str:
    try:
        st = C.ECLASS_MANIFEST.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return ""


def activity_mods() -> dict[str, str]:
    """활동 번호(cmid) → 모듈 이름. 자료의 종류(강의자료·게시판·과제)를 가르는 기준."""
    out: dict[str, str] = {}
    for c in _read_json(C.ECLASS_COURSES, []) or []:
        if not isinstance(c, dict):
            continue
        for a in c.get("activities") or []:
            if isinstance(a, dict) and a.get("cmid"):
                out[str(a["cmid"])] = str(a.get("mod", ""))
    return out


def course_names() -> dict[str, str]:
    return {str(c.get("id")): str(c.get("name", "")) for c in _read_json(C.ECLASS_COURSES, []) or []
            if isinstance(c, dict) and c.get("id")}


def kind_of(entry: dict, mods: dict[str, str]) -> str:
    """강의자료 / 게시판 첨부 / 과제 첨부. 활동 모듈이 먼저, 없으면 경로 모양으로 본다."""
    if entry.get("post"):
        return "board"
    mod = mods.get(str(entry.get("cmid", "")), "")
    if mod in C.BOARD_MODULES:
        return "board"
    if mod in C.ASSIGN_MODULES:
        return "assignment"
    if mod in C.RESOURCE_MODULES:
        return "lecture"
    parts = str(entry.get("path", "")).replace("\\", "/").split("/")
    if "게시판" in parts:
        return "board"
    if "과제" in parts:
        return "assignment"
    return "lecture"


# ---------------------------------------------------------------- 보관함에 들여놓기

def library_rel(eclass_rel: str) -> str:
    """F6 의 'data/<과목>/<활동>/<파일>' → 보관함 안의 '<과목>/<활동>/<파일>' (같은 짜임새를 유지한다)."""
    parts = [x for x in str(eclass_rel).replace("\\", "/").split("/") if x not in ("", ".")]
    if parts and parts[0] == "data":
        parts = parts[1:]
    return "/".join(parts)


def _same_file(a, b) -> bool:
    """같은 파일로 볼 수 있나 — 크기가 같고 수정 시각이 2초 안쪽(복사는 시각을 그대로 옮긴다)."""
    return a.st_size == b.st_size and abs(a.st_mtime - b.st_mtime) <= 2


def _kind_of_stored(st) -> str:
    return "link" if getattr(st, "st_nlink", 1) > 1 else "copy"


def _link_or_copy(src: Path, dest: Path) -> tuple[str, str]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(src, dest)                               # 같은 드라이브면 디스크를 더 쓰지 않는다
        return "link", ""
    except (OSError, NotImplementedError, AttributeError):
        pass                                             # 다른 드라이브·파일 시스템 → 복사
    try:
        shutil.copy2(src, dest)
        return "copy", ""
    except OSError as e:
        return "eclass", f"보관함에 들여놓지 못했습니다: {e}"


def place(cand: dict, previous: Optional[str] = None) -> tuple[str, str]:
    """수집분 하나를 보관함으로 들여놓는다 → (stored, 안내 문구).

    stored: `link`·`copy` 들여놨다 · `eclass` 못 들여놔서 F6 자리를 그대로 가리킨다.
    원본(수집 캐시)이 사라져도 보관본이 있으면 그대로 쓴다 — **F6 data 를 지워도 자료는 남는다.**"""
    try:
        src = abs_path("eclass", cand["origin_path"])
        dest = abs_path("library", cand["rel_path"])
    except ValueError as e:
        return "eclass", str(e)
    sst = src.stat() if src.is_file() else None
    if dest.is_file():
        dst = dest.stat()
        if sst is None or _same_file(sst, dst):
            return previous if previous in ("link", "copy") else _kind_of_stored(dst), ""
        try:
            dest.unlink()                                # 원본이 바뀌었다 (F4-R07) → 다시 들여놓는다
        except OSError as e:
            return _kind_of_stored(dst), f"보관본을 갱신하지 못했습니다: {e}"
    if sst is None:
        return "eclass", ""                              # 원본도 보관본도 없다 → '파일 없음' 으로 보인다
    return _link_or_copy(src, dest)


# ---------------------------------------------------------------- 주차 추정

_WEEK_RE = [
    re.compile(r"(\d{1,2})\s*주\s*차"),                    # 3주차
    re.compile(r"(\d{1,2})\s*주(?![가-힣])"),              # 3주 ; 오리엔테이션 · 5주. 삼국지
    re.compile(r"(\d{1,2})\s*강(?![가-힣])"),              # 4강 git 기본사용법
    re.compile(r"week\s*_?-?\s*(\d{1,2})", re.I),          # Week1 · Week 2_2
    re.compile(r"^(\d{1,2})[-_.](?=\S)"),                   # 2-1_소프트웨어품질1 ('1. 샘플…' 처럼 뒤가 빈칸이면 제외)
    re.compile(r"^[A-Za-z]{2,10}[_ -]?(\d{2})(?![0-9])"),  # os04_process · comnet05_L3
]


def week_of(*names: Optional[str]) -> tuple[Optional[int], bool]:
    """이름에서 주차를 추정한다 → (주차, 추정인가). 못 찾으면 (None, True).

    자료 이름은 학교·교수마다 제각각이라 **맞히면 좋고 틀려도 화면에 '추정'이라고 적는다.**
    범위 선택(F4-R14)이 붙을 때 기본값으로 쓰고, 사용자가 고칠 수 있게 할 자리다."""
    for name in names:
        if not name:
            continue
        text = Path(str(name)).stem if "." in str(name) else str(name)
        for rx in _WEEK_RE:
            m = rx.search(text)
            if m:
                n = int(m.group(1))
                if 1 <= n <= 20:
                    return n, True
    return None, True


# ---------------------------------------------------------------- 스캔

def _candidates(mods: dict[str, str], names: dict[str, str]) -> list[dict]:
    """이번 스캔에서 목록에 있어야 할 자료들 — e클래스 수집분 + 직접 추가분."""
    out: list[dict] = []
    manifest = _read_json(C.ECLASS_MANIFEST, {}) or {}
    for key, e in (manifest.get("files") or {}).items():
        if not isinstance(e, dict) or not e.get("path"):
            continue
        rel = str(e["path"]).replace("\\", "/")
        ext = Path(rel).suffix.lower()
        if ext not in C.ALLOWED_EXT:
            continue
        course_id = str(e.get("course_id", "")) or "unknown"
        title = Path(rel).name
        week, guess = week_of(title, e.get("post"), e.get("activity"))
        out.append({
            "id": material_id(key), "source_key": key, "course_id": course_id,
            "course": names.get(course_id) or str(e.get("course", "")), "title": title,
            # 자리는 보관함(data/materials/<과목>/<활동>/<파일>), 어디서 왔는지는 origin_path 에 남긴다
            "root": "library", "rel_path": library_rel(rel), "origin_path": rel,
            "source": "eclass", "kind": kind_of(e, mods), "ext": ext,
            "activity": str(e.get("activity", "")), "post": str(e.get("post", "")),
            # 수집기가 HTML 속성에서 그대로 떠 온 주소라 '&amp;' 가 남아 있을 수 있다 (2026-09-30 실측: 과제 첨부)
            "url": html.unescape(str(e.get("url", ""))), "week": week, "week_guess": int(guess),
            "collected_at": e.get("downloaded_at"),
        })
    for p in (sorted(C.UPLOAD_DIR.glob("*/*")) if C.UPLOAD_DIR.exists() else []):
        if not p.is_file():
            continue
        course_id = p.parent.name
        rel = f"{course_id}/{p.name}"
        week, guess = week_of(p.name)
        out.append({
            "id": material_id(f"upload:{rel}"), "source_key": f"upload:{rel}", "course_id": course_id,
            "course": names.get(course_id, ""), "title": p.name,
            "root": "upload", "rel_path": rel, "origin_path": "", "stored": "upload",
            "source": "upload", "kind": "upload", "ext": p.suffix.lower(),
            "activity": "", "post": "", "url": "", "week": week, "week_guess": int(guess),
            "collected_at": None,
        })
    return out


def _derive_state(ext: str, meta: dict, previous: Optional[str], reread: bool) -> str:
    """인덱싱 상태 — 1차에는 파이프라인이 없으므로 '대기'가 기본. 해 봐야 소용없는 것만 미리 가른다."""
    if meta.get("locked"):
        return "locked"
    if ext not in C.INDEXABLE_EXT:
        return "unsupported"
    if meta.get("textState") == "none":
        return "ocr_needed"
    if not reread and previous in ("running", "done", "failed"):
        return previous                                  # 내용이 그대로면 인덱싱 결과를 지우지 않는다 (F4-R07)
    return "pending"


def _read_meta(path: Path, ext: str, size: int) -> dict:
    if size > C.MAX_SCAN_MB * 1024 * 1024:
        return {"pages": None, "textState": "unknown", "locked": False,
                "error": f"{C.MAX_SCAN_MB}MB 가 넘어 읽지 않았습니다", "hash": None}
    meta = dict(docmeta.read(path, ext))
    try:
        meta["hash"] = docmeta.file_hash(path)
    except OSError as e:
        meta["hash"] = None
        meta["error"] = meta.get("error") or str(e)
    return meta


_WATCH = ("size", "mtime", "pages", "text_state", "content_hash", "index_state", "missing",
          "title", "course_id", "kind", "week", "root", "rel_path", "detached")


def scan(con: sqlite3.Connection, force: bool = False) -> dict:
    """자료 목록을 파일 상태에 맞춘다. 바뀐 것이 없으면 updated_at 을 올리지 않는다(화면이 다시 부르지 않게)."""
    t0 = time.perf_counter()
    mods, names = activity_mods(), course_names()
    before = {r["id"]: r for r in store.all_rows(con)}
    stats = {"files": 0, "new": 0, "changed": 0, "missing": 0, "removed": 0, "reread": 0,
             "placed": 0, "detached": 0}
    seen: set[str] = set()

    for cand in _candidates(mods, names):
        seen.add(cand["id"])
        old = before.get(cand["id"])
        place_error = ""
        if cand["source"] == "eclass":                   # 보관함으로 들여놓는다 (없거나 바뀌었을 때만 실제로 움직인다)
            stored, place_error = place(cand, old["stored"] if old else None)
            cand["stored"] = stored
            if stored == "eclass":                       # 못 들여놨다 → F6 자리를 그대로 가리킨다
                cand["root"], cand["rel_path"] = "eclass", cand["origin_path"]
            elif old is not None and old["stored"] != stored:
                stats["placed"] += 1
            elif old is None:
                stats["placed"] += 1
        cand["detached"] = 0                             # 목록에 있으니 다시 붙는다
        path: Optional[Path]
        try:
            path = abs_path(cand["root"], cand["rel_path"])
            st = path.stat()
            size, mtime, missing = st.st_size, st.st_mtime, 0
        except (OSError, ValueError):
            path, size, mtime, missing = None, (old["size"] if old else 0), (old["mtime"] if old else None), 1

        reread = not missing and (force or old is None or old["missing"] or old["meta_state"] != "done"
                                  or old["size"] != size or old["mtime"] != mtime)
        if reread and path is not None:
            meta = _read_meta(path, cand["ext"], size)
            stats["reread"] += 1
        elif old is not None:
            meta = {"pages": old["pages"], "textState": old["text_state"], "hash": old["content_hash"],
                    "locked": old["index_state"] == "locked", "error": old["meta_error"]}
        else:
            meta = {"pages": None, "textState": "unknown", "hash": None, "locked": False, "error": ""}

        unreadable = bool(meta.get("error")) and meta.get("pages") is None and cand["ext"] in C.PAGED_EXT
        rowd = {
            **cand, "size": size, "mtime": mtime, "missing": missing,
            "pages": meta.get("pages"), "text_state": meta.get("textState") or "unknown",
            "content_hash": meta.get("hash"),
            "meta_state": "pending" if missing else ("failed" if unreadable else "done"),
            "meta_error": place_error or str(meta.get("error") or ""),
            "index_state": _derive_state(cand["ext"], meta, old["index_state"] if old else None, reread),
            "index_error": "" if reread else (old["index_error"] if old else ""),
            "dup_of": None,
            "added_at": old["added_at"] if old else store.now(),
            "seen_at": store.now(),
        }
        if old is None:
            stats["new"] += 1
        elif any(old[k] != rowd[k] for k in _WATCH):
            stats["changed"] += 1
        stats["missing"] += missing
        store.upsert(con, rowd)
        stats["files"] += 1

    for mid in set(before) - seen:
        row = before[mid]
        if row["root"] == "library" and _exists(row):    # e클래스에서 내려갔어도 **보관본은 내 것**이다
            if not row["detached"]:
                con.execute("UPDATE materials SET detached = 1, seen_at = ? WHERE id = ?", (store.now(), mid))
                stats["detached"] += 1
                stats["changed"] += 1
            continue
        store.delete(con, mid)                           # 보관본도 없다 → 목록에서 지운다
        stats["removed"] += 1

    stats["duplicates"] = _mark_duplicates(con)
    moved = stats["new"] + stats["changed"] + stats["removed"]
    stats["updatedAt"] = store.touch(con) if moved else store.updated_at(con)
    store.set_meta(con, scanned_at=store.now(), manifest_stamp=manifest_stamp())
    stats["elapsedMs"] = round((time.perf_counter() - t0) * 1000)
    return stats


def _exists(row: Any) -> bool:
    try:
        return material_path(row).is_file()
    except (OSError, ValueError):
        return False


def _mark_duplicates(con: sqlite3.Connection) -> int:
    """같은 내용의 파일은 먼저 들어온 하나만 남긴다 (F4 8절 '같은 파일 중복')."""
    groups: dict[str, list[sqlite3.Row]] = {}
    for r in con.execute("SELECT * FROM materials WHERE content_hash IS NOT NULL AND missing = 0 "
                         "ORDER BY added_at, rowid"):        # 먼저 들어온 것 = 목록에 먼저 자리 잡은 것
        groups.setdefault(r["content_hash"], []).append(r)
    dups = 0
    for rows in groups.values():
        keep = rows[0]["id"]
        for r in rows[1:]:
            con.execute("UPDATE materials SET dup_of = ?, index_state = 'duplicate' WHERE id = ?", (keep, r["id"]))
            dups += 1
    return dups


def upload_stamp() -> str:
    """직접 추가 폴더의 상태 — 파일 수 + 가장 최근 수정 시각 (몇 개뿐이라 훑어도 싸다)."""
    try:
        files = [p.stat() for p in C.UPLOAD_DIR.glob("*/*") if p.is_file()]
    except OSError:
        return ""
    return f"{len(files)}:{max((s.st_mtime_ns for s in files), default=0)}"


def ensure_scan(con: sqlite3.Connection, force: bool = False) -> dict:
    """화면이 자료를 물어볼 때마다 부른다.

    manifest.json 과 직접 추가 폴더가 그대로면 **훑지 않는다** — /api/status 는 1분(수집 중에는 3초)마다
    오는데 그때마다 파일 43개를 stat 할 이유가 없다. 파일을 밖에서 바꿔치기했을 때를 위해 '다시 훑기'(force)를 둔다."""
    stamp = f"{manifest_stamp()}|{upload_stamp()}"
    if not force and stamp == store.get_meta(con, "scan_stamp") and store.get_meta(con, "scanned_at"):
        n = con.execute("SELECT COUNT(*) FROM materials").fetchone()[0]
        return {"skipped": True, "files": n, "new": 0, "changed": 0, "removed": 0, "missing": 0, "reread": 0,
                "duplicates": 0, "elapsedMs": 0, "updatedAt": store.updated_at(con)}
    stats = scan(con, force=force)
    store.set_meta(con, scan_stamp=stamp)
    stats["skipped"] = False
    return stats
