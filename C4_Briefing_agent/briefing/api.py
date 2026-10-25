"""대시보드(univ_us_local)에 붙이는 C4 브리핑 API — FastAPI APIRouter. (Frontend-Route 15-6)

    GET    /api/briefing/today            오늘 브리핑 — 만들 때가 됐는데 없으면 지금 만든다(catchup). state: ready·before·pending·off
    POST   /api/briefing/regenerate       다시 만들기 — 지금 시점 기준으로 오늘 것을 덮어쓴다 (F10-R24)
    GET    /api/briefings?limit=30        지난 브리핑 목록(최신 순, 본문 없이) (F10-R22)
    GET    /api/briefings/{date}          그날 브리핑 스냅샷 전체
    GET    /api/settings/briefing         켜기 · 시각 · 보관 기간 (+ 기본값 · 고친 칸 · LLM 설정 여부)
    PATCH  /api/settings/briefing         {enabled?, time?, keepDays?} — null 은 그 칸을 기본값으로, {reset: true} 는 전부

Frontend-Route 15-6 초안은 설정을 `GET/PUT /api/settings/notifications` 하나로 적었지만, 알림 기본 시각은 F1
(/api/academic/settings), 과제 마감 알림은 F6(/api/assignments/settings)가 이미 자기 자리에 저장한다. 그래서 C4 는
브리핑 칸만 자기 경로 /api/settings/briefing 으로 둔다(F7 이 /api/priority 를 쓴 것과 같은 이유). 화면은 한 곳(/settings/notifications)이다.

의존성: fastapi + 표준 라이브러리. 재료는 백엔드가 함수로 넘겨준다(service.Sources).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Body, HTTPException, Query

from . import service
from . import settings as S
from .service import Sources

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


# ---------------------------------------------------------------- 백엔드가 직접 부르는 것

def today(src: Sources, now: Optional[datetime] = None) -> dict:
    return service.ensure_today(src, now)


def status_summary(src: Sources, now: Optional[datetime] = None) -> dict:
    return service.status(src, now)


# ---------------------------------------------------------------- 라우터

def build_router(src: Sources, on_change=None) -> APIRouter:
    r = APIRouter(tags=["C4 브리핑"])

    @r.get("/api/briefing/today")
    def get_today() -> dict:
        return service.ensure_today(src)

    @r.post("/api/briefing/regenerate")
    def post_regenerate() -> dict:
        out = service.regenerate(src)
        if on_change:
            on_change()
        return out

    @r.get("/api/briefings")
    def get_list(limit: int = Query(30, ge=1, le=90)) -> dict:
        return service.history(limit)

    @r.get("/api/briefings/{day}")
    def get_one(day: str) -> dict:
        if not _DATE.match(day):
            raise HTTPException(422, "날짜는 YYYY-MM-DD 모양이어야 합니다")
        try:
            return service.get(day)
        except service.NotFound:
            raise HTTPException(404, "그날 브리핑이 없습니다 — 지난 날짜는 새로 만들지 않습니다")

    @r.get("/api/settings/briefing")
    def get_settings() -> dict:
        return service.settings_view()

    @r.patch("/api/settings/briefing")
    def patch_settings(body: dict = Body(...)) -> dict:
        if not isinstance(body, dict):
            raise HTTPException(422, "설정은 JSON 객체여야 합니다")
        reset = bool(body.pop("reset", False))
        try:
            out = service.save_settings(body, reset=reset)
        except S.Invalid as e:
            raise HTTPException(422, str(e))
        if on_change:
            on_change()
        return out

    return r


__all__ = ["Sources", "build_router", "today", "status_summary"]
