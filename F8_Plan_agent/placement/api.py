"""대시보드(univ_us_local)에 붙이는 F8 API — FastAPI APIRouter. (Frontend-Route 13-6)

    POST   /api/placement/preview               {range?, exclude?, settings?} → 주간 격자 · 블록 · 미배치 · 하루 합계 · 조정 제안
    POST   /api/placement                       {signature, at, range?, exclude?} → 학습 블록 등록 (placedBy=auto)
    GET    /api/placement/conflicts             겹친 블록 · 끝낸 작업의 블록 (F8-R31 · S08)
    GET    /api/placement/today                 오늘 학습 블록 — F10 브리핑 · F9 대화
    DELETE /api/placement?from=&to=             기간 안의 자동 배치 블록 지우기 (고정·완료 제외, F8-S10)
    PATCH  /api/placement/blocks/{id}           {start, end} 옮기기(→ 고정) · {done} 완료 체크 · {fixed: false} 고정 풀기
    DELETE /api/placement/blocks/{id}           블록 하나 지우기
    GET    /api/settings/availability           공강 배치 설정 (+ 기본값 · 고친 칸)
    PUT·PATCH /api/settings/availability        {칸: 값} · null = 그 칸 기본값 · {reset: true}
    (공부 캘린더에 섞는 공강 공부 블록은 study_blocks() 로 백엔드가 F5 에 넘겨준다 — 경로 없음)

**미리보기와 등록을 나눈다** — F5 와 같은 규칙이다. 계산은 부수효과가 없고, 캘린더를 바꾸는 것은 `배치하기` 뿐이다.
등록은 미리보기 시각(at)으로 다시 계산해 signature 가 같을 때만 쓴다 — 그 사이 데이터가 바뀌면 409.

의존성: fastapi + 표준 라이브러리. 일정 · F5 공부 대상 · F7 순위는 백엔드가 함수로 넘겨준다(아래 Loaders).
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from . import config as C
from . import service, store
from . import settings as S

EventsLoader = Callable[[Optional[str], Optional[str]], list[dict]]     # 수업 · 내 일정·할 일 · 시험 (/api/events 모양, 학사 제외)
ExamsLoader = Callable[[bool], list[dict]]                              # F5 공강 공부 대상 (with_progress) — 시험 · 진도율
PriorityLoader = Callable[[], list[dict]]                               # F7 순위 목록 (순서 그대로)


def _safe(fn: Optional[Callable[..., Any]], default: Any, *args: Any) -> Any:
    if fn is None:
        return default
    try:
        return fn(*args)
    except Exception:                                   # noqa: BLE001 — 한 기능이 깨져도 배치는 나머지로 계산한다
        return default


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except service.Stale as e:
        raise HTTPException(409, str(e))
    except S.Invalid as e:
        raise HTTPException(422, str(e))


def _window(range_days: Optional[int]) -> tuple[str, str]:
    """일정을 읽을 기간 — 날짜가 지난 미완료 할 일도 가져오려고 시작을 2주 앞당긴다(service.todo_tasks)."""
    n = int(range_days or S.load()["rangeDays"])
    t = date.today()
    return (t - timedelta(days=C.TODO_LOOKBACK_DAYS)).isoformat(), (t + timedelta(days=max(n, 1) - 1)).isoformat()


def _refs(events: Optional[list[dict]], load_exams: Optional[ExamsLoader],
          load_priority: Optional[PriorityLoader]) -> Optional[dict]:
    exams, pri = _safe(load_exams, None, False), _safe(load_priority, None)
    if exams is None or pri is None or events is None:
        return None                                     # 하나라도 못 읽으면 '끝낸 작업' 표시는 하지 않는다
    return service.open_refs_of(exams, pri, events)


# ---------------------------------------------------------------- 백엔드가 직접 부르는 것

def calendar_events(start: Optional[str], end: Optional[str], load_events: Optional[EventsLoader] = None,
                    load_exams: Optional[ExamsLoader] = None, load_priority: Optional[PriorityLoader] = None) -> list[dict]:
    """/api/events 의 과제·할 일 블록(kind=study — 공부 블록은 빼고). 앞으로 남은 블록이 있을 때만 다른 일정을 읽어 충돌을 단다."""
    with store.connect() as con:
        span = service.active_span(con, start, end)
        events = refs = None
        if span:
            events = _safe(load_events, None, span[0], span[1])
            refs = _refs(events, load_exams, load_priority)
        return service.calendar_events(con, start, end, events, refs)


def study_blocks(start: str, end: str, load_events: Optional[EventsLoader] = None,
                 load_exams: Optional[ExamsLoader] = None, load_priority: Optional[PriorityLoader] = None) -> list[dict]:
    """F5 공부 캘린더에 섞을 공강 공부 블록 (2026-10-07) — 전체 캘린더에는 없다. 앞으로 남은 공부 블록이 있으면 충돌을 단다."""
    with store.connect() as con:
        span = service.active_span(con, start, end, study=True)
        events = refs = None
        if span:
            events = _safe(load_events, None, span[0], span[1])
            refs = _refs(events, load_exams, load_priority)
        return service.study_blocks(con, start, end, events, refs)


def today() -> dict:
    with store.connect() as con:
        return service.today(con)


def status_summary() -> dict:
    with store.connect() as con:
        return service.status_summary(con)


def touch() -> None:
    with store.connect() as con:
        store.touch(con)


# ---------------------------------------------------------------- 라우터

def build_router(load_events: EventsLoader, load_exams: Optional[ExamsLoader] = None,
                 load_priority: Optional[PriorityLoader] = None,
                 on_change: Optional[Callable[[], None]] = None) -> APIRouter:
    r = APIRouter(tags=["F8 공강 학습 플랜"])

    def inputs(range_days: Optional[int]) -> tuple[list[dict], list[dict], list[dict]]:
        first, last = _window(range_days)
        return (_safe(load_events, [], first, last), _safe(load_exams, [], True), _safe(load_priority, []))

    def changed() -> None:
        if on_change:
            on_change()

    @r.post("/api/placement/preview")
    def post_preview(body: dict[str, Any] = Body(default={})) -> dict:
        def run():
            rng = body.get("range")
            ev, st, pr = inputs(rng)
            patch = body.get("settings")
            with store.connect() as con:
                return service.preview(con, ev, st, pr, S.merged(patch) if patch else None, None, rng,
                                       body.get("exclude") or ())
        return _errors(run)

    @r.post("/api/placement")
    def post_register(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            rng = body.get("range")
            ev, st, pr = inputs(rng)
            with store.connect() as con:
                out = service.register(con, ev, st, pr, body.get("signature"), body.get("at"), rng,
                                       body.get("exclude") or ())
            changed()
            return out
        return _errors(run)

    @r.get("/api/placement/conflicts")
    def get_conflicts() -> dict:
        def run():
            first = date.today().isoformat()
            last = (date.today() + timedelta(days=60)).isoformat()
            ev = _safe(load_events, [], first, last)
            refs = _refs(ev, load_exams, load_priority)
            with store.connect() as con:
                return service.conflicts(con, ev, refs)
        return _errors(run)

    @r.get("/api/placement/today")
    def get_today() -> dict:
        return today()

    @r.delete("/api/placement")
    def delete_auto(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                out = service.delete_auto(con, from_, to)
            changed()
            return out
        return _errors(run)

    @r.patch("/api/placement/blocks/{block_id}")
    def patch_block(block_id: str, body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                out = service.patch_block(con, block_id, body)
            changed()
            return out
        return _errors(run)

    @r.delete("/api/placement/blocks/{block_id}")
    def delete_block(block_id: str) -> dict:
        def run():
            with store.connect() as con:
                out = service.delete_block(con, block_id)
            changed()
            return out
        return _errors(run)

    @r.get("/api/settings/availability")
    def get_settings() -> dict:
        return S.view()

    def save_settings(body: dict[str, Any]) -> dict:
        def run():
            b = dict(body or {})
            reset = bool(b.pop("reset", False))
            out = S.save(b, reset=reset)
            changed()
            return out
        return _errors(run)

    @r.put("/api/settings/availability")
    def put_settings(body: dict[str, Any] = Body(...)) -> dict:
        return save_settings(body)

    @r.patch("/api/settings/availability")
    def patch_settings(body: dict[str, Any] = Body(...)) -> dict:
        return save_settings(body)

    return r


__all__ = ["build_router", "calendar_events", "study_blocks", "today", "status_summary", "touch"]
