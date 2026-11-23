"""대시보드(univ_us_local)에 붙이는 F11 API — FastAPI APIRouter. (Frontend-Route 16절 호출표)

    GET    /api/scholarships                          목록(판정·진행 상태) + 건수 + 수집 상태 + 프로필 요약
    GET    /api/scholarships/items/{id}               상세 — 조건별 대조표 · 본문 · 첨부 · 진행 상태
    PATCH  /api/scholarships/items/{id}               {verdict: eligible|ineligible|null, reason} 판정 뒤집기·되돌리기
                                                      {progress: approved(신청 예정)|applied|selected|not_selected|skipped|null, note, amount}
    POST   /api/scholarships/items/{id}/calendar      신청 마감 → 내 캘린더 (C1)
    POST   /api/scholarships/items/{id}/todos         {index} 제출 서류 → 할 일 (마감 하루 전)
    GET    /api/scholarships/history                  이력 — 학기별 신청·선정·금액
    GET    /api/scholarships/sources                  원천 — 학교 전체 · 부서 · 사업단 · 내 소속 (내 학과와 관련 여부 · 켜짐)
    PATCH  /api/scholarships/sources/{key}            {enabled: true|false|null(기본값으로)}
    POST   /api/scholarships/sync                     지금 수집 {sources?}

신청서 초안(/draft)·초안 재료(/materials)는 2026-11-19 폐기했다 — 요구사항정의서 F11 1절 '신청서 초안 폐기'.
의존성: fastapi·pydantic + 표준 라이브러리. 수집(requests·bs4)은 runner 가 자식 프로세스로 띄운다.
프로필(C2, 민감정보 포함)은 대시보드가 get_profile 로, 캘린더·할 일은 add_event 로, 알림은 push 로 넘겨준다.
"""
from __future__ import annotations

import time
from typing import Callable, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import config as C
from . import notify, runner, service, store

ProfileGetter = Callable[[], Optional[dict]]
AddEvent = Callable[[dict], Optional[dict]]


class ItemPatch(BaseModel):
    verdict: Optional[Literal["eligible", "ineligible"]] = None
    reason: Optional[str] = Field(default=None, max_length=300)
    progress: Optional[Literal["approved", "applied", "selected", "not_selected", "skipped"]] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    amount: Optional[str] = Field(default=None, max_length=100)
    askedApplied: Optional[bool] = None


class TodoIn(BaseModel):
    index: int = Field(ge=0, le=30)


class SourcePatch(BaseModel):
    enabled: Optional[bool] = None


class SyncIn(BaseModel):
    sources: Optional[list[str]] = None


_deliver_cache: dict = {"at": 0.0, "stamp": None}


def status_summary(get_profile: ProfileGetter, push: Optional[notify.Push] = None) -> dict:
    """대시보드 /api/status 의 scholarship 칸 — 1분마다 불린다. 겸사겸사 알림 배달·자동 수집 시각 확인."""
    profile = get_profile()
    with store.connect() as con:
        if push is not None:
            stamp = store.get_meta(con, "updated_at")
            # 알림 계산은 공지가 바뀌었을 때나 10분마다만 (마감 D-3·D-1 은 하루 단위라 충분)
            if stamp != _deliver_cache["stamp"] or time.monotonic() - _deliver_cache["at"] > 600:
                notify.deliver(con, profile, push)
                _deliver_cache.update(at=time.monotonic(), stamp=stamp)
        out = service.status_summary(con, profile)
    if C.autosync_enabled():
        runner.maybe_autosync(profile)
    out["sync"] = runner.sync_state()
    return out


def brief(get_profile: ProfileGetter, days: int = 3) -> list[dict]:
    with store.connect() as con:
        return service.brief(con, get_profile(), days)


def touch() -> None:
    """프로필이 바뀌었다 → 목록이 다시 판정되도록 화면에 알린다 (판정은 부를 때 계산하므로 저장할 것은 없다)."""
    with store.connect() as con:
        store.touch(con)


def build_router(get_profile: ProfileGetter, add_event: Optional[AddEvent] = None) -> APIRouter:
    r = APIRouter(prefix="/api/scholarships", tags=["F11 장학"])

    def _404(nid: str):
        raise HTTPException(404, f"장학 공지가 없습니다: {nid}")

    @r.get("")
    def overview() -> dict:
        with store.connect() as con:
            ov = service.overview(con, get_profile())
        return {**ov, "sync": runner.sync_state(), "log": runner.last_log_lines(8)}

    @r.get("/items/{nid}")
    def item(nid: str) -> dict:
        with store.connect() as con:
            d = service.detail(con, nid, get_profile())
        return d or _404(nid)

    @r.patch("/items/{nid}")
    def patch_item(nid: str, body: ItemPatch) -> dict:
        try:
            with store.connect() as con:
                service.patch(con, nid, body.model_dump(exclude_unset=True))
                return service.detail(con, nid, get_profile())     # type: ignore[return-value]
        except service.NotFound:
            _404(nid)
        except service.Invalid as e:
            raise HTTPException(422, str(e))

    @r.post("/items/{nid}/calendar")
    def to_calendar(nid: str) -> dict:
        if add_event is None:
            raise HTTPException(503, "캘린더(C1)를 불러오지 못했습니다")
        with store.connect() as con:
            try:
                service.add_calendar(con, nid, get_profile(), add_event)
            except service.NotFound:
                _404(nid)
            except service.Invalid as e:
                raise HTTPException(422, str(e))
            return service.detail(con, nid, get_profile())     # type: ignore[return-value]

    @r.post("/items/{nid}/todos")
    def to_todo(nid: str, body: TodoIn) -> dict:
        if add_event is None:
            raise HTTPException(503, "캘린더(C1)를 불러오지 못했습니다")
        with store.connect() as con:
            try:
                service.add_todo(con, nid, body.index, get_profile(), add_event)
            except service.NotFound:
                _404(nid)
            except service.Invalid as e:
                raise HTTPException(422, str(e))
            return service.detail(con, nid, get_profile())     # type: ignore[return-value]

    @r.get("/history")
    def history() -> dict:
        with store.connect() as con:
            return service.history(con)

    @r.get("/sources")
    def sources() -> dict:
        with store.connect() as con:
            rows = service.source_rows(con, get_profile())
        return {"sources": rows, "sync": runner.sync_state(), "log": runner.last_log_lines(),
                "slots": list(C.SYNC_SLOTS), "autosync": C.autosync_enabled()}

    @r.patch("/sources/{key}")
    def patch_source(key: str, body: SourcePatch) -> dict:
        with store.connect() as con:
            try:
                service.set_source(con, key, body.enabled)
            except service.NotFound:
                raise HTTPException(404, "원천이 없습니다")
            rows = service.source_rows(con, get_profile())
        return next(x for x in rows if x["key"] == key)

    @r.post("/sync")
    def sync(body: SyncIn = SyncIn()) -> dict:
        return runner.start_sync(body.sources, get_profile(), "button")

    return r


__all__ = ["build_router", "status_summary", "brief", "touch"]
