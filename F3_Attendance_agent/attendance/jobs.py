"""'시간표 자동으로 가져오기' 버튼 뒤에서 도는 일 — 학사정보시스템 시간표 조회(공개) 수집. 표준 라이브러리만.

로그인이 필요 없는 화면이라 브라우저·학교 로그인 세션(C3)을 빌리지 않는다 → 백엔드 안의 스레드로 돈다.
과목당 1회 요청(1.5초 간격) — 7과목이면 15초 안팎. 같은 일이 이미 돌고 있으면 새로 띄우지 않는다.
마지막 결과는 state/timetable.last.json 에 남겨 재시작해도 보인다. DB 쓰기는 끝났을 때 한 번(apply_import).
"""
from __future__ import annotations

import json
import threading
from datetime import datetime
from typing import Any, Callable, Optional

from . import config as C
from . import service, store, timetable

on_change: Optional[Callable[[], None]] = None          # api.build_router 가 넣는다

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "ok": None, "result": None,
                          "error": None, "semester": None, "progress": None}


def _last_file():
    return C.STATE_DIR / "timetable.last.json"


def state() -> dict:
    with _lock:
        s = dict(_state)
    if not s["running"] and s["startedAt"] is None:
        try:
            s.update(json.loads(_last_file().read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return s


def _finish(**kw: Any) -> None:
    with _lock:
        _state.update(running=False, finishedAt=datetime.now().isoformat(timespec="seconds"), progress=None, **kw)
        snap = dict(_state)
    C.ensure_dirs()
    _last_file().write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")


def _log(line: str) -> None:
    C.ensure_dirs()
    with (C.STATE_DIR / "timetable.log").open("a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {line}\n")


def _run(sid: str, courses: list[dict], grade: int, search: Optional[timetable.TimetableSearch]) -> None:
    try:
        year, term = sid.split("-")
        done = {"n": 0}

        def log(line: str) -> None:
            done["n"] += 1
            with _lock:
                _state["progress"] = {"done": done["n"], "total": len(courses)}
            _log(line)

        _log(f"시작 {sid} · {len(courses)}과목")
        results = timetable.lookup(courses, int(year), term, grade, search=search, log=log)
        with store.connect() as con:
            summary = service.apply_import(con, sid, results)
        found = sum(1 for r in results if r["status"] == "found")
        _log(f"끝 — 찾음 {found} / {len(results)}")
        _finish(ok=True, result={**summary, "found": found, "total": len(results)})
        if on_change:
            on_change()
    except Exception as e:                              # noqa: BLE001 — 실패해도 직접 입력으로 계속 쓸 수 있다
        _log(f"실패 {type(e).__name__}: {e}")
        _finish(ok=False, error=f"시간표를 가져오지 못했습니다 — {str(e)[:200]}")


def _begin(sid: str) -> Optional[dict]:
    with _lock:
        if _state["running"]:
            return {**_state, "alreadyRunning": True}
        _state.update(running=True, startedAt=datetime.now().isoformat(timespec="seconds"), finishedAt=None,
                      ok=None, result=None, error=None, semester=sid, progress={"done": 0, "total": 0})
    return None


def start_import(sid: str, courses: list[dict], grade: Optional[int] = None,
                 search: Optional[timetable.TimetableSearch] = None, background: bool = True) -> dict:
    if not courses:
        return {**state(), "running": False, "error": "과목이 없습니다 — e클래스 동기화를 먼저 해 주세요"}
    if sid.split("-")[1] not in C.TERM_CODES:
        return {**state(), "running": False, "error": f"이 학기({sid})는 시간표 조회를 지원하지 않습니다"}
    busy = _begin(sid)
    if busy:
        return busy
    g = grade if isinstance(grade, int) and 1 <= grade <= 4 else 1   # 학년은 필수지만 결과를 거르지 않는다(실측)
    if background:
        threading.Thread(target=_run, args=(sid, courses, g, search), daemon=True).start()
    else:
        _run(sid, courses, g, search)
    return state()
