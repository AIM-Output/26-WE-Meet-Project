"""화면이 쓰는 모양 — 과목별 자료 목록 · 요약 숫자 · 파일 열기/내려받기 · 직접 추가/삭제.

계산은 전부 여기(백엔드)에서 한다. 화면은 받은 대로 그린다 (Frontend-Route 9-3).
과목 이름·색은 e클래스 과목 목록(F6)에서 받아 온다 — 캘린더·출결(F3)과 같은 색을 쓰기 위해서다.

파일을 넘겨줄 때 지키는 것 (F4-R40~R42)
  - 자료 id 로만 연다. 경로를 받지 않는다 → 주소를 만져도 다른 폴더의 파일이 나오지 않는다(catalog.abs_path).
  - 받는 쪽은 127.0.0.1 의 내 대시보드뿐이다. 밖으로 보내는 기능은 만들지 않는다.
  - 파일은 이 폴더의 보관함(`data/materials/`)에서 읽는다 — F6 의 수집 캐시를 지워도 열린다 (2026-09-30).
"""
from __future__ import annotations

import mimetypes
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from . import config as C
from . import catalog, store

CoursesGetter = Callable[[], list[dict]]


class Invalid(ValueError):
    """사용자 입력이 규칙에 어긋난다 (422)."""


class NotFound(LookupError):
    """그런 자료가 없다 (404)."""


class Conflict(RuntimeError):
    """지금은 할 수 없다 — e클래스 수집분 삭제 등 (409)."""


# '확인 필요' 로 세는 상태 — 사용자가 손쓸 수 있는 것만 (기능 타일·과목 카드 숫자).
# 텍스트 없는 이미지 PDF(ocr_needed)는 넣지 않는다: 할 수 있는 조치가 없는데 경고만 뜨면 소음이다 (2026-10-01 사용자 요청).
# 자료 줄의 안내 문구('글자가 없는 이미지 PDF 입니다 — …')는 그대로 남긴다.
ATTENTION_STATES = ("locked", "failed", "missing")

# 앱 안에서 바로 열리는 확장자. 나머지는 '내려받기'만 보여 준다 (브라우저가 못 그리면 빈 화면이 된다).
VIEWABLE_EXT = {".pdf", ".txt", ".md", ".csv", ".py", ".c", ".cpp", ".h", ".java"}
_MIME = {
    ".pdf": "application/pdf", ".md": "text/markdown; charset=utf-8", ".txt": "text/plain; charset=utf-8",
    ".csv": "text/csv; charset=utf-8", ".hwp": "application/x-hwp", ".hwpx": "application/hwp+zip",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint", ".doc": "application/msword", ".xls": "application/vnd.ms-excel",
    ".ipynb": "application/json", ".zip": "application/zip",
}
_TEXTY = {".txt", ".md", ".csv", ".py", ".c", ".cpp", ".h", ".java", ".ipynb"}
_SPLIT = re.compile(r"^(?P<short>.+?)(?:\[(?P<section>[^\]]*)\])?\s*(?:\((?P<code>[^)]*)\))?\s*$")


def media_type(ext: str) -> str:
    if ext in _MIME:
        return _MIME[ext]
    guess, _ = mimetypes.guess_type("x" + ext)
    return guess or ("text/plain; charset=utf-8" if ext in _TEXTY else "application/octet-stream")


def _split_course(name: str) -> dict:
    m = _SPLIT.match((name or "").strip())
    g = m.groupdict() if m else {}
    return {"short": (g.get("short") or name or "").strip(), "code": (g.get("code") or "").strip(),
            "section": (g.get("section") or "").strip()}


# ---------------------------------------------------------------- 한 줄 · 과목

