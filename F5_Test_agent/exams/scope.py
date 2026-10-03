"""범위 → 분량 — F4 강의자료의 쪽수 합계 (F5-R10·R11, D2).

F4_Textbook_agent 를 **읽기만** 한다. 폴더를 sys.path 에 넣고 `textbook.store`·`textbook.catalog` 를
import 한다(다른 기능이 서로를 빌려 쓰는 방식 — F2→C2 · F6→C3 와 같다). `textbook.api` 는 부르지 않는다:
그쪽은 fastapi 를 필요로 해서 명령줄에서 쓸 수 없다.

쪽수에서 빼는 것 (F4 8절의 판정을 그대로 믿는다)
  - `missing`  파일이 사라진 자료
  - `dup_of`   같은 내용의 중복 자료 (두 번 세지 않는다)
  - 쪽수를 못 센 자료(`pages` 없음)는 합계에서 빼고 **몇 개인지 알려 준다** — 화면이 '직접 입력'을 권한다.
    틀린 숫자보다 모른다고 말하는 것이 낫다 (F4 의 쪽수 규칙과 같은 태도).

F4 가 없거나 못 불러와도 F5 는 돌아간다 — `available: False` 로 알리고 사용자가 분량을 직접 넣는다 (F5-R11).
"""
from __future__ import annotations

import sys
from typing import Any, Optional

from . import config as C

_error: Optional[str] = None
_f4: Any = None
_tried = False


def _load() -> Any:
    """F4 의 자료 목록 모듈 (store·catalog·config). 한 번만 시도한다."""
    global _f4, _error, _tried
    if _tried:
        return _f4
    _tried = True
    if not (C.F4_AGENT_DIR / "textbook" / "store.py").exists():
        _error = f"F4_Textbook_agent 가 없습니다: {C.F4_AGENT_DIR}"
        return None
    if str(C.F4_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F4_AGENT_DIR))
    try:
        from textbook import catalog as f4_catalog      # type: ignore[import-not-found]
        from textbook import store as f4_store          # type: ignore[import-not-found]
        _f4 = (f4_store, f4_catalog)
    except Exception as e:                              # noqa: BLE001 — F4 가 못 뜨면 직접 입력으로 돌아간다
        _error = f"F4 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        _f4 = None
    return _f4


def reset() -> None:
    """테스트에서 F4 폴더를 갈아 끼울 때."""
    global _f4, _error, _tried
    _f4, _error, _tried = None, None, False


def available() -> bool:
    return _load() is not None


def error() -> Optional[str]:
    _load()
    return _error


def _rows(course_id: str) -> list[dict]:
    mods = _load()
    if not mods:
        return []
    f4_store, f4_catalog = mods
    try:
        with f4_store.connect() as con:
            f4_catalog.ensure_scan(con)                 # 새로 수집된 자료가 바로 범위에 들어오게
            rows = f4_store.all_rows(con, course_id)
    except Exception:                                   # noqa: BLE001 — 자료 DB 문제로 계획 화면이 죽지 않게
        return []
    return [{"id": r["id"], "title": r["title"], "week": r["week"], "weekGuess": bool(r["week_guess"]),
             "pages": r["pages"], "kind": r["kind"], "ext": r["ext"], "activity": r["activity"],
             "missing": bool(r["missing"]), "dupOf": r["dup_of"], "state": r["index_state"]}
            for r in rows]


def _usable(rows: list[dict]) -> list[dict]:
    return [r for r in rows if not r["missing"] and not r["dupOf"]]


def materials(course_id: str) -> list[dict]:
    """과목의 자료 목록 — 계획 만들기 화면의 '범위' 고르기 (F5-S04)."""
    return _usable(_rows(course_id))


def weeks(course_id: str) -> list[int]:
    """자료가 있는 주차들 — 범위 드롭다운(`3~7주차`)이 고를 수 있는 값."""
    return sorted({r["week"] for r in _usable(_rows(course_id)) if r["week"]})


def measure(course_id: str, scope_weeks: Optional[list[int]] = None,
            material_ids: Optional[list[str]] = None) -> dict:
    """범위 안 자료의 쪽수 합계 (F5-R10).

    자료 id 를 주면 그것만, 주차를 주면 그 주차만, 둘 다 없으면 **과목의 자료 전체**를 센다.
    {available, pages, files, noPages, materials, weeks, note}
    """
    rows = _usable(_rows(course_id))
    ids = set(material_ids or [])
    weeks_set = {int(w) for w in (scope_weeks or [])}
    if ids:
        picked = [r for r in rows if r["id"] in ids]
    elif weeks_set:
        picked = [r for r in rows if r["week"] in weeks_set]
    else:
        picked = list(rows)

    counted = [r for r in picked if r["pages"]]
    no_pages = [r for r in picked if not r["pages"]]
    pages = sum(r["pages"] or 0 for r in counted)
    return {
        "available": available(),
        "error": _error,
        "pages": pages,
        "files": len(picked),
        "counted": len(counted),
        "noPages": len(no_pages),
        "noPagesTitles": [r["title"] for r in no_pages[:5]],
        "materials": [{"id": r["id"], "title": r["title"], "week": r["week"], "pages": r["pages"],
                       "kind": r["kind"], "ext": r["ext"]} for r in picked],
        "weeks": sorted({r["week"] for r in picked if r["week"]}),
        "note": _note(picked, counted, no_pages),
    }


def _note(picked: list[dict], counted: list[dict], no_pages: list[dict]) -> str:
    if not available():
        return "강의자료(F4)를 읽을 수 없습니다 — 쪽수를 직접 입력하세요"
    if not picked:
        return "범위 안에 자료가 없습니다 — 쪽수를 직접 입력하세요"
    if not counted:
        return f"자료 {len(picked)}개의 쪽수를 세지 못했습니다 — 쪽수를 직접 입력하세요"
    if no_pages:
        return f"자료 {len(counted)}개 {sum(r['pages'] for r in counted)}쪽 " \
               f"(쪽수를 세지 못한 {len(no_pages)}개는 빠졌습니다)"
    return f"자료 {len(counted)}개 {sum(r['pages'] for r in counted)}쪽"


__all__ = ["measure", "materials", "weeks", "available", "error", "reset"]
