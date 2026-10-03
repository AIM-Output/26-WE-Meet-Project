"""대시보드(univ_us_local)에 붙이는 F6 API — FastAPI APIRouter. (Frontend-Route 11-8)

    GET    /api/assignments?tab=open|done|past&course=&removed=1   과제 목록 + 탭별 건수 (F6-S01·S02)
    GET    /api/assignments/{id}                                   상세 (변경 이력 포함, F6-S03·S05)
    PATCH  /api/assignments/{id}   {userDone?, estimatedHours?}    내가 체크함(F6-R30·R33) · 소요시간(F7) → 과제 + 캘린더 이벤트
    POST   /api/assignments/legacy {userDone, estimates}          브라우저에만 있던 값 옮기기 (한 번)
    GET    /api/assignments/settings · PUT {reminders}             마감 알림 시점 D-3·D-1·당일 (F6-R40)
    GET    /api/sources/eclass                                      주기 · 예약 작업 · 최근 실행 · 연속 실패 · 로그인 상태 (F6-S08)
    PATCH  /api/sources/eclass     {intervalHours?, scheduled?}    주기 바꾸기 → 작업 스케줄러 재등록 (F6-R18) · 예약 켜기/끄기
    POST   /api/sync/login · GET                                   로그인 창 열기 (C3) → 로그인되면 바로 수집 (F6-S10)
    GET    /api/eclass/feed?kind=notice|board|material&course=&unread=1   새 글·자료 (공지 · 자료실 글 · 강의자료) + 종류별 건수
    GET    /api/eclass/feed/{id}                                   글 본문 · 첨부 이름
    POST   /api/eclass/feed/read  {ids, read?} | {all: true}       읽음 표시
    GET    /api/eclass/feed/settings · PUT {notices, materials}    새 글 알림 켜고 끄기

/api/events 의 deadline · /api/status 의 sync·eclass · POST /api/sync 는 백엔드가 아래 함수로 만든다.
의존성: fastapi + 표준 라이브러리. 알림 센터는 백엔드가 push(...) 로 넘겨준다(F1 알림 표).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from . import config as C
from . import feed, jobs, notify, reconcile, schedule, service, store
from . import runs as R


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except service.Invalid as e:
        raise HTTPException(422, str(e))
    except service.NotFound as e:
        raise HTTPException(404, str(e))


# ---------------------------------------------------------------- 백엔드가 부르는 함수

def courses() -> list[dict]:
    return service.courses()


def calendar_events() -> list[dict]:
    with store.connect() as con:
        service.ensure_reconciled(con)
        return service.calendar_events(con)


def deliver(push: Optional[notify.Push]) -> int:
    """때가 된 마감 알림·변경·실패 알림 + 새 글·자료 알림을 알림 센터로 (백엔드가 /api/status 때마다 부른다)."""
    with store.connect() as con:
        service.ensure_reconciled(con)
        n = notify.deliver(con, push)
    try:
        with store.connect() as con:
            feed.sync(con)
            n += feed.deliver(con, push)
    except Exception:                           # noqa: BLE001 — 새 글 알림 문제로 마감 알림이 막히지 않게
        pass
    return n


def sync_state() -> dict:
    return jobs.sync_state()


def start_sync() -> dict:
    return jobs.start_sync()


def last_log_lines(n: int = 14) -> list[str]:
    return jobs.last_log_lines(n)


def status_block() -> dict:
    """/api/status 의 eclass 칸 — 타일 숫자 · 연속 실패 · 로그인 필요 · 재시도 · 다음 주기 · updatedAt."""
    with store.connect() as con:
        service.ensure_reconciled(con)
        s = service.summary(con)
    try:
        with store.connect() as con:
            feed.sync(con)
            fs = feed.summary(con)
    except Exception:                           # noqa: BLE001
        fs = None
    run_list = R.list_runs(30)
    streak = R.failure_streak(run_list)
    last = next((r for r in run_list if r.get("exit_code") != C.EXIT_BUSY), None)
    interval = R.settings()["intervalHours"]
    now = datetime.now()
    return {
        "available": True, **s,
        "lastOkAt": streak["lastOkAt"],
        "failureStreak": streak["count"], "failureSince": streak["since"], "lastError": streak["lastError"],
        "warn": streak["count"] >= C.FAILURE_STREAK_WARN,
        "needLogin": bool(last and last.get("exit_code") == C.EXIT_LOGIN),
        "retry": R.pending_retry(),
        "intervalHours": interval, "nextSlot": schedule.next_slot(now, interval).isoformat(timespec="seconds"),
        "login": jobs.login_state(),
        "feed": fs,                              # 새 글·자료 — 안 읽은 수 · 안 읽은 공지 · updatedAt
    }


def source_view() -> dict:
    run_list = R.list_runs(20)
    streak = R.failure_streak(run_list)
    interval = R.settings()["intervalHours"]
    now = datetime.now()
    return {
        "key": "eclass", "intervalHours": interval, "choices": list(C.INTERVAL_CHOICES),
        "slots": [f"{h:02d}:00" for h in schedule.slot_hours(interval)],
        "nextSlot": schedule.next_slot(now, interval).isoformat(timespec="seconds"),
        "task": jobs.task_info(), "runs": run_list, "streak": streak, "warnAt": C.FAILURE_STREAK_WARN,
        "retry": R.pending_retry(), "sync": jobs.sync_state(), "login": jobs.login_status(),
        "loginJob": jobs.login_state(), "log": jobs.last_log_lines(), "dataDir": str(C.DATA_DIR),
    }


# ---------------------------------------------------------------- 라우터

def build_router(on_change: Optional[Callable[[], None]] = None) -> APIRouter:
    r = APIRouter(tags=["F6 과제·마감"])

    def changed() -> None:
        if on_change:
            on_change()

    @r.get("/api/assignments")
    def list_assignments(tab: Optional[str] = Query(None, pattern="^(open|done|past|all)$"),
                         course: Optional[str] = None, removed: bool = False) -> dict:
        with store.connect() as con:
            service.ensure_reconciled(con)
            return service.list_assignments(con, None if tab == "all" else tab, course, include_removed=removed)

    @r.get("/api/assignments/settings")
    def get_settings() -> dict:
        with store.connect() as con:
            return {**notify.settings(con), "planned": notify.planned(con)[:20]}

    @r.put("/api/assignments/settings")
    def put_settings(body: dict = Body(...)) -> dict:
        rem = body.get("reminders")
        if not isinstance(rem, list):
            raise HTTPException(422, "reminders 는 목록이어야 합니다 (d3 · d1 · d0)")
        with store.connect() as con:
            return _errors(lambda: notify.save_settings(con, [str(x) for x in rem]))

    @r.post("/api/assignments/legacy")
    def migrate(body: dict = Body(...)) -> dict:
        ud = body.get("userDone") or {}
        est = body.get("estimates") or {}
        if not isinstance(ud, dict) or not isinstance(est, dict):
            raise HTTPException(422, "userDone · estimates 는 {id: 값} 모양이어야 합니다")
        with store.connect() as con:
            service.ensure_reconciled(con)
            out = service.migrate_legacy(con, ud, est)
        if out["userDone"] or out["estimates"]:
            changed()
        return out

    @r.get("/api/assignments/{item_id}")
    def get_assignment(item_id: str) -> dict:
        with store.connect() as con:
            return _errors(lambda: service.detail(con, item_id))

    @r.patch("/api/assignments/{item_id}")
    def patch_assignment(item_id: str, body: dict = Body(...)) -> dict:
        kw: dict[str, Any] = {}
        if "userDone" in body:
            if not isinstance(body["userDone"], bool):
                raise HTTPException(422, "userDone 은 true/false 여야 합니다")
            kw["user_done"] = body["userDone"]
        if "estimatedHours" in body:
            kw["estimate_hours"] = body["estimatedHours"]
        if not kw:
            raise HTTPException(422, "바꿀 값이 없습니다 (userDone · estimatedHours)")
        with store.connect() as con:
            a = _errors(lambda: service.patch(con, item_id, **kw))
        changed()
        return {"assignment": a, "event": service.to_event(a) if a["due"] else None}

    # -- 새 글·자료 (공지 · 자료실 글 · 강의자료) --------------------------------
    @r.get("/api/eclass/feed")
    def get_feed(kind: Optional[str] = Query(None, pattern="^(notice|board|material)$"), course: Optional[str] = None,
                 unread: bool = False) -> dict:
        with store.connect() as con:
            feed.sync(con)
            return feed.list_items(con, kind, course, unread)

    @r.get("/api/eclass/feed/settings")
    def get_feed_settings() -> dict:
        with store.connect() as con:
            return feed.settings(con)

    @r.put("/api/eclass/feed/settings")
    def put_feed_settings(body: dict = Body(...)) -> dict:
        with store.connect() as con:
            return feed.save_settings(con, notices=body.get("notices"), materials=body.get("materials"))

    @r.post("/api/eclass/feed/read")
    def read_feed(body: dict = Body(...)) -> dict:
        """{ids: [...], read?: true|false} 몇 건 읽음/안 읽음 · {all: true} 전부 읽음."""
        ids = body.get("ids")
        if not body.get("all") and not isinstance(ids, list):
            raise HTTPException(422, "ids 목록 또는 all: true 가 필요합니다")
        with store.connect() as con:
            n = feed.mark_read(con, None if body.get("all") else [str(i) for i in ids], read=body.get("read", True) is not False)
            out = {"updated": n, **feed.summary(con)}
        if n:
            changed()
        return out

    @r.get("/api/eclass/feed/{item_id}")
    def get_feed_item(item_id: str) -> dict:
        with store.connect() as con:
            d = feed.detail(con, item_id)
        if not d:
            raise HTTPException(404, "글·자료가 없습니다")
        return d

    @r.get("/api/sources/eclass")
    def get_source() -> dict:
        return source_view()

    @r.patch("/api/sources/eclass")
    def patch_source(body: dict = Body(...)) -> dict:
        out: dict[str, Any] = {}
        interval = body.get("intervalHours")
        if interval is not None:
            if interval not in C.INTERVAL_CHOICES:
                raise HTTPException(422, f"주기는 {', '.join(map(str, C.INTERVAL_CHOICES))}시간 중 하나입니다")
            R.save_settings(intervalHours=interval)
        scheduled = body.get("scheduled")
        if scheduled is False:
            out["task"] = jobs.unregister_task()
        elif scheduled is True or (interval is not None and jobs.task_info().get("registered")):
            out["task"] = jobs.register_task(R.settings()["intervalHours"])     # 주기가 바뀌면 다시 등록 (F6-R18)
        if out.get("task") and not out["task"].get("ok"):
            raise HTTPException(500, out["task"].get("error") or "작업 스케줄러 오류")
        return {**source_view(), **out}

    @r.get("/api/sync/login")
    def get_login() -> dict:
        return {**jobs.login_state(), "status": jobs.login_status()}

    @r.post("/api/sync/login")
    def post_login(body: Optional[dict] = Body(None)) -> dict:
        then_sync = True if not body else bool(body.get("thenSync", True))
        st = jobs.start_login(then_sync=then_sync)
        if st.get("error") and not st.get("running"):
            raise HTTPException(409, st["error"])
        return st

    return r


__all__ = ["build_router", "courses", "calendar_events", "deliver", "sync_state", "start_sync", "last_log_lines",
           "status_block", "source_view", "reconcile"]
