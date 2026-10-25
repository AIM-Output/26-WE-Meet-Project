"""대시보드(univ_us_local)에 붙이는 F12 API — FastAPI APIRouter. (Frontend-Route 17절 호출표)

    GET    /api/opportunities                          목록(관심사 등급·모집 상태·진행 상태) + 건수 + 관심사 + 태그 사전 + 수집 상태
    GET    /api/opportunities/items/{id}               상세 — 왜 이 등급인가 · 대상·장소·기간·혜택 · 본문 · 첨부 · 초안 · 진행 상태
    PATCH  /api/opportunities/items/{id}               {grade: match|other|null} 등급 뒤집기 · {saved: true|false} 담기 ·
                                                       {progress: saved|draft|approved|applied|selected|not_selected|skipped|null, note}
    POST   /api/opportunities/items/{id}/draft         신청서 초안 만들기 {borrowFrom?} (재료가 없으면 409 needsMaterials)
    PUT    /api/opportunities/items/{id}/draft         초안 고치기 {body}
    DELETE /api/opportunities/items/{id}/draft
    POST   /api/opportunities/items/{id}/calendar      신청 마감 → 내 캘린더 (C1, 출처 act:<id>)
    POST   /api/opportunities/items/{id}/todos         {index} 준비 서류 → 할 일 (마감 하루 전)
    GET    /api/opportunities/history                  이력 — 학기별 담음·지원·선정
    GET    /api/opportunities/sources                  원천 — F11 과 같은 목록(장학 전용 원천 제외) · 내 학과와 관련 여부 · 켜짐
    PATCH  /api/opportunities/sources/{key}            {enabled: true|false|null(기본값으로)}
    POST   /api/opportunities/sync                     지금 수집 {sources?}
    GET|PUT|DELETE /api/opportunities/materials        초안 재료(기본 정보 basic · 진로·활동·보유 역량·강조점) — 비어 있으면 장학 초안 재료를
                                                       불러온다. 기본 정보(이름·학번·연락처 …)는 LLM 에 보내지 않는다

관심사(태그·키워드·제외어)는 C2 프로필의 interests 칸 — 화면이 PATCH /api/profile 로 저장하면 프로필 updatedAt 이 바뀌어 다시 부른다.
의존성: fastapi·pydantic + 표준 라이브러리. 수집(requests·bs4)은 runner 가 자식 프로세스로 띄운다.
프로필(C2)은 get_profile, 캘린더·할 일은 add_event·remove_event, 알림은 push, 장학 초안 재료는 shared_materials 로 대시보드가 넘겨준다.
"""
from __future__ import annotations

import threading
import time
from typing import Callable, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import config as C
from . import judge, notify, runner, service, store

ProfileGetter = Callable[[], Optional[dict]]
AddEvent = Callable[[dict], Optional[dict]]
RemoveEvent = Callable[[str], None]
Shared = Callable[[], Optional[dict]]


class ItemPatch(BaseModel):
    grade: Optional[Literal["match", "other"]] = None
    saved: Optional[bool] = None
    progress: Optional[Literal["saved", "draft", "approved", "applied", "selected", "not_selected", "skipped"]] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    askedApplied: Optional[bool] = None


class DraftIn(BaseModel):
    borrowFrom: Optional[str] = Field(default=None, max_length=200)


class DraftBody(BaseModel):
    body: str = Field(max_length=30000)


class TodoIn(BaseModel):
    index: int = Field(ge=0, le=30)


class SourcePatch(BaseModel):
    enabled: Optional[bool] = None


class SyncIn(BaseModel):
    sources: Optional[list[str]] = None


class BasicIn(BaseModel):
    """초안 기본 정보 — 이 PC 의 초안 재료에만 둔다(프로필·LLM 에는 가지 않는다, F11 basicinfo)."""
    name: str = Field(default="", max_length=40)
    studentId: str = Field(default="", max_length=20)
    department: str = Field(default="", max_length=80)
    grade: str = Field(default="", max_length=10)
    phone: str = Field(default="", max_length=30)
    email: str = Field(default="", max_length=80)


class MaterialsIn(BaseModel):
    careerGoal: str = Field(default="", max_length=2000)
    activities: str = Field(default="", max_length=2000)
    skills: str = Field(default="", max_length=2000)
    highlights: str = Field(default="", max_length=2000)
    basic: Optional[BasicIn] = None


_deliver_cache: dict = {"at": 0.0, "stamp": None}
_judge = {"running": False}