def view(row: Any) -> dict:
    ext = row["ext"] or ""
    state = row["index_state"]
    dup = row["dup_of"]
    return {
        "id": row["id"],
        "courseId": row["course_id"],
        "course": row["course"],
        "title": row["title"],
        "source": row["source"],                                   # eclass | upload
        "kind": row["kind"],                                       # lecture | board | assignment | upload
        "kindLabel": C.KIND_LABEL.get(row["kind"], row["kind"]),
        "activity": row["activity"],
        "post": row["post"],
        "ext": ext,
        "pages": row["pages"],
        "size": row["size"],
        "sizeMB": round((row["size"] or 0) / 1024 / 1024, 2),
        "week": row["week"],
        "weekGuess": bool(row["week_guess"]),
        "stored": row["stored"],                                   # link | copy | upload | eclass(들여놓지 못함)
        "detached": bool(row["detached"]),                         # e클래스 목록에서 내려갔지만 보관본은 남아 있다
        "state": "missing" if row["missing"] else state,           # F4-R04 — 화면이 색만으로 구분하지 않게 라벨도 준다
        "stateLabel": "파일 없음" if row["missing"] else C.STATE_LABEL.get(state, state),
        "note": _note(row),
        "textState": row["text_state"],
        "dupOf": dup,
        "missing": bool(row["missing"]),
        "indexable": (ext in C.INDEXABLE_EXT and not row["missing"]
                      and state not in ("locked", "unsupported", "ocr_needed", "duplicate")),
        "viewable": ext in VIEWABLE_EXT and not row["missing"],
        # 직접 추가분과 '내려간 보관본'만 지울 수 있다. e클래스에 아직 있는 자료는 지워도 다음 스캔에 다시 들어온다
        "canDelete": row["source"] == "upload" or bool(row["detached"]),
        "eclassUrl": row["url"],
        "fileUrl": f"/api/materials/{row['id']}/file",
        "downloadUrl": f"/api/materials/{row['id']}/file?download=1",
        "addedAt": row["added_at"],
        "collectedAt": row["collected_at"],
    }


def _note(row: Any) -> str:
    if row["missing"]:
        return "파일을 찾지 못했습니다 — e클래스 동기화를 다시 하면 보관함에 다시 들여옵니다"
    if row["detached"]:
        return "e클래스 목록에서는 내려갔지만 보관본이 남아 있습니다"
    if row["dup_of"]:
        return "같은 내용의 자료가 이미 있습니다"
    if row["index_state"] == "locked":
        return "암호가 걸려 있어 열어 볼 수는 있어도 분석은 못 합니다"
    if row["index_state"] == "ocr_needed":
        return "글자가 없는 이미지 PDF 입니다 — 요약·문제 생성에서 제외됩니다"
    if row["index_state"] == "unsupported":
        return f"{row['ext']} 는 분석 대상이 아닙니다 (목록·열람은 됩니다)"
    return row["meta_error"] or ""


def _course_row(cid: str, name: str, known: dict[str, dict], rows: list[Any]) -> dict:
    base = known.get(cid) or {"id": cid, "name": name, "color": None, **_split_course(name)}
    kinds = {k: 0 for k in C.KIND_LABEL}
    states: dict[str, int] = {}
    pages = 0
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        st = "missing" if r["missing"] else r["index_state"]
        states[st] = states.get(st, 0) + 1
        pages += r["pages"] or 0
    attention = sum(states.get(k, 0) for k in ATTENTION_STATES)
    collected = [r["collected_at"] for r in rows if r["collected_at"]]
    return {
        "id": cid, "name": base.get("name") or name, "short": base.get("short") or name,
        "code": base.get("code", ""), "section": base.get("section", ""), "color": base.get("color"),
        "files": len(rows), "pages": pages, "byKind": kinds, "states": states,
        "uploads": sum(1 for r in rows if r["source"] == "upload"),
        "ready": states.get("done", 0), "waiting": states.get("pending", 0), "attention": attention,
        "lastCollectedAt": max(collected) if collected else None,
    }


# ---------------------------------------------------------------- 목록

def overview(con: sqlite3.Connection, get_courses: Optional[CoursesGetter] = None,
             course: Optional[str] = None, kind: Optional[str] = None, q: Optional[str] = None,
             scan: Optional[dict] = None) -> dict:
    """자료 화면 한 판 — 과목 요약(목록 화면) + 고른 과목의 자료들 (Frontend-Route 9-2·9-3)."""
    known = {str(c["id"]): c for c in (_safe_courses(get_courses))}
    rows = store.all_rows(con)
    by_course: dict[str, list[Any]] = {}
    for r in rows:
        by_course.setdefault(r["course_id"], []).append(r)

    order = [cid for cid in known if cid in by_course] + [cid for cid in by_course if cid not in known]
    courses = [_course_row(cid, (by_course[cid][0]["course"] if by_course[cid] else ""), known, by_course[cid])
               for cid in order]
    # 자료가 아직 없는 과목도 목록에는 보여 준다 ("강의자료가 없습니다" 를 그 자리에서 말해 준다)
    courses += [_course_row(cid, c.get("name", ""), known, []) for cid, c in known.items() if cid not in by_course]

    picked = [r for r in rows if (not course or r["course_id"] == course) and (not kind or r["kind"] == kind)]
    if q:
        needle = q.strip().lower()
        picked = [r for r in picked
                  if needle in (r["title"] or "").lower() or needle in (r["activity"] or "").lower()
                  or needle in (r["post"] or "").lower()]
    return {
        "updatedAt": store.updated_at(con),
        "scannedAt": store.get_meta(con, "scanned_at"),
        "scan": scan,
        "source": source_block(),
        "limits": {"maxFileMB": C.MAX_FILE_MB, "allowedExt": sorted(C.ALLOWED_EXT),
                   "indexableExt": sorted(C.INDEXABLE_EXT)},
        "totals": totals(rows),
        "courses": courses,
        "materials": [view(r) for r in picked],
        "filter": {"course": course, "kind": kind, "q": q or ""},
        "analysis": {"available": False,
                     "note": "요약·예상 문제·질문은 아직 붙이지 않았습니다 — 자료 모으기·열람까지가 1차입니다"},
    }


