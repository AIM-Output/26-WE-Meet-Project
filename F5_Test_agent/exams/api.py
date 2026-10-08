"""대시보드(univ_us_local)에 붙이는 F5 API — FastAPI APIRouter. (Frontend-Route 10-7)

    GET    /api/exams?semester=&sync=1              시험 목록 + 확인 필요 + 오늘 분량 (F5-S01·S02)
    POST   /api/exams                               시험 직접 추가 (F5-S03)
    POST   /api/exams/sync                          e클래스 공지에서 시험 다시 찾기 (F5-R01)
    GET    /api/exams/today                         오늘 분량 + 가장 가까운 시험 (F10 브리핑 · F9 대화)
    GET    /api/exams/courses                       과목별 시험 유무 + 중간·기말 상태 + 학사일정 기간
    PATCH  /api/exams/courses/{courseId}            {midterm?, final?} — 시험을 안 보는 과목은 끈다
    GET    /api/study-calendar?start=&end=          공부 캘린더 — 날짜마다 과목·시간·분량 + 그날의 시험
    GET·PUT /api/exams/settings                     난이도 시간 설정 {difficulty: {easy, normal, hard}} (분/쪽)
    DELETE /api/study-plans/{id}/days/{date}        학습 블록 하나 지우기 (완료한 것도, 마지막이면 계획도)
    GET    /study-calendar                          공부 캘린더 화면 (F5_Test_agent/web/study_calendar.html)
    GET    /api/exams/{id}                          시험 하나 + 계획 옵션 기본값 + 범위 후보 (F5-S04)
    PATCH  /api/exams/{id}                          승인·수정 (F5-S02)
    DELETE /api/exams/{id}                          삭제
    GET    /api/exams/{id}/materials                범위 강의자료 + 공부 완료 체크 (2026-10-06)
    PATCH  /api/exams/{id}/materials                {ids, done} — 서비스 밖에서 공부한 자료 체크·해제 (과목 단위)
    PATCH  /api/exams/{id}/ready                    {ready} — 발표 '준비 완료' (발표는 공부 계획 없이 이것만, 2026-10-06)
    POST   /api/study-plans/preview                 계획 계산만 — 등록하지 않는다 (F5-S05)
    POST   /api/study-plans                         계획 등록 → 학습 블록 생성 (F5-R31 — 공부 캘린더에만 나온다)
    GET    /api/study-plans/{id}                    계획 + 진도 + 범위 자료 (F5-S07)
    DELETE /api/study-plans/{id}                    계획 취소 — 미완료 블록만 지운다 (F5-R35)
    POST   /api/study-plans/{id}/rebalance          재조정 미리보기 (F5-R34)
    GET    /api/study-plans/{id}/days/{date}        학습 블록 하나 + 그날 볼 자료 (F5-S08)
    PATCH  /api/study-plans/{id}/days/{date}        완료 체크 {done} · 다른 날로 옮기기 {date} (F5-R32·R33)

미리보기와 등록을 나눈 이유: 같은 계산기를 두 번 쓰되 **등록만 부수효과**를 갖게 해서, 화면이 '계산 결과'와
'실제 캘린더'를 헷갈리지 않게 한다 (Frontend-Route 10-7 주석 · F5 D3).

의존성: fastapi + 표준 라이브러리. 과목 목록은 get_courses() (e클래스 courses.json 을 백엔드가 읽은 모양),
알림 센터는 notify(alert) 로 넣는다(F1 notifications 표). 분량은 F4 를 읽는다(scope.py).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import FileResponse

from . import academic, defaults, service, store
from . import config as C
from . import plan as P

CoursesGetter = Callable[[], list[dict]]


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except (service.Invalid, P.Invalid) as e:
        raise HTTPException(422, str(e))
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except service.Conflict as e:
        raise HTTPException(409, str(e))


def _safe(fn: Optional[Callable[[], Any]], default: Any) -> Any:
    if fn is None:
        return default
    try:
        return fn()
    except Exception:                                   # noqa: BLE001 — 과목 목록을 못 받아도 시험 화면은 살린다
        return default


# ---------------------------------------------------------------- 백엔드가 직접 부르는 것

def status_summary(get_courses: Optional[CoursesGetter] = None,
                   notify: Optional[service.Notify] = None) -> dict:
    """/api/status 의 exams 칸 — 기능 타일 숫자 (F5-S09)."""
    with store.connect() as con:
        return service.status_summary(con, get_courses, notify=notify)


def calendar_events(start: Optional[str] = None, end: Optional[str] = None,
                    get_courses: Optional[CoursesGetter] = None) -> list[dict]:
    """/api/events 에 섞는 시험(kind=exam) — 날짜가 확정된 것만. 공부 계획은 넣지 않는다(공부 캘린더에만) (C1 3절).

    대시보드는 첫 화면에서 /api/events 를 /api/status 보다 먼저 받을 수 있다 → 여기서도 임의 일정·수업 시간 채우기를
    맞춰 둔다(바뀐 게 없으면 도장으로 바로 건너뛴다). 안 그러면 첫 화면의 시험이 '시각 미정'으로 보였다."""
    with store.connect() as con:
        defaults.ensure(con, None, get_courses)
        return service.calendar_events(con, start, end, get_courses)


def today_block(get_courses: Optional[CoursesGetter] = None) -> dict:
    """'오늘 공부: 운영체제 15쪽 (38분)' — F10 아침 브리핑이 읽는다 (F5-R36)."""
    with store.connect() as con:
        return service.today_block(con, None, service.course_map(get_courses))


def study_targets(get_courses: Optional[CoursesGetter] = None, with_progress: bool = True) -> list[dict]:
    """공강 공부 대상 — 다가오는 시험과 남은 진도율. F8(공강 배치)이 남는 공강에 넣을 과목을 고른다 (2026-10-07)."""
    with store.connect() as con:
        return service.study_targets(con, get_courses, with_progress=with_progress)


def sync(get_courses: Optional[CoursesGetter] = None,
         notify: Optional[service.Notify] = None) -> dict:
    """e클래스 수집이 끝났다 — 새 공지에서 시험을 찾는다 (백엔드가 수집 뒤에 부른다)."""
    with store.connect() as con:
        return service.sync_notices(con, notify=notify, get_courses=get_courses)


def touch() -> None:
    with store.connect() as con:
        store.touch(con)


# ---------------------------------------------------------------- 라우터

def build_router(get_courses: Optional[CoursesGetter] = None,
                 notify: Optional[service.Notify] = None,
                 extra_blocks: Optional[Callable[[str, str], list[dict]]] = None) -> APIRouter:
    """extra_blocks(start, end) — 공부 캘린더에 섞을 F8 공강 공부 블록 (백엔드가 넘겨준다, 2026-10-07)."""
    r = APIRouter(tags=["F5 시험 공부 일정"])

    # ── 시험 ──

    @r.get("/api/exams")
    def list_exams(semester: Optional[str] = None, sync: bool = False) -> dict:
        """시험 목록. sync=1 이면 먼저 공지를 다시 읽는다 (화면의 '공지에서 찾기')."""
        def run():
            with store.connect() as con:
                synced = service.sync_notices(con, notify=notify, get_courses=get_courses) if sync else None
                out = service.overview(con, get_courses, semester)
                if synced is not None:
                    out["sync"] = synced
                return out
        return _errors(run)

    @r.post("/api/exams", status_code=201)
    def add_exam(body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return {"exam": service.add_exam(con, body, get_courses),
                        "updatedAt": store.updated_at(con)}
        return _errors(run)

    @r.post("/api/exams/sync")
    def sync_exams() -> dict:
        """e클래스 공지에서 시험을 다시 찾는다 (F5-R01). 파일을 새로 내려받지는 않는다 — 수집은 F6 몫이다."""
        def run():
            with store.connect() as con:
                out = service.sync_notices(con, notify=notify, get_courses=get_courses)
                return {**out, "exams": service.overview(con, get_courses)["exams"],
                        "updatedAt": store.updated_at(con)}
        return _errors(run)

    @r.get("/api/exams/today")
    def exams_today() -> dict:
        with store.connect() as con:
            return service.today_block(con, None, service.course_map(get_courses))

    @r.get("/api/study-calendar")
    def study_calendar(start: str, end: str) -> dict:
        """공부 캘린더 데이터 — 날짜마다 과목·시간·분량 + 그날의 시험 (2026-10-01)."""
        def run():
            with store.connect() as con:
                return service.study_calendar(con, start, end, get_courses, extra=extra_blocks)
        return _errors(run)

    @r.get("/study-calendar", include_in_schema=False)
    def study_calendar_page() -> FileResponse:
        """공부 캘린더 화면 — 이 폴더(F5_Test_agent/web)에 있는 한 장짜리 페이지. 대시보드와 같은 서버가 준다."""
        page = C.ROOT / "web" / "study_calendar.html"
        if not page.exists():
            raise HTTPException(404, "공부 캘린더 화면 파일이 없습니다")
        return FileResponse(page, media_type="text/html; charset=utf-8", headers={"Cache-Control": "no-cache"})

    @r.get("/api/exams/settings")
    def exam_settings() -> dict:
        """난이도 시간 설정(쪽당 분, 기본 쉬움 1 · 보통 1.5 · 어려움 2) + 저녁 시간대(기본 19:00~24:00, 계획 전용)."""
        with store.connect() as con:
            return {"difficulties": service.difficulty_view(con), "evening": service.evening_view(con),
                    "updatedAt": store.updated_at(con)}

    @r.put("/api/exams/settings")
    def put_exam_settings(body: dict[str, Any] = Body(...)) -> dict:
        """{difficulty?: {easy?, normal?, hard?}, evening?: {start?, end?}} — 값이 null 이면 기본값으로."""
        def run():
            body_ = body or {}
            if "difficulty" not in body_ and "evening" not in body_:
                raise service.Invalid("difficulty 또는 evening 을 주세요")
            with store.connect() as con:
                if "difficulty" in body_:
                    service.set_difficulty_minutes(con, body_.get("difficulty") or {})
                if "evening" in body_:
                    service.set_evening(con, body_.get("evening"))
                return {"difficulties": service.difficulty_view(con), "evening": service.evening_view(con),
                        "updatedAt": store.updated_at(con)}
        return _errors(run)

    @r.get("/api/exams/courses")
    def exam_courses() -> dict:
        """과목별 시험 유무 + 그 과목의 중간·기말 상태 (2026-10-01 — 모든 과목은 중간·기말을 본다고 둔다)."""
        def run():
            with store.connect() as con:
                today = date.today()
                made = defaults.ensure(con, today, get_courses)
                return {"courses": service.course_settings_view(con, service.course_map(get_courses), today),
                        "periods": defaults.period_view(academic.periods(service.semester_of(today))),
                        "hints": made.get("hints", []), "updatedAt": store.updated_at(con)}
        return _errors(run)

    @r.patch("/api/exams/courses/{course_id}")
    def patch_exam_course(course_id: str, body: dict[str, Any] = Body(...)) -> dict:
        """{midterm?: bool, final?: bool} — 끄면 임의 일정을 치우고, 켜면 바로 다시 잡는다."""
        def run():
            with store.connect() as con:
                return service.set_course_exams(con, course_id, body, get_courses)
        return _errors(run)

    @r.get("/api/exams/{exam_id}")
    def get_exam(exam_id: str) -> dict:
        # id 에 ':' 가 들어간다(`ex:74245:a1b2c3d4`) — 경로 조각 안의 ':' 는 그대로 받힌다(슬래시만 못 들어간다).
        # /sync · /today 를 **먼저** 등록해 두었으므로 그 두 경로가 여기로 흘러오지 않는다.
        def run():
            with store.connect() as con:
                return service.detail(con, exam_id, get_courses)
        return _errors(run)

    @r.patch("/api/exams/{exam_id}")
    def patch_exam(exam_id: str, body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return {"exam": service.patch_exam(con, exam_id, body, get_courses),
                        "updatedAt": store.updated_at(con)}
        return _errors(run)

    @r.delete("/api/exams/{exam_id}")
    def delete_exam(exam_id: str) -> dict:
        def run():
            with store.connect() as con:
                return {**service.delete_exam(con, exam_id), "updatedAt": store.updated_at(con)}
        return _errors(run)

    # ── 공부 완료 체크 (2026-10-06) — 서비스 밖에서 공부한 강의자료 ──

    @r.get("/api/exams/{exam_id}/materials")
    def exam_materials(exam_id: str) -> dict:
        def run():
            with store.connect() as con:
                return service.study_materials(con, exam_id, get_courses)
        return _errors(run)

    @r.patch("/api/exams/{exam_id}/materials")
    def patch_exam_materials(exam_id: str, body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return service.set_study_materials(con, exam_id, body, get_courses)
        return _errors(run)

    @r.patch("/api/exams/{exam_id}/ready")
    def patch_exam_ready(exam_id: str, body: dict[str, Any] = Body(...)) -> dict:
        def run():
            with store.connect() as con:
                return {"exam": service.set_ready(con, exam_id, body, get_courses),
                        "updatedAt": store.updated_at(con)}
        return _errors(run)

    # ── 학습 계획 ──

    @r.post("/api/study-plans/preview")
    def preview_plan(body: dict[str, Any] = Body(...)) -> dict:
        """계획 계산만 — 저장하지 않는다 (F5-R30 · S05)."""
        def run():
            exam_id = str(body.get("examId") or "")
            if not exam_id:
                raise service.Invalid("examId 를 넣어 주세요")
            with store.connect() as con:
                return service.preview(con, exam_id, _options(body), get_courses=get_courses)
        return _errors(run)

    @r.post("/api/study-plans", status_code=201)
    def create_plan(body: dict[str, Any] = Body(...)) -> dict:
        """미리보기를 등록한다 (F5-R31) — 학습 블록이 생겨 공부 캘린더(/study-calendar)에 나온다."""
        def run():
            exam_id = str(body.get("examId") or "")
            if not exam_id:
                raise service.Invalid("examId 를 넣어 주세요")
            with store.connect() as con:
                return service.create_plan(con, exam_id, _options(body), get_courses=get_courses,
                                           keep_done=bool(body.get("keepDone", True)))
        return _errors(run)

    @r.get("/api/study-plans/{plan_id}")
    def get_plan(plan_id: str) -> dict:
        def run():
            with store.connect() as con:
                return service.plan_detail(con, service.parse_plan_id(plan_id), get_courses=get_courses)
        return _errors(run)

    @r.delete("/api/study-plans/{plan_id}")
    def cancel_plan(plan_id: str) -> dict:
        def run():
            with store.connect() as con:
                return service.cancel_plan(con, service.parse_plan_id(plan_id))
        return _errors(run)

    @r.post("/api/study-plans/{plan_id}/rebalance")
    def rebalance_plan(plan_id: str, body: Optional[dict[str, Any]] = Body(None)) -> dict:
        """재조정 미리보기 (F5-R34) — 확인해야 캘린더가 바뀐다(자동 변경 없음)."""
        def run():
            with store.connect() as con:
                return service.rebalance(con, service.parse_plan_id(plan_id), _options(body or {}),
                                         get_courses=get_courses)
        return _errors(run)

    @r.get("/api/study-plans/{plan_id}/days/{when}")
    def get_day(plan_id: str, when: str) -> dict:
        def run():
            with store.connect() as con:
                return service.day_detail(con, service.parse_plan_id(plan_id), when, get_courses)
        return _errors(run)

    @r.delete("/api/study-plans/{plan_id}/days/{when}")
    def delete_day(plan_id: str, when: str) -> dict:
        """학습 블록 하나 지우기 — 완료한 것도. 마지막 블록이면 계획도 지운다 (2026-10-02)."""
        def run():
            with store.connect() as con:
                return service.delete_day(con, service.parse_plan_id(plan_id), when)
        return _errors(run)

    @r.patch("/api/study-plans/{plan_id}/days/{when}")
    def patch_day(plan_id: str, when: str, body: dict[str, Any] = Body(...)) -> dict:
        """완료 체크 {done: true} · 다른 날로 옮기기 {date: 'YYYY-MM-DD'} (F5-R32·R33)."""
        def run():
            with store.connect() as con:
                return service.patch_day(con, service.parse_plan_id(plan_id), when, body,
                                         get_courses=get_courses)
        return _errors(run)

    return r


_OPTION_KEYS = ("unit", "totalPages", "totalMinutes", "pageMinutes", "difficulty", "reviewDays",
                "excludedDates", "includeQuiz", "quizCount", "startDate",
                "scopeWeeks", "scopeMaterialIds", "studyDays", "studyDates", "dayMinutes")


def _options(body: dict) -> dict:
    """요청 본문에서 계획 옵션만 골라낸다 — 조정안의 `apply` 를 그대로 덮어써도 되게 (F5-R24).

    모르는 항목은 조용히 버린다: 화면이 미리보기 결과를 그대로 되돌려 보내는 흐름이라
    (`등록하기` → 방금 본 미리보기 옵션) 계산에 쓰지 않는 값이 섞여 들어온다."""
    out = {k: body[k] for k in _OPTION_KEYS if k in body}
    for k, v in (body.get("apply") or {}).items():
        if k in _OPTION_KEYS:
            out[k] = v
    return out


__all__ = ["build_router", "status_summary", "calendar_events", "today_block", "sync", "touch"]
