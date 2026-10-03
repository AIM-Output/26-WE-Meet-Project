"""대시보드(univ_us_local)에 붙이는 F2 API — FastAPI APIRouter. (Frontend-Route 7-7)

    GET    /api/graduation/status?track=           판정 · 총계 · 영역별 · 세부 요건 · 인증 · 미분류 · 이수 과목 · 기준(매칭 단계·경고)
    GET    /api/graduation/summary                 대시보드 타일용 한 줄
    POST   /api/graduation/courses                 직접 입력 과목 추가 {year, semester, name, credits, grade, area, code}
    PATCH  /api/graduation/courses/{id}            구분 지정 {area, applyToCategory} · 계산 제외 {excluded} · (직접 입력만) 내용 수정
    DELETE /api/graduation/courses/{id}            직접 입력 과목만 지운다 (학사시스템 과목은 409 — 제외 토글을 쓴다)
    POST   /api/graduation/sync                    학사정보시스템 기이수성적 가져오기 {interactive} — 로그인 기록이 없으면 409 {needLogin}
    GET    /api/graduation/sync                    진행 상태·결과
    POST   /api/graduation/simulate                가정 계산 {track, assumptions: {areas: {키: 학점}, courses: [학수번호]}} → 현재/가정 후
    GET    /api/graduation/ruleset?dept&major&year&track   매칭 결과 + 펼친 룰셋 + 편집용 원본 (없으면 빈 템플릿)
    PUT    /api/graduation/ruleset                 내 수정본 저장 {ruleset, track, target?}
    DELETE /api/graduation/ruleset?…               기본값으로 되돌리기
    GET    /api/graduation/rulesets[/{id}]         저장소의 기본 룰셋 목록 · 하나 ('비슷한 학과에서 복사')
    GET    /api/graduation/categories              교과구분 → 영역 매핑 (기본 + 내 지정 + 내 과목에 나온 구분)
    PUT    /api/graduation/categories              {raw, area|null}
    PATCH  /api/graduation/certifications/{key}    {state: done|todo|unknown, memo}
    GET/POST /api/graduation/plans · DELETE /api/graduation/plans/{id}   가정 '내 계획'
    GET    /api/graduation/curriculum              내 학과·전공·입학년도 교육과정 스냅숏이 있는지 + 받기 진행 상태
    POST   /api/graduation/curriculum/sync         교육과정검색에서 받기 (내 학과·전공·입학년도)

의존성: fastapi + 표준 라이브러리. 프로필은 get_profile() 로 읽는다(C2 matching_view 모양, 없으면 None).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from . import jobs, rules, service, store


class SyncIn(BaseModel):
    interactive: bool = False           # True 면 로그인 창을 띄운다 (세션이 없을 때)


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except (service.Invalid, rules.Invalid) as e:
        raise HTTPException(422, str(e))
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except service.Conflict as e:
        raise HTTPException(409, str(e))


def status_summary(profile: Optional[dict]) -> dict:
    """/api/status 에 싣는 F2 칸 — 타일 숫자와 updatedAt(바뀌었을 때만 화면이 다시 부른다)."""
    with store.connect() as con:
        s = service.summary(con, profile)
        up = store.get_meta(con, "updated_at")
    return {"available": True, "updatedAt": up, **s, "import": jobs.state("import")}


def touch() -> None:
    """프로필이 바뀌었다 — 기준이 달라지므로 화면이 다시 부르게 updatedAt 을 올린다 (C2-R08)."""
    with store.connect() as con:
        store.touch(con)


def build_router(get_profile: Callable[[], Optional[dict]], on_change: Optional[Callable[[], None]] = None,
                 on_profile: Optional[Callable[[dict], Any]] = None) -> APIRouter:
    r = APIRouter(prefix="/api/graduation", tags=["F2 졸업요건"])
    jobs.on_change = on_change
    jobs.on_profile = on_profile

    def target_q(dept: Optional[str], major: Optional[str], year: Optional[int], track: Optional[str]) -> Optional[dict]:
        if not (dept or major or year):
            return None
        return {"deptCode": dept, "majorCode": major, "admissionYear": year, "track": track}

    @r.get("/status")
    def get_status(track: Optional[str] = None) -> dict:
        with store.connect() as con:
            return service.status(con, get_profile(), track)

    @r.get("/summary")
    def get_summary() -> dict:
        with store.connect() as con:
            return service.summary(con, get_profile())

    @r.post("/courses", status_code=201)
    def add_course(body: dict[str, Any] = Body(...), track: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                p = get_profile()
                cid = service.add_manual(con, body, service.area_keys(con, p, track))
                s = service.status(con, p, track)
            return {"id": cid, "status": s}
        return _errors(run)

    @r.patch("/courses/{cid}")
    def patch_course(cid: str, body: dict[str, Any] = Body(...), track: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                p = get_profile()
                res = service.patch_course(con, cid, body, service.area_keys(con, p, track))
                s = service.status(con, p, track)
            return {**res, "status": s}
        return _errors(run)

    @r.delete("/courses/{cid}", status_code=204)
    def delete_course(cid: str) -> None:
        def run():
            with store.connect() as con:
                service.delete_course(con, cid)
        _errors(run)

    @r.post("/sync")
    def start_sync(body: SyncIn = Body(default_factory=SyncIn)) -> Any:
        problem = jobs.import_problem(body.interactive)
        if problem:
            return JSONResponse({"detail": problem, "needLogin": "로그인" in problem}, status_code=409)
        return jobs.start_import(body.interactive)

    @r.get("/sync")
    def sync_state() -> dict:
        return jobs.state("import")

    @r.post("/simulate")
    def simulate(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.simulate(con, get_profile(), body.get("track"), body.get("assumptions") or {})
        return _errors(run)

    @r.get("/ruleset")
    def get_ruleset(dept: Optional[str] = None, major: Optional[str] = None, year: Optional[int] = Query(None),
                    track: Optional[str] = None) -> dict:
        with store.connect() as con:
            return service.ruleset_view(con, get_profile(), track, target_q(dept, major, year, track))

    @r.put("/ruleset")
    def put_ruleset(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.save_ruleset(con, get_profile(), body)
        res = _errors(run)
        if on_change:
            on_change()
        return res

    @r.delete("/ruleset")
    def reset_ruleset(dept: Optional[str] = None, major: Optional[str] = None, year: Optional[int] = Query(None),
                      track: Optional[str] = None) -> dict:
        with store.connect() as con:
            res = service.reset_ruleset(con, get_profile(), track, target_q(dept, major, year, track))
        if on_change:
            on_change()
        return res

    @r.get("/rulesets")
    def list_rulesets() -> list[dict]:
        return rules.listing()

    @r.get("/rulesets/{rid}")
    def one_ruleset(rid: str) -> dict:
        doc = rules.by_id(rid)
        if not doc:
            raise HTTPException(404, "룰셋이 없습니다")
        doc.pop("_file", None)
        return doc

    @r.get("/categories")
    def categories(track: Optional[str] = None) -> dict:
        with store.connect() as con:
            return service.category_view(con, get_profile(), track)

    @r.put("/categories")
    def put_category(body: dict[str, Any] = Body(...), track: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                p = get_profile()
                service.set_category(con, str(body.get("raw") or ""), body.get("area"), service.area_keys(con, p, track))
                return service.category_view(con, p, track)
        return _errors(run)

    @r.patch("/certifications/{key}")
    def patch_cert(key: str, body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.set_cert(con, key, body)
        return _errors(run)

    @r.get("/plans")
    def list_plans() -> list[dict]:
        with store.connect() as con:
            return service.plans(con)

    @r.post("/plans", status_code=201)
    def add_plan(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.save_plan(con, body)
        return _errors(run)

    @r.delete("/plans/{pid}", status_code=204)
    def del_plan(pid: str) -> None:
        def run():
            with store.connect() as con:
                service.delete_plan(con, pid)
        _errors(run)

    @r.get("/curriculum")
    def curriculum_state() -> dict:
        return {**service.curriculum_state(get_profile()), "sync": jobs.state("curriculum")}

    @r.post("/curriculum/sync")
    def curriculum_sync() -> dict:
        st = service.curriculum_state(get_profile())
        codes = st["missing"] or st["codes"]
        return jobs.start_curriculum(st["collegeCode"], codes, st["year"])

    return r
