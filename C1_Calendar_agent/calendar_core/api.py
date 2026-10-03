"""C1 서비스 캘린더 — FastAPI 라우터 (/api/events).

대시보드 백엔드가 `univ_us_local/backend/app/calendar_events.py` 에서 아래 함수로 붙인다.

    build_router(sources)   GET/POST/PATCH/DELETE /api/events   — 캘린더 본체 (C1-R10·R30~R32)
    calendar_events(...)    다른 곳에서 합쳐진 목록이 필요할 때 (F9·F10)
    status_summary()        /api/status 의 calendar 칸 · 건수 · 분류표

`sources` 는 다른 기능이 캘린더에 얹는 일정을 주는 함수들이다 — F6 마감 · F1 학사 · F3 수업 (C1 3절).
이 폴더는 **내 일정·할 일**(kind=user)만 저장한다.
"""
from __future__ import annotations

from typing import Literal, Optional, Sequence

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import config as C
from . import service, store
from .service import Source

CategoryKey = Literal["personal", "study", "team", "etc"]


class UserEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: str
    end: Optional[str] = None
    all_day: bool = False
    category: CategoryKey = "personal"
    memo: str = ""
    is_todo: bool = False      # 할 일 — To Do List 에서 완료 체크 가능
    done: bool = False
    # 가져온 곳 — 학사 일정 '내 일정에 넣기'면 그 학사 일정 id('ac:…'). 같은 곳에서 두 번 넣지 않는다
    origin: Optional[str] = Field(default=None, max_length=160, pattern=r"^ac:[^\s]+$")


class UserEventPatch(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=200)
    start: Optional[str] = None
    end: Optional[str] = None
    all_day: Optional[bool] = None
    category: Optional[CategoryKey] = None
    memo: Optional[str] = None
    is_todo: Optional[bool] = None
    done: Optional[bool] = None


def _check_dates(start: Optional[str], end: Optional[str]) -> None:
    if msg := service.date_error(start, end):
        raise HTTPException(422, msg)


def _user_id(event_id: str) -> int:
    uid = service.parse_user_id(event_id)
    if uid is None:
        raise HTTPException(404, "사용자 일정이 아닙니다 (e클래스 마감·학사 일정은 여기서 수정할 수 없습니다).")
    return uid


def build_router(sources: Sequence[Source] = ()) -> APIRouter:
    router = APIRouter()

    @router.get("/api/events")
    def get_events(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
        """e클래스 마감(F6) + 내 일정 + 학사 일정(F1, 내 캘린더에 등록된 것만) + 수업 회차(F3, kind=class).
        start/end(YYYY-MM-DD)를 주면 그 구간에 걸치는 것만."""
        return service.collect(sources, start, end)

    @router.post("/api/events", status_code=201)
    def post_event(body: UserEventIn) -> dict:
        _check_dates(body.start, body.end)
        if body.origin and store.find_by_origin(body.origin):
            raise HTTPException(409, "이미 내 일정에 넣은 학사 일정입니다.")
        data = body.model_dump()
        data["title"] = data["title"].strip()
        data["memo"] = data["memo"].strip()
        return store.create_event(**data)

    @router.patch("/api/events/{event_id}")
    def patch_event(event_id: str, body: UserEventPatch) -> dict:
        uid = _user_id(event_id)
        current = store.get_event(uid)
        if not current:
            raise HTTPException(404, "일정이 없습니다.")
        fields = body.model_dump(exclude_unset=True)
        if "title" in fields:
            fields["title"] = fields["title"].strip()
        _check_dates(fields.get("start", current["start"]), fields.get("end", current["end"]))
        updated = store.update_event(uid, fields)
        if not updated:
            raise HTTPException(404, "일정이 없습니다.")
        return updated

    @router.delete("/api/events/{event_id}", status_code=204)
    def delete_event(event_id: str) -> None:
        if not store.delete_event(_user_id(event_id)):
            raise HTTPException(404, "일정이 없습니다.")

    return router


def calendar_events(sources: Sequence[Source] = (), start: Optional[str] = None,
                    end: Optional[str] = None) -> list[dict]:
    """합쳐진 캘린더 목록 — 라우터를 거치지 않고 필요할 때 (F9 자연어 질의 · F10 브리핑)."""
    return service.collect(sources, start, end)


def status_summary() -> dict:
    """/api/status 의 calendar 칸 — 건수와 분류표(화면이 색·이름을 여기서 받는다)."""
    return {"available": True, "db": str(C.DB_PATH),
            "counts": store.count_events(), "categories": C.CATEGORIES}
