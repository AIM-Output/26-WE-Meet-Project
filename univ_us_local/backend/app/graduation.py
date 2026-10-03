"""F2 졸업요건·학점 트래커 — ../F2_Graduation_agent 의 API(graduation.api)를 이 서버에 붙인다.

계산·룰셋·이수 내역 코드는 전부 F2_Graduation_agent 에 있다. 여기서는
  - 라우터(/api/graduation/*)를 include 하고 프로필(C2)을 넘겨주고,
  - /api/status 에 타일 숫자(남은 학점·판정)를 싣고,
  - 이수 내역을 가져올 때 같이 읽은 평점·학년을 C2 프로필에 '자동'으로 넣는다.
F2 쪽 모듈은 표준 라이브러리 + fastapi 만 쓰므로 이 백엔드의 .venv 에 더 설치할 것이 없다.
기이수성적 수집(playwright)은 C3_Login_agent 의 .venv 에서 돈다(F2 jobs 가 띄운다).

F2 폴더가 없거나 불러오지 못해도 나머지 화면은 그대로 동작해야 한다 → available=False 로 알린다.
"""
from __future__ import annotations

import sys
from typing import Callable, Optional

from . import config as C
from .student_profile import get_profile

_error: Optional[str] = None


def _load():
    global _error
    if not (C.F2_AGENT_DIR / "graduation" / "api.py").exists():
        _error = f"F2_Graduation_agent 가 없습니다: {C.F2_AGENT_DIR}"
        return None
    if str(C.F2_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.F2_AGENT_DIR))
    try:
        from graduation import api as f2_api   # type: ignore[import-not-found]
        return f2_api
    except Exception as e:                     # noqa: BLE001 — 어떤 이유로든 F2 가 못 뜨면 나머지는 살린다
        _error = f"F2 모듈을 불러오지 못했습니다: {type(e).__name__}: {e}"
        return None


f2 = _load()


def _apply_profile_import(on_profile_change: Optional[Callable[[], None]]):
    """기이수성적 화면에서 같이 읽은 평점·학년·취득학점 → C2 프로필(자동). 사용자가 입력한 값은 C2 가 건너뛴다."""
    def apply(fetched: dict) -> Optional[dict]:
        try:
            from student import service as c2s, store as c2store   # type: ignore[import-not-found]
        except Exception:                      # noqa: BLE001 — C2 가 없으면 이수 내역만 저장
            return None
        with c2store.connect() as con:
            res = c2s.apply_import(con, fetched)
        if res.get("changed") and on_profile_change:
            on_profile_change()
        return {"changed": res.get("changed"), "skipped": res.get("skipped")}
    return apply


def router(on_profile_change: Optional[Callable[[], None]] = None):
    if not f2:
        return None
    return f2.build_router(get_profile, on_profile=_apply_profile_import(on_profile_change))


def touch() -> None:
    """프로필이 바뀌었다 — 졸업요건 기준(학과·입학년도·이수유형)이 달라질 수 있으니 화면이 다시 부르게 한다 (C2-R08)."""
    if not f2:
        return
    try:
        f2.touch()
    except Exception:                          # noqa: BLE001
        pass


def status() -> dict:
    if not f2:
        return {"available": False, "error": _error}
    try:
        return f2.status_summary(get_profile())
    except Exception as e:                     # noqa: BLE001
        return {"available": False, "error": f"{type(e).__name__}: {e}"}
