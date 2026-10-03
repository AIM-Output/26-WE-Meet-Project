"""대시보드(univ_us_local) 에 붙이는 F1 API — FastAPI APIRouter. (Frontend-Route 6-9 의 호출표)

    GET    /api/academic/events                 학기 목록 + 학사 일정 전체 (탭은 화면에서 거른다)
    GET    /api/academic/events/{id}            하나
    PATCH  /api/academic/events/{id}            {status: approved|hidden|restore, start, end, memo, pinned, reminders}
    GET    /api/academic/upcoming?days=3        오늘부터 N일 안의 내 학사 일정 (F10 브리핑)
    GET    /api/academic/status                 원천별 수집 상태 · 확인 필요 건수 (대시보드 /api/status 에도 실린다)
    GET    /api/academic/settings · PUT         알림 기준 시각
    GET    /api/sources                         수집 원천 4곳 (① 학사일정 표 ② 학사안내 ③ 내 단과대학 ④ 내 학부) + 내 소속 홈페이지·게시판
    PATCH  /api/sources/{key}                   {enabled} 켜고 끄기 · {overrideUrl} ③·④ 게시판 직접 지정(null = 자동으로)
    POST   /api/sources/{key}/sync              지금 수집 (key=academic 이면 켜진 학사 원천 전부)
    POST   /api/sources/academic/schedule       {enabled} 예약 수집(매일 08:00 + 실패 재시도) 켜고 끄기 — 작업 스케줄러
    POST   /api/academic/new/ack                신규 묶음 '전체 확인' → 날짜순 목록으로
    GET    /api/notifications?unread=1          알림 (때가 된 것을 먼저 배달한다)
    POST   /api/notifications/{id}/read · POST /api/notifications/read-all

의존성: fastapi·pydantic (대시보드 백엔드에 이미 있음) + 표준 라이브러리. 수집(requests·bs4)은 import 하지 않는다.
프로필은 대시보드가 get_profile 로 넘겨준다 (C2_Profile_agent).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import homepages, notify, runner, service, sources_admin, store

ProfileGetter = Callable[[], Optional[dict]]
_DT = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:T(\d{2}:\d{2})(?::\d{2})?)?$")


class AcademicPatch(BaseModel):
    status: Optional[Literal["approved", "hidden", "restore"]] = None
    start: Optional[str] = Field(default=None, description="승인할 때 고친 시작 — YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM")
    end: Optional[str] = Field(default=None, description="승인할 때 고친 끝 — 마지막 날(포함) 또는 끝 시각")
    memo: Optional[str] = Field(default=None, max_length=2000)
    pinned: Optional[bool] = None
    reminders: Optional[dict[str, bool]] = None


class SourcePatch(BaseModel):
    enabled: Optional[bool] = None
    overrideUrl: Optional[str] = Field(default=None, max_length=500, description="③·④ 게시판 직접 지정 — null 이면 자동으로")


class ScheduleIn(BaseModel):
    enabled: bool


class SettingsIn(BaseModel):
    alertTime: Optional[str] = None


def _split(v: Optional[str], label: str) -> tuple[Optional[str], Optional[str]]:
    if not v:
        return None, None
    m = _DT.match(v.strip())
    if not m:
        raise HTTPException(422, f"{label} 형식이 잘못됐습니다: {v!r} (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM)")
    return m.group(1), m.group(2)


last_day = service.last_day
_review_count = service.review_count


def status_summary(profile: Optional[dict]) -> dict:
    """대시보드 /api/status 의 academic 칸."""
    today = date.today()
    with store.connect() as con:
        items = service.list_events(con, profile, today)
        rows = sources_admin.list_rows(con, profile)
        updated = store.get_meta(con, "updated_at")
        last_run = store.get_meta(con, "last_run_started")
    cur = service.current_semester(today)
    in_sem = [e for e in items if e["semester"] == cur and e["status"] in ("auto", "approved")]
    return {
        "available": True,
        "updatedAt": updated,
        "sync": runner.sync_state(),
        "reviewCount": _review_count(items, today),
        # 마지막 수집에서 새로 찾아 바로 등록된, 아직 지나지 않은 일정 수 (확인 필요는 reviewCount) — 대시보드 '신규 일정 N건'
        # = /academic 맨 위 '새로 수집된 학사일정' 묶음. 학과 게시판의 옛 글처럼 이미 지난 것은 세지 않는다
        "newCount": sum(1 for e in items if e["isNew"] and e["status"] in ("auto", "approved")
                        and last_day(e) is not None and last_day(e) >= today),
        "lastRunAt": last_run,
        "counts": {"total": len(in_sem), "mine": sum(1 for e in in_sem if e["appliesToMe"] is True),
                   "thisMonth": sum(1 for e in items if e["onCalendar"] and (e["start"] or "")[:7] == today.isoformat()[:7])},
        "sources": [{k: r[k] for k in ("key", "name", "kindLabel", "state", "lastRunAt", "lastOkAt", "count", "error",
                                       "enabled", "items", "scope", "target", "resolve", "stale")} for r in rows],
    }


def calendar_events(profile: Optional[dict], start: Optional[str], end: Optional[str]) -> list[dict]:
    with store.connect() as con:
        return service.calendar_events(con, profile, start, end)


def build_router(get_profile: ProfileGetter) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["F1 학사일정"])

    @r.get("/academic/events")
    def academic_events() -> dict:
        with store.connect() as con:
            return service.overview(con, get_profile())

    @r.get("/academic/events/{event_id}")
    def academic_event(event_id: str) -> dict:
        with store.connect() as con:
            e = service.get_event(con, event_id, get_profile())
        if not e:
            raise HTTPException(404, "학사 일정이 없습니다.")
        return e

    @r.patch("/academic/events/{event_id}")
    def patch_academic_event(event_id: str, body: AcademicPatch) -> dict:
        patch = body.model_dump(exclude_unset=True)
        if body.status == "approved" and (body.start or body.end):
            sd, st = _split(body.start, "start")
            ed, et = _split(body.end, "end")
            if not sd:
                raise HTTPException(422, "시작 날짜가 필요합니다.")
            if ed == sd and not et:
                ed = None
            patch["dates"] = {"start_date": sd, "start_time": st, "end_date": ed, "end_time": et}
        try:
            with store.connect() as con:
                service.update_event(con, event_id, patch)
                e = service.get_event(con, event_id, get_profile())
        except service.NotFound:
            raise HTTPException(404, "학사 일정이 없습니다.")
        except service.Invalid as ex:
            raise HTTPException(422, str(ex))
        return e

    @r.post("/academic/new/ack")
    def academic_new_ack() -> dict:
        """'전체 확인' — 신규 묶음을 날짜순 목록으로 돌려보낸다."""
        with store.connect() as con:
            service.ack_new(con)
        return {"ok": True}

    @r.get("/academic/upcoming")
    def academic_upcoming(days: int = 3) -> list[dict]:
        with store.connect() as con:
            return notify.upcoming(con, get_profile(), max(0, min(days, 60)))

    @r.get("/academic/status")
    def academic_status() -> dict:
        return {**status_summary(get_profile()), "log": runner.last_log_lines()}

    @r.get("/academic/settings")
    def academic_settings() -> dict:
        with store.connect() as con:
            return service.get_settings(con)

    @r.put("/academic/settings")
    def put_academic_settings(body: SettingsIn) -> dict:
        try:
            with store.connect() as con:
                out = service.set_settings(con, body.alertTime)
                store.touch(con)
                return out
        except service.Invalid as ex:
            raise HTTPException(422, str(ex))

    @r.get("/sources")
    def sources() -> dict:
        with store.connect() as con:
            rows = sources_admin.list_rows(con, get_profile())
        return {"sources": rows, "sync": runner.sync_state(), "log": runner.last_log_lines(),
                "directory": homepages.summary(), "schedule": runner.task_info()}

    @r.post("/sources/academic/schedule")
    def academic_schedule(body: ScheduleIn) -> dict:
        """예약 수집 켜고 끄기 — 작업 스케줄러에 매일 08:00 + 로그인 시 등록 / 해제."""
        res = runner.register_task() if body.enabled else runner.unregister_task()
        if not res["ok"]:
            raise HTTPException(500, f"{res['error']}: {res.get('output', '')[-300:]}")
        return runner.task_info(force=True)

    @r.patch("/sources/{key}")
    def patch_source(key: str, body: SourcePatch) -> dict:
        """켜고 끄기 — 끄면 그 원천의 일정이 목록·캘린더에서 빠지므로 updatedAt 을 올려 화면이 다시 받게 한다."""
        fields = body.model_dump(exclude_unset=True)
        try:
            with store.connect() as con:
                if fields.get("enabled") is not None:
                    sources_admin.set_enabled(con, key, bool(fields["enabled"]))
                if "overrideUrl" in fields:
                    sources_admin.set_override(con, key, fields["overrideUrl"])
                store.touch(con)
                return sources_admin.get_row(con, key, get_profile())
        except service.NotFound:
            raise HTTPException(404, "원천이 없습니다.")
        except service.Invalid as ex:
            raise HTTPException(422, str(ex))

    @r.post("/sources/{key}/sync")
    def sync_source(key: str) -> dict:
        if key == "academic":
            return runner.start_sync(None)
        with store.connect() as con:
            row = store.get_source(con, key)
        if row is None:
            raise HTTPException(404, "원천이 없습니다.")
        return runner.start_sync([key])

    @r.get("/notifications")
    def notifications(unread: int = 0) -> dict:
        with store.connect() as con:
            return notify.list_notifications(con, get_profile(), unread_only=bool(unread))

    @r.post("/notifications/read-all")
    def notifications_read_all() -> dict:
        with store.connect() as con:
            return {"updated": notify.mark_all_read(con)}

    @r.post("/notifications/{nid}/read")
    def notification_read(nid: str) -> dict:
        with store.connect() as con:
            return {"updated": notify.mark_read(con, nid)}

    return r


__all__ = ["build_router", "status_summary", "calendar_events"]