def totals(rows: Iterable[Any]) -> dict:
    rows = list(rows)
    kinds = {k: 0 for k in C.KIND_LABEL}
    states: dict[str, int] = {}
    pages = size = 0
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        st = "missing" if r["missing"] else r["index_state"]
        states[st] = states.get(st, 0) + 1
        pages += r["pages"] or 0
        size += r["size"] or 0
    stored: dict[str, int] = {}
    for r in rows:
        stored[r["stored"] or "eclass"] = stored.get(r["stored"] or "eclass", 0) + 1
    return {
        "files": len(rows), "pages": pages, "sizeMB": round(size / 1024 / 1024, 1),
        "courses": len({r["course_id"] for r in rows}), "byKind": kinds, "states": states,
        "stored": stored,                                # link · copy · upload · eclass(들여놓지 못함)
        "detached": sum(1 for r in rows if r["detached"]),
        "uploads": sum(1 for r in rows if r["source"] == "upload"),
        "attention": sum(states.get(k, 0) for k in ATTENTION_STATES),
    }


def source_block() -> dict:
    """어디서 온 자료인지 — 화면 상단 안내와 '자료 가져오기'(F6 동기화) 버튼이 쓴다."""
    exists = C.ECLASS_MANIFEST.exists()
    at = None
    if exists:
        at = datetime.fromtimestamp(C.ECLASS_MANIFEST.stat().st_mtime).isoformat(timespec="seconds")
    return {"eclass": {"available": exists, "dataDir": str(C.ECLASS_DATA_DIR), "manifestAt": at,
                       "note": "e클래스에서 파일을 받아오는 일은 F6 수집이 합니다 (대시보드의 'e클래스 동기화')"},
            "libraryDir": str(C.LIBRARY_DIR),
            "uploadDir": str(C.UPLOAD_DIR)}


def status_summary(con: sqlite3.Connection) -> dict:
    """/api/status 의 materials 칸 — 기능 타일 숫자 (F4-S01)."""
    rows = store.all_rows(con)
    t = totals(rows)
    return {"available": True, "updatedAt": store.updated_at(con), "scannedAt": store.get_meta(con, "scanned_at"),
            "files": t["files"], "pages": t["pages"], "courses": t["courses"], "uploads": t["uploads"],
            "attention": t["attention"], "eclassAvailable": C.ECLASS_MANIFEST.exists()}


def detail(con: sqlite3.Connection, material_id: str) -> dict:
    row = _row(con, material_id)
    out = view(row)
    if row["dup_of"]:
        other = store.row(con, row["dup_of"])
        out["dupWith"] = {"id": other["id"], "title": other["title"]} if other else None
    same = con.execute("SELECT id, title FROM materials WHERE course_id = ? AND id != ? AND activity = ? "
                       "ORDER BY title", (row["course_id"], row["id"], row["activity"]))
    out["sameActivity"] = [{"id": r["id"], "title": r["title"]} for r in same] if row["activity"] else []
    out["path"] = str(catalog.material_path(row))
    out["originPath"] = str(catalog.abs_path("eclass", row["origin_path"])) if row["origin_path"] else ""
    return out


# ---------------------------------------------------------------- 파일 열기

def file_target(con: sqlite3.Connection, material_id: str) -> tuple[Path, str, str]:
    """(실제 경로, 내려받을 이름, MIME). 파일이 없으면 404 로 알린다."""
    row = _row(con, material_id)
    path = catalog.material_path(row)
    if not path.is_file():
        raise NotFound(f"파일을 찾지 못했습니다: {row['title']}")
    return path, row["title"], media_type(row["ext"])


