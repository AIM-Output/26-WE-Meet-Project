"""F6 과제 마감 자동 등록 — ../F6_Eclass_agent 의 API(eclass.api)를 이 서버에 붙인다.

수집·원장(신규·변경·삭제)·내가 체크함·알림 시점 계산은 전부 F6_Eclass_agent 에 있다. 여기서는
  - 라우터(/api/assignments* · /api/sources/eclass · /api/sync/login)를 include 하고,
  - /api/events 의 과제 마감(C1 kind=deadline) · /api/courses · /api/status 의 sync·eclass 칸 · POST /api/sync 를 넘겨주고,
  - 마감 알림·변경·수집 실패를 대시보드 알림 센터(F1 notifications 표, 헤더 종)에 넣는다.
F6 쪽 모듈(수집기 제외)은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.
수집(playwright)은 C3_Login_agent 의 .venv 에서 따로 돈다.

F6 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → 빈 목록과 available=False.
"""
from __future__ import annotations

import sys
from datetime import datetime
from typing import Any, Optional

from . import config as C

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F6_AGENT_DIR / "eclass" / "api.py").exists():
        _error = f"F6_Eclass_agent 가 없습니다: {C.F6_AGENT_DIR}"
        return None
    if str(C.F6_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F6_AGENT_DIR))
    try:
        from eclass import api as f6_api        # type: ignore[import-not-found]
        return f6_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 F6 가 못 뜨면 나머지는 살린다
        _error = f"F6 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f6 = _load()

_IDLE = {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "source": None, "pid": None}


def _push(nid: str, kind: str, ref_id: Optional[str], title: str, body: str, href: Optional[str],
          fire_at: Optional[datetime], missed: bool, upsert: bool) -> bool:
    """F6 알림 → 알림 센터 (F6-R40~R43). 알림 표는 F1 이 처음 만들었다(types.ts AppNotification.kind)."""
    try:
        from bachelor import notify as f1notify, store as f1store   # type: ignore[import-not-found]
    except Exception:                           # noqa: BLE001 — F1 이 없으면 알림 센터가 없다
        return False
    with f1store.connect() as con:
        return f1notify.push(con, kind, ref_id, title, body, href, nid=nid, fire_at=fire_at, missed=missed, upsert=upsert)


def router(on_change=None):
    return f6.build_router(on_change=on_change) if f6 else None


def load_courses() -> list[dict]:
    """과목 목록 (courses.json 순서대로 색) — /api/courses · F3 출결의 과목 목록."""
    if not f6:
        return []
    try:
        return f6.courses()
    except Exception:                           # noqa: BLE001
        return []


def load_assignments() -> list[dict]:
    """과제 원장 전체(완료·지난 마감 포함, 사라진 것 제외) — F7 우선순위가 읽는다. 마감 없는 과제도 들어온다."""
    if not f6:
        return []
    with f6.store.connect() as con:
        f6.service.ensure_reconciled(con)
        return f6.service.list_assignments(con, None)["items"]


def load_deadline_events() -> list[dict]:
    """과제·퀴즈·동영상 마감 → 캘린더 이벤트(kind=deadline). 마감이 없거나 사라진 과제는 빠진다."""
    if not f6:
        return []
    try:
        return f6.calendar_events()
    except Exception:                           # noqa: BLE001 — 원장 문제로 캘린더 전체가 죽지 않게
        return []


def status_block() -> dict:
    if not f6:
        return {"available": False, "error": _error}
    try:
        return f6.status_block()
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}


def deliver() -> int:
    """때가 된 마감 알림·변경·실패 알림을 알림 센터로 (상태를 부를 때마다 — 1분)."""
    if not f6:
        return 0
    try:
        return f6.deliver(_push)
    except Exception:                           # noqa: BLE001 — 알림 문제로 상태 응답이 죽지 않게
        return 0


def sync_state() -> dict:
    if not f6:
        return {**_IDLE, "error": _error}
    return f6.sync_state()


def start_sync() -> dict[str, Any]:
    if not f6:
        return {**_IDLE, "error": _error}
    return f6.start_sync()


def last_log_lines(n: int = 14) -> list[str]:
    return f6.last_log_lines(n) if f6 else []


def data_dir() -> str:
    return str(f6.C.DATA_DIR) if f6 else str(C.F6_AGENT_DIR / "data")
