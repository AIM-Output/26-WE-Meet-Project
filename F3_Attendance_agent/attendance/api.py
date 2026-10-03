"""대시보드(univ_us_local)에 붙이는 F3 API — FastAPI APIRouter. (Frontend-Route 8-7)

    GET    /api/attendance/summary?semester=          학기 · 과목(설정·시간표·회차·집계) · 합계 · 교시 시각 · 학사경고
    GET    /api/attendance/sessions?course=&from=&to= 회차 목록 (course 없으면 전체)
    PATCH  /api/attendance/sessions/{id}              출결 {attendance} · 휴강/되돌리기 {state} · 메모 {memo}
    POST   /api/attendance/sessions                   보강 추가 {courseId, date, periods, memo?}
    DELETE /api/attendance/sessions/{id}              내가 추가한 보강 지우기
    POST   /api/attendance/sessions/bulk              몰아서 입력 {items: [{id, attendance}]}
    PATCH  /api/attendance/courses/{id}               한도·지각 환산·누적 직접 조정·제외 (수기 과목은 이름도)
    POST   /api/attendance/courses                    수기 과목 추가 {name, code?, section?, meetings?}
    DELETE /api/attendance/courses/{id}               수기 과목 지우기
    PUT    /api/attendance/timetable                  시간표 저장 {courses: [{courseId, meetings}], validFrom?} → 회차 재생성 결과
    DELETE /api/attendance/timetable/{courseId}       자동값으로 되돌리기
    POST   /api/attendance/timetable/import           시간표 자동으로 가져오기 (학사정보시스템 공개 조회) · GET 진행 상태
    PUT    /api/attendance/semester                   개강·종강·휴업일 직접 입력 {semester, start, end, holidays}
    GET    /api/attendance/periods · PUT · DELETE     교시 ↔ 시각 (C1 주 뷰 설정 — 학교 시간표 모듈이 기본)
    GET    /api/attendance/today                      오늘 수업 + 위험 과목 (F10 브리핑·F9 대화용)
    GET    /api/attendance/alerts                     만든 경고 알림 이력

바꾸는 요청은 다시 계산한 과목(course)과 새로 생긴 경고(alerts — 토스트용)를 같이 돌려준다.
의존성: fastapi + 표준 라이브러리. 과목 목록은 get_courses() (e클래스 courses.json 을 백엔드가 읽은 모양),
프로필은 get_profile() (C2 matching_view), 알림 센터는 notify(alert) 로 넣는다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from . import academic_calendar as AC
from . import jobs, service, store

CoursesGetter = Callable[[], list[dict]]
ProfileGetter = Callable[[], Optional[dict]]


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except service.Invalid as e:
        raise HTTPException(422, str(e))
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except service.Conflict as e:
        raise HTTPException(409, str(e))


def _safe(fn: Callable[[], Any], default: Any) -> Any:
    try:
        return fn()
    except Exception:                                   # noqa: BLE001 — e클래스 폴더·프로필 문제로 출결 화면이 죽지 않게
        return default


def status_summary(get_courses: CoursesGetter, profile: Optional[dict] = None,
                   notify: Optional[service.Notify] = None) -> dict:
    """/api/status 에 싣는 F3 칸 — 타일 숫자와 updatedAt(바뀌었을 때만 화면이 다시 부른다)."""
    with store.connect() as con:
        s = service.status_summary(con, profile, _safe(get_courses, None), notify=notify)
    return {"available": True, **s, "import": jobs.state()}


def calendar_events(start: Optional[str] = None, end: Optional[str] = None) -> list[dict]:
    with store.connect() as con:
        return service.calendar_events(con, start, end)


def touch() -> None:
    with store.connect() as con:
        store.touch(con)


def build_router(get_courses: CoursesGetter, get_profile: ProfileGetter,
                 notify: Optional[service.Notify] = None, on_change: Optional[Callable[[], None]] = None) -> APIRouter:
    r = APIRouter(prefix="/api/attendance", tags=["F3 출결"])
    jobs.on_change = on_change

    def current(con, semester: Optional[str]) -> str:
        return semester or service.current_semester(con, AC.load(), datetime.now().date())

    @r.get("/summary")
    def summary(semester: Optional[str] = None) -> dict:
        eclass = _safe(get_courses, None)
        with store.connect() as con:
            return service.overview(con, semester, profile=_safe(get_profile, None), eclass=eclass, notify=notify)

    @r.get("/sessions")
    def sessions(course: Optional[str] = None, semester: Optional[str] = None,
                 from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None) -> list[dict]:
        with store.connect() as con:
            _, courses = service.build_semester(con, current(con, semester), datetime.now())
        out = []
        for c in courses:
            if course and c["id"] != course:
                continue
            out += [{**s, "courseName": c["short"], "color": c["color"]} for s in c["sessions"]
                    if (not from_ or s["date"] >= from_) and (not to or s["date"] <= to)]
        return out

    @r.patch("/sessions/{sid}")
    def patch_session(sid: str, body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.patch_session(con, sid, body, notify=notify)
        return _errors(run)

    @r.post("/sessions/bulk")
    def bulk(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.bulk_attendance(con, body.get("items") or [], notify=notify)
        return _errors(run)

    @r.post("/sessions", status_code=201)
    def add_makeup(body: dict[str, Any] = Body(...), semester: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                return service.add_makeup(con, body, semester=semester or body.get("semester"), notify=notify)
        return _errors(run)

    @r.delete("/sessions/{sid}")
    def delete_makeup(sid: str) -> dict:
        def run():
            with store.connect() as con:
                return service.delete_makeup(con, sid)
        return _errors(run)

    @r.patch("/courses/{cid}")
    def patch_course(cid: str, body: dict[str, Any] = Body(...), semester: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                return service.patch_course(con, cid, body, semester=semester, notify=notify)
        return _errors(run)

    @r.post("/courses", status_code=201)
    def add_course(body: dict[str, Any] = Body(...), semester: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                return service.add_manual_course(con, body, semester=current(con, semester or body.get("semester")))
        return _errors(run)

    @r.delete("/courses/{cid}", status_code=204)
    def delete_course(cid: str, semester: Optional[str] = None) -> None:
        def run():
            with store.connect() as con:
                service.delete_course(con, cid, semester=current(con, semester))
        _errors(run)

    @r.put("/timetable")
    def put_timetable(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.save_timetable(con, body, semester=current(con, body.get("semester")), notify=notify)
        return _errors(run)

    @r.delete("/timetable/{cid}")
    def revert_timetable(cid: str, semester: Optional[str] = None) -> dict:
        def run():
            with store.connect() as con:
                return service.revert_timetable(con, cid, semester=current(con, semester))
        return _errors(run)

    @r.post("/timetable/import")
    def start_import(body: dict[str, Any] = Body(default_factory=dict)) -> dict:
        eclass = _safe(get_courses, None)
        with store.connect() as con:
            sid = current(con, body.get("semester"))
            if eclass is not None and sid == current(con, None):
                service.sync_courses(con, sid, eclass)
            targets = service.import_targets(con, sid)
        grade = (_safe(get_profile, None) or {}).get("grade")
        return jobs.start_import(sid, targets, grade)

    @r.get("/timetable/import")
    def import_state() -> dict:
        return jobs.state()

    @r.put("/semester")
    def put_semester(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                sid = current(con, body.get("semester"))
                service.set_semester(con, sid, body)
                return service.resolve_semester(con, AC.load(), sid)
        return _errors(run)

    @r.get("/periods")
    def periods() -> dict:
        with store.connect() as con:
            return service.period_view(con)

    @r.put("/periods")
    def put_periods(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.set_period_map(con, body)
        return _errors(run)

    @r.delete("/periods")
    def reset_periods() -> dict:
        with store.connect() as con:
            return service.set_period_map(con, None)

    @r.get("/today")
    def today() -> dict:
        with store.connect() as con:
            return service.today(con)

    @r.get("/alerts")
    def alerts(semester: Optional[str] = None) -> list[dict]:
        with store.connect() as con:
            return service.alert_history(con, current(con, semester))

    return r


__all__ = ["build_router", "status_summary", "calendar_events", "touch"]
