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

공부 완료 체크 (2026-10-06 사용자 요청)
  사용자가 **서비스 밖에서 공부한 자료**를 체크해 두면(`exams.store.material_done`) 그 쪽수를 범위에서 뺀다.
  `pages` = 아직 공부할 쪽수(범위 − 체크), `scopePages` = 범위 전체, `donePages` = 체크한 쪽수.
  계획 만들기가 `pages` 를 분량 기본값으로 쓰므로 체크하면 남은 분량이 바로 줄어든다.

범위를 정하지 않은 시험 (공지에 범위가 없는 과목)
  **지금까지 e클래스에 올라온 강의자료 전체**(`basis='all'`). 과제 첨부(`kind='assignment'` — 제출 양식·샘플)는
  공부할 자료가 아니라서 뺀다 (실측: 산학협력 제안서 양식·소공론 정의서 샘플).
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
    """공부할 자료 — 사라진 파일·중복·과제 첨부(양식·샘플)는 뺀다."""
    return [r for r in rows if not r["missing"] and not r["dupOf"] and r["kind"] != "assignment"]


def materials(course_id: str) -> list[dict]:
    """과목의 자료 목록 — 계획 만들기 화면의 '범위' 고르기 (F5-S04)."""
    return _usable(_rows(course_id))


def weeks(course_id: str) -> list[int]:
    """자료가 있는 주차들 — 범위 드롭다운(`3~7주차`)이 고를 수 있는 값."""
    return sorted({r["week"] for r in _usable(_rows(course_id)) if r["week"]})


def measure(course_id: str, scope_weeks: Optional[list[int]] = None,
            material_ids: Optional[list[str]] = None, done: Optional[dict[str, str]] = None) -> dict:
    """범위 안 자료의 쪽수 합계 (F5-R10) — 공부 완료로 체크한 자료는 남은 분량에서 뺀다.

    자료 id 를 주면 그것만, 주차를 주면 그 주차만, 둘 다 없으면 **과목의 강의자료 전체**를 센다.
    done = {자료 id: 체크한 시각} (exams.store.material_done)
    {available, pages(남은 쪽), scopePages, donePages, files, doneFiles, materials, weeks, basis, label, note}
    """
    rows = _usable(_rows(course_id))
    done = done or {}
    ids = set(material_ids or [])
    weeks_set = {int(w) for w in (scope_weeks or [])}
    if ids:
        picked, basis = [r for r in rows if r["id"] in ids], "ids"
    elif weeks_set:
        picked, basis = [r for r in rows if r["week"] in weeks_set], "weeks"
    else:
        picked, basis = list(rows), "all"

    counted = [r for r in picked if r["pages"]]
    no_pages = [r for r in picked if not r["pages"]]
    scope_pages = sum(r["pages"] or 0 for r in counted)
    checked = [r for r in picked if r["id"] in done]
    done_pages = sum(r["pages"] or 0 for r in checked)
    return {
        "available": available(),
        "error": _error,
        "pages": scope_pages - done_pages,
        "scopePages": scope_pages,
        "donePages": done_pages,
        "files": len(picked),
        "doneFiles": len(checked),
        "counted": len(counted),
        "noPages": len(no_pages),
        "noPagesTitles": [r["title"] for r in no_pages[:5]],
        "materials": [{"id": r["id"], "title": r["title"], "week": r["week"], "pages": r["pages"],
                       "kind": r["kind"], "ext": r["ext"], "done": r["id"] in done,
                       "doneAt": done.get(r["id"])} for r in picked],
        "weeks": sorted({r["week"] for r in picked if r["week"]}),
        "basis": basis,
        "label": _label(basis, picked, weeks_set),
        "note": _note(picked, counted, no_pages, done_pages, len(checked)),
    }


def _label(basis: str, picked: list[dict], weeks_set: set[int]) -> str:
    """범위 한 줄 — 카드의 '범위 …'."""
    if basis == "all":
        return "e클래스 강의자료 전체"
    if basis == "weeks":
        ws = sorted(weeks_set)
        run = ws == list(range(ws[0], ws[-1] + 1))
        return f"{ws[0]}~{ws[-1]}주차" if run and len(ws) > 2 else "·".join(map(str, ws)) + "주차"
    return f"고른 자료 {len(picked)}개"


def _note(picked: list[dict], counted: list[dict], no_pages: list[dict],
          done_pages: int = 0, done_files: int = 0) -> str:
    if not available():
        return "강의자료(F4)를 읽을 수 없습니다 — 쪽수를 직접 입력하세요"
    if not picked:
        return "범위 안에 자료가 없습니다 — 쪽수를 직접 입력하세요"
    if not counted:
        return f"자료 {len(picked)}개의 쪽수를 세지 못했습니다 — 쪽수를 직접 입력하세요"
    total = sum(r["pages"] for r in counted)
    head = f"자료 {len(counted)}개 {total}쪽"
    if no_pages:
        head += f" (쪽수를 세지 못한 {len(no_pages)}개는 빠졌습니다)"
    if done_files:
        head += f" · 공부 완료 {done_files}개 {done_pages}쪽 빼고 {total - done_pages}쪽"
    return head


__all__ = ["measure", "materials", "weeks", "available", "error", "reset"]