def _judge_in_background(get_profile: ProfileGetter) -> None:
    """LLM 이 설정돼 있으면 키워드로 못 가른 공지를 몇 건씩 판단한다 (1분마다 이어서, 하루 상한까지)."""
    if _judge["running"] or not C.llm_configured():
        return
    _judge["running"] = True

    def work():
        try:
            with store.connect() as con:
                judge.run_batch(con, get_profile())
        except Exception:                        # noqa: BLE001 — 판단 실패는 키워드 판정으로 남는다
            pass
        finally:
            _judge["running"] = False

    threading.Thread(target=work, daemon=True).start()


def status_summary(get_profile: ProfileGetter, push: Optional[notify.Push] = None) -> dict:
    """대시보드 /api/status 의 activity 칸 — 1분마다 불린다. 겸사겸사 알림 배달·LLM 판단·자동 수집 시각 확인."""
    profile = get_profile()
    with store.connect() as con:
        if push is not None:
            stamp = f"{store.get_meta(con, 'updated_at')}|{(profile or {}).get('interests')}"
            if stamp != _deliver_cache["stamp"] or time.monotonic() - _deliver_cache["at"] > 600:
                notify.deliver(con, profile, push)
                _deliver_cache.update(at=time.monotonic(), stamp=stamp)
        out = service.status_summary(con, profile)
    _judge_in_background(get_profile)
    if C.autosync_enabled():
        runner.maybe_autosync(profile)
    out["sync"] = runner.sync_state()
    return out


def brief(get_profile: ProfileGetter, days: int = 3) -> list[dict]:
    with store.connect() as con:
        return service.brief(con, get_profile(), days)


def touch() -> None:
    """프로필(관심사·소속)이 바뀌었다 → 목록이 다시 매겨지도록 화면에 알린다 (등급은 부를 때 계산하므로 저장할 것은 없다)."""
    with store.connect() as con:
        store.touch(con)


def build_router(get_profile: ProfileGetter, add_event: Optional[AddEvent] = None, remove_event: Optional[RemoveEvent] = None,
                 shared_materials: Optional[Shared] = None, shared_basic: Optional[Shared] = None) -> APIRouter:
    """shared_materials = 장학(F11) 초안 재료 전체(대외활동 재료가 비어 있을 때) · shared_basic = 장학 재료의 기본 정보(기본 정보 칸이 비어 있을 때)."""
    r = APIRouter(prefix="/api/opportunities", tags=["F12 대외활동"])

    def _404(nid: str):
        raise HTTPException(404, f"공지가 없습니다: {nid}")

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
        profile = get_profile()
        try:
            with store.connect() as con:
                service.patch(con, nid, body.model_dump(exclude_unset=True), profile, add_event=add_event, remove_event=remove_event)
                return service.detail(con, nid, profile)     # type: ignore[return-value]
        except service.NotFound:
            _404(nid)
        except service.Invalid as e:
            raise HTTPException(422, str(e))

    @r.post("/items/{nid}/draft")
    def make_draft(nid: str, body: DraftIn) -> dict:
        profile = get_profile()
        with store.connect() as con:
            mats = service.materials(con, profile)
            if not mats["exists"] and not body.borrowFrom:
                raise HTTPException(409, "needsMaterials")
            try:
                return service.make_draft(con, nid, profile, body.borrowFrom, add_event=add_event, other_basic=shared_basic)
            except service.NotFound:
                _404(nid)
            except service.Invalid as e:
                raise HTTPException(422, str(e))

    @r.put("/items/{nid}/draft")
    def put_draft(nid: str, body: DraftBody) -> dict:
        with store.connect() as con:
            try:
                service.save_draft_body(con, nid, body.body)
            except service.NotFound:
                raise HTTPException(404, "초안이 없습니다")
            return service.detail(con, nid, get_profile())     # type: ignore[return-value]

    @r.delete("/items/{nid}/draft")
    def delete_draft(nid: str) -> dict:
        with store.connect() as con:
            store.delete_draft(con, nid)
            store.touch(con)
            return service.detail(con, nid, get_profile()) or _404(nid)

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

    @r.get("/materials")
    def get_materials() -> dict:
        with store.connect() as con:
            return service.materials(con, get_profile(), shared_materials, shared_basic)

    @r.put("/materials")
    def put_materials(body: MaterialsIn) -> dict:
        with store.connect() as con:
            return service.put_materials(con, body.model_dump(exclude_unset=True), get_profile(), shared_basic)

    @r.delete("/materials")
    def delete_materials() -> dict:
        with store.connect() as con:
            service.delete_materials(con)
            return service.materials(con, get_profile(), shared_materials, shared_basic)

    return r


__all__ = ["build_router", "status_summary", "brief", "touch"]
