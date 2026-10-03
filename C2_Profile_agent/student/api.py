"""대시보드(univ_us_local)에 붙이는 C2 API — FastAPI APIRouter. (Frontend-Route 5-6)

    GET    /api/profile                  내 프로필 + 항목별 출처(자동/내가 입력) + 필수 항목 채움 여부
    PATCH  /api/profile                  일부 항목 저장 {affiliation: {deptCode, majorCode}, admissionYear, …} — null 이면 지움
    DELETE /api/profile                  내 정보 전부 지우기 (C2-S07)
    DELETE /api/profile/sensitive        장학용 민감정보만 지우기 (C2-R07)
    GET    /api/profile/schema           항목 이름·쓰는 기능(F1·F2·F11)·민감정보 이유·선택지
    POST   /api/profile/legacy           브라우저에 저장돼 있던 옛 프로필 옮기기 (프로필이 비어 있을 때만)
    POST   /api/profile/import           학사정보시스템에서 가져오기 시작 {interactive} — 로그인 기록이 없으면 409 {needLogin}
    GET    /api/profile/import           가져오기 진행 상태·결과
    GET    /api/master/departments       학과 선택기 목록 (로컬 JSON — 네트워크 없이 뜬다)
    POST   /api/master/departments/sync  교육과정검색에서 다시 수집 (1분 남짓)
    GET    /api/master/status            학과 목록 기준 연도·갱신 시각·수집 진행 상태

의존성: fastapi (대시보드 백엔드에 이미 있음) + 표준 라이브러리. 프로필이 바뀌면 on_change 를 부른다(F1 재판정 등, C2-R08).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import jobs, master, schema, service, store


class ImportIn(BaseModel):
    interactive: bool = False           # True 면 로그인 창을 띄운다 (세션이 없을 때)


def profile_for_matching() -> Optional[dict]:
    """다른 기능(F1 대상 판정 등)이 부르는 프로필 — 없으면 None."""
    with store.connect() as con:
        return service.matching_view(con)


def build_router(on_change: Optional[Callable[[], None]] = None) -> APIRouter:
    r = APIRouter(prefix="/api", tags=["C2 프로필"])
    jobs.on_change = on_change              # 가져오기가 끝나 값이 바뀌었을 때도 부른다

    def changed() -> None:
        if on_change:
            on_change()

    @r.get("/profile")
    def get_profile() -> dict:
        with store.connect() as con:
            return service.get(con)

    @r.patch("/profile")
    def patch_profile(body: dict[str, Any] = Body(...)) -> dict:
        try:
            with store.connect() as con:
                res = service.patch(con, body, by="user")
                doc = service.get(con)
        except schema.Invalid as e:
            raise HTTPException(422, str(e))
        if res["changed"]:
            changed()
        return {**doc, "changed": res["changed"]}

    @r.delete("/profile", status_code=204)
    def delete_profile() -> None:
        with store.connect() as con:
            service.delete_all(con)
        changed()

    @r.delete("/profile/sensitive")
    def delete_sensitive() -> dict:
        with store.connect() as con:
            service.delete_sensitive(con)
            doc = service.get(con)
        changed()
        return doc

    @r.get("/profile/schema")
    def profile_schema() -> dict:
        return schema.describe()

    @r.post("/profile/legacy")
    def migrate(body: dict[str, Any] = Body(...)) -> dict:
        with store.connect() as con:
            res = service.migrate_legacy(con, body)
            doc = service.get(con)
        if res.get("migrated"):
            changed()
        return {**doc, "migration": res}

    @r.post("/profile/import")
    def start_import(body: ImportIn = Body(default_factory=ImportIn)) -> Any:
        problem = jobs.import_problem(body.interactive)
        if problem:
            return JSONResponse({"detail": problem, "needLogin": "로그인" in problem}, status_code=409)
        st = jobs.start_import(body.interactive)
        return st

    @r.get("/profile/import")
    def import_state() -> dict:
        return jobs.state("import")

    @r.get("/master/departments")
    def departments() -> dict:
        return {**master.summary(), "entries": master.entries()}

    @r.post("/master/departments/sync")
    def sync_departments() -> dict:
        return jobs.start_master_sync()

    @r.get("/master/status")
    def master_status() -> dict:
        return {**master.summary(), "sync": jobs.state("master")}

    return r
