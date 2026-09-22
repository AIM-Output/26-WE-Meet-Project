"""유니버스(Univ-Us) 개인 로컬 서버 — FastAPI.

    uvicorn app.main:app --host 127.0.0.1 --port 8000        (backend/ 에서)

- /api/*            프론트가 쓰는 JSON API
- /                 frontend/out (next build 결과) 가 있으면 정적으로 서빙. 없으면 안내 페이지.
개발 중에는 `next dev`(3000) 가 /api 를 여기로 넘겨준다 (frontend/next.config.ts rewrites).
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from typing import Literal, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config as C
from . import eclass_data, store


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.init()
    yield


app = FastAPI(title="Univ-Us Local", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)

# Host 헤더가 localhost/127.0.0.1 이 아니면 거절 (DNS 리바인딩 대비)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=C.ALLOWED_HOSTS)


@app.middleware("http")
async def check_origin(request: Request, call_next):
    """브라우저가 보내는 변경 요청은 허용된 Origin 에서만. Origin 이 없는 요청(curl 등)은 로컬 도구로 본다."""
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin not in C.ALLOWED_ORIGINS:
            return JSONResponse({"detail": f"허용되지 않은 Origin: {origin}"}, status_code=403)
    return await call_next(request)


# ---------------------------------------------------------------- 모델

CategoryKey = Literal["personal", "study", "team", "etc"]
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$")


class UserEventIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    start: str
    end: Optional[str] = None
    all_day: bool = False
    category: CategoryKey = "personal"
    memo: str = ""
    is_todo: bool = False      # 할 일 — To Do List 에서 완료 체크 가능
    done: bool = False


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
    for label, v in (("start", start), ("end", end)):
        if v is not None and not DATE_RE.match(v):
            raise HTTPException(422, f"{label} 형식이 잘못됐습니다: {v!r} (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM[:SS])")
    if start and end and end <= start:
        raise HTTPException(422, "종료가 시작보다 빠르거나 같습니다.")


def _parse_user_id(event_id: str) -> int:
    if not event_id.isdigit():
        raise HTTPException(404, "사용자 일정이 아닙니다 (e클래스 마감은 수정할 수 없습니다).")
    return int(event_id)


# ---------------------------------------------------------------- API

@app.get("/api/events")
def get_events(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    """e클래스 마감 + 사용자 일정. start/end(YYYY-MM-DD)를 주면 그 구간에 걸치는 것만."""
    deadlines, _ = eclass_data.load_deadline_events()
    events = deadlines + store.list_events()
    if start or end:
        def overlaps(ev: dict) -> bool:
            s = ev["start"][:10]
            e = (ev.get("end") or ev["start"])[:10]
            return (not end or s <= end) and (not start or e >= start)
        events = [ev for ev in events if overlaps(ev)]
    return events


@app.post("/api/events", status_code=201)
def post_event(body: UserEventIn) -> dict:
    _check_dates(body.start, body.end)
    data = body.model_dump()
    data["title"] = data["title"].strip()
    data["memo"] = data["memo"].strip()
    return store.create_event(**data)


@app.patch("/api/events/{event_id}")
def patch_event(event_id: str, body: UserEventPatch) -> dict:
    uid = _parse_user_id(event_id)
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


@app.delete("/api/events/{event_id}", status_code=204)
def delete_event(event_id: str) -> None:
    if not store.delete_event(_parse_user_id(event_id)):
        raise HTTPException(404, "일정이 없습니다.")


@app.get("/api/courses")
def get_courses() -> list[dict]:
    return eclass_data.load_courses()


@app.get("/api/status")
def get_status() -> dict:
    deadlines, updated_at = eclass_data.load_deadline_events()
    counts = store.count_events()
    return {
        "updated_at": updated_at,
        "sync": eclass_data.sync_state(),
        "counts": {
            "courses": len(eclass_data.load_courses()),
            "deadlines": len(deadlines),
            "userEvents": counts["total"],
            "todos": counts["todos"],
            "todosDone": counts["done"],
        },
        "categories": C.CATEGORIES,
        "eclassDataDir": str(C.ECLASS_DATA_DIR),
        "log": eclass_data.last_log_lines(),
    }


@app.post("/api/sync")
def post_sync() -> dict:
    """eclass_agent/run-sync.cmd 를 백그라운드로 실행한다. 진행 상황은 /api/status 의 sync 로 본다."""
    return eclass_data.start_sync()


# ---------------------------------------------------------------- 정적 프론트

if C.FRONTEND_OUT.exists():
    app.mount("/", StaticFiles(directory=str(C.FRONTEND_OUT), html=True), name="frontend")
else:
    @app.get("/", response_class=HTMLResponse)
    def index_placeholder() -> str:
        return (
            "<h1>Univ-Us Local</h1>"
            "<p>프론트 빌드(<code>frontend/out</code>)가 없습니다. 개발 중이면 "
            "<a href='http://localhost:3000'>http://localhost:3000</a> (next dev) 로 여세요.<br>"
            "배포용은 <code>frontend</code> 에서 <code>npm run build</code> 를 실행하면 여기서 바로 서빙됩니다.</p>"
            "<p>API 문서: <a href='/api/docs'>/api/docs</a></p>"
        )
