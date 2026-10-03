"""F4 강의자료 — ../F4_Textbook_agent 의 API(textbook.api)를 이 서버에 붙인다.

자료 목록 만들기(F6 수집 결과 읽기)·쪽수 읽기·파일 열기/내려받기는 전부 F4_Textbook_agent 에 있다. 여기서는
  - 라우터(/api/materials*)를 include 하고 과목 목록(e클래스 courses.json)을 넘겨주고,
  - /api/status 에 타일 숫자(자료 수·쪽수·확인 필요)를 싣는다.
F4 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다
(업로드도 multipart 가 아니라 본문에 파일을 그대로 받는다 — python-multipart 를 깔지 않으려고).

F4 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Optional

from . import config as C
from . import eclass_data

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F4_AGENT_DIR / "textbook" / "api.py").exists():
        _error = f"F4_Textbook_agent 가 없습니다: {C.F4_AGENT_DIR}"
        return None
    if str(C.F4_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F4_AGENT_DIR))
    try:
        from textbook import api as f4_api      # type: ignore[import-not-found]
        return f4_api
    except Exception as e:                      # noqa: BLE001 — 어떤 이유로든 F4 가 못 뜨면 나머지는 살린다
        _error = f"F4 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f4 = _load()


def router():
    if not f4:
        return None
    return f4.build_router(eclass_data.load_courses)


def touch() -> None:
    """e클래스 수집이 끝났다 — 새로 받은 파일이 자료 목록에 들어가게 한다 (F4-R05)."""
    if not f4:
        return
    try:
        f4.touch()
    except Exception:                           # noqa: BLE001 — 자료 스캔 실패로 수집 뒷정리가 막히지 않게
        pass


def status() -> dict:
    if not f4:
        return {"available": False, "error": _error}
    try:
        return f4.status_summary()
    except Exception as e:                      # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
