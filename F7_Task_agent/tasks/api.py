"""대시보드(univ_us_local)에 붙이는 F7 API — FastAPI APIRouter. (Frontend-Route 12-4)

    GET    /api/priority?course=&top=3        급한 순 목록 + 그룹 헤더(건수·합계) + 오늘 남은 시간 + 상위 N건 (F7-S01~S07)
    GET    /api/priority/top?n=3              상위 N건 + 총 소요시간 + 한 줄 — F10 아침 브리핑 · F9 대화 (F7-R33)
    GET    /api/settings/priority             안전계수 · 유형별 기본 시간 · 취침 시각 (+ 기본값 · 고친 칸) (F7-S08)
    PATCH  /api/settings/priority             {safetyFactor?, defaultHours?: {kind: h}, bedTime?} · {reset: true}

과제별 소요시간 수정은 F6 의 PATCH /api/assignments/{id} {estimatedHours} 그대로다 — 값이 F6 원장에 있어야 재수집이 덮어쓰지
않는다(F7-R03). 그 뒤 화면이 /api/priority 를 다시 부르면 새 그룹이 나온다.

Frontend-Route 12-4 초안은 목록을 `GET /api/assignments?sort=priority` 로 적었으나, 그 경로는 F6 라우터 것이고
F6 과제·마감 흐름은 건드리지 않기로 했으므로(2026-10-03) F7 은 자기 경로 /api/priority 를 쓴다.

의존성: fastapi + 표준 라이브러리. 과제·일정·학습 분량은 백엔드가 함수로 넘겨준다(아래 Loaders).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from . import config as C
from . import service
from . import settings as S

ItemsLoader = Callable[[], list[dict]]                                   # F6 과제 (eclass.service.view 모양)
EventsLoader = Callable[[Optional[str], Optional[str]], list[dict]]      # 캘린더 이벤트 (C1 · F3 수업 · F5 시험)
StudyLoader = Callable[[], float]                                        # 오늘 남은 학습 분량(분) — F5


def _safe(fn: Optional[Callable[..., Any]], default: Any, *args: Any) -> Any:
    if fn is None:
        return default
    try:
        return fn(*args)
    except Exception:                                   # noqa: BLE001 — 일정·학습 분량을 못 읽어도 순위는 보여 준다
        return default


def _today_events(load_events: Optional[EventsLoader], now: datetime) -> list[dict]:
    """지금 ~ 취침 사이 일정 — 취침이 자정을 넘길 수 있어 이틀치를 받는다."""
    start = (now - timedelta(days=1)).date().isoformat()
    end = (now + timedelta(days=1)).date().isoformat()
    return _safe(load_events, [], start, end)


# ---------------------------------------------------------------- 백엔드가 직접 부르는 것

def overview(load_items: ItemsLoader, load_events: Optional[EventsLoader] = None,
             load_study: Optional[StudyLoader] = None, course: Optional[str] = None,
             top_n: int = C.TOP_N, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    return service.overview(load_items(), now, S.load(), _today_events(load_events, now),
                            _safe(load_study, 0.0), course, top_n)


def brief(load_items: ItemsLoader, n: int = C.TOP_N) -> dict:
    return service.brief(load_items(), n=n)


def status_summary(load_items: ItemsLoader) -> dict:
    return service.status_summary(load_items())


# ---------------------------------------------------------------- 라우터

def build_router(load_items: ItemsLoader, load_events: Optional[EventsLoader] = None,
                 load_study: Optional[StudyLoader] = None,
                 on_change: Optional[Callable[[], None]] = None) -> APIRouter:
    r = APIRouter(tags=["F7 과제 우선순위"])

    @r.get("/api/priority")
    def get_priority(course: Optional[str] = None, top: int = Query(C.TOP_N, ge=0, le=20)) -> dict:
        return overview(load_items, load_events, load_study, course or None, top)

    @r.get("/api/priority/top")
    def get_top(n: int = Query(C.TOP_N, ge=1, le=20)) -> dict:
        return brief(load_items, n)

    @r.get("/api/settings/priority")
    def get_settings() -> dict:
        return S.view()

    @r.patch("/api/settings/priority")
    def patch_settings(body: dict = Body(...)) -> dict:
        reset = bool(body.pop("reset", False)) if isinstance(body, dict) else False
        try:
            out = S.save(body, reset=reset)
        except S.Invalid as e:
            raise HTTPException(422, str(e))
        if on_change:
            on_change()
        return out

    return r


__all__ = ["build_router", "overview", "brief", "status_summary"]