# ---------------------------------------------------------------- 직접 추가·삭제

_BAD = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def safe_name(name: str) -> str:
    base = _BAD.sub("_", Path(str(name or "")).name).strip(" .")
    return base[:120] or "파일"


def upload_target(con: sqlite3.Connection, course_id: str, filename: str,
                  get_courses: Optional[CoursesGetter] = None) -> Path:
    """직접 추가할 파일이 들어갈 자리를 정한다 (F4-R02). 같은 이름이 있으면 뒤에 번호를 붙인다."""
    course_id = (course_id or "").strip()
    if not course_id:
        raise Invalid("과목을 지정해 주세요")
    if not re.fullmatch(r"[A-Za-z0-9_:-]{1,40}", course_id):
        raise Invalid(f"과목 id 가 이상합니다: {course_id}")
    known = {str(c["id"]) for c in _safe_courses(get_courses)}
    if known and course_id not in known and not _has_course(con, course_id):
        raise Invalid("이 과목을 찾지 못했습니다 — e클래스 동기화 후 다시 시도하세요")
    name = safe_name(filename)
    ext = Path(name).suffix.lower()
    if ext not in C.ALLOWED_EXT:
        raise Invalid(f"{ext or '이 형식'} 은 받지 않습니다 — 문서 파일만 추가할 수 있습니다")
    dest = C.UPLOAD_DIR / course_id / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    stem, n = Path(name).stem, 2
    while dest.exists():
        dest = dest.with_name(f"{stem} ({n}){ext}")
        n += 1
    return dest


def finish_upload(con: sqlite3.Connection, dest: Path, get_courses: Optional[CoursesGetter] = None) -> dict:
    """파일을 다 쓴 뒤 — 목록에 넣고 그 자료를 돌려준다."""
    catalog.scan(con)
    rel = f"{dest.parent.name}/{dest.name}"
    row = store.row(con, catalog.material_id(f"upload:{rel}"))
    if row is None:
        raise Conflict("자료 목록에 넣지 못했습니다")
    return view(row)


def delete(con: sqlite3.Connection, material_id: str) -> dict:
    """직접 추가한 파일과 '내려간 보관본'만 지운다 (F4-R08 · 9-3).

    e클래스에 아직 올라와 있는 자료를 지우는 것은 막는다 — 지워도 다음 스캔에 보관함으로 다시 들어와
    지운 것처럼 보이지 않는다. 정말 안 보이게 하려면 e클래스에서 내려간 뒤에."""
    row = _row(con, material_id)
    if row["source"] != "upload" and not row["detached"]:
        raise Conflict("e클래스에 올라와 있는 자료입니다 — 지워도 다음 동기화 때 보관함에 다시 들어옵니다")
    path = catalog.material_path(row)
    if path.is_file():
        path.unlink()
    parent = path.parent
    while parent.is_dir() and not any(parent.iterdir()) and parent not in (C.UPLOAD_DIR, C.LIBRARY_DIR):
        parent.rmdir()                                   # 빈 과목·활동 폴더는 남기지 않는다
        parent = parent.parent
    store.delete(con, material_id)
    store.touch(con)
    return {"deleted": material_id, "title": row["title"]}


# ---------------------------------------------------------------- 도구

def _row(con: sqlite3.Connection, material_id: str) -> Any:
    row = store.row(con, material_id)
    if row is None:
        raise NotFound(f"그런 자료가 없습니다: {material_id}")
    return row


def _has_course(con: sqlite3.Connection, course_id: str) -> bool:
    return con.execute("SELECT 1 FROM materials WHERE course_id = ? LIMIT 1", (course_id,)).fetchone() is not None


def _safe_courses(get_courses: Optional[CoursesGetter]) -> list[dict]:
    if get_courses is None:
        return _courses_from_file()
    try:
        return [c for c in (get_courses() or []) if isinstance(c, dict) and c.get("id")]
    except Exception:                                    # noqa: BLE001 — 과목 목록을 못 받아도 자료는 보여 준다
        return _courses_from_file()


def _courses_from_file() -> list[dict]:
    """대시보드 밖(명령줄·테스트)에서 부를 때 — e클래스 courses.json 을 직접 읽는다."""
    out = []
    for i, (cid, name) in enumerate(catalog.course_names().items()):
        out.append({"id": cid, "name": name, **_split_course(name),
                    "color": C.COURSE_PALETTE[i % len(C.COURSE_PALETTE)] if C.COURSE_PALETTE else None})
    return out
