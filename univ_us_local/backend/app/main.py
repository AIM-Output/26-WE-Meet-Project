"""유니버스(Univ-Us) 개인 로컬 서버 — FastAPI.

    uvicorn app.main:app --host 127.0.0.1 --port 8000        (backend/ 에서)

- /api/*            프론트가 쓰는 JSON API
- /                 frontend/out (next build 결과) 가 있으면 정적으로 서빙. 없으면 안내 페이지.
개발 중에는 `next dev`(3000) 가 /api 를 여기로 넘겨준다 (frontend/next.config.ts rewrites).

이 파일은 **붙이는 곳**이다. 기능 코드는 전부 기능 폴더에 있다 (C1 캘린더 · F6 · C2 · F1 · F2 · F3 · F4 · F5).
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import academic, attendance, calendar_events, exams, graduation, materials
from . import config as C
from . import eclass_data, student_profile


@asynccontextmanager
async def lifespan(_: FastAPI):
    calendar_events.init()               # C1: 표 만들기 · 옛 자리(univ_us_local/data)의 일정 DB 옮기기
    student_profile.migrate_legacy()     # 예전 kv 프로필이 남아 있으면 C2 로 옮긴다 (한 번)
    yield


app = FastAPI(title="Univ-Us Local", version="0.1.0", docs_url="/api/docs", openapi_url="/api/openapi.json",
              lifespan=lifespan)

# Host 헤더가 localhost/127.0.0.1 이 아니면 거절 (DNS 리바인딩 대비)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=C.ALLOWED_HOSTS)


@app.middleware("http")
async def cache_headers(request: Request, call_next):
    """정적 프론트 캐시 규칙. 헤더가 없으면 브라우저가 옛 index.html 을 추정 캐시로 계속 써서
    `npm run build` 뒤에도 옛 화면이 보인다 → HTML 은 매번 재검증(no-cache), 해시 붙은 _next/static 은 영구 캐시."""
    response = await call_next(request)
    path = request.url.path
    if not path.startswith("/api"):
        if path.startswith("/_next/static/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        else:
            response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.middleware("http")
async def check_origin(request: Request, call_next):
    """브라우저가 보내는 변경 요청은 허용된 Origin 에서만. Origin 이 없는 요청(curl 등)은 로컬 도구로 본다."""
    if request.method in ("POST", "PATCH", "PUT", "DELETE"):
        origin = request.headers.get("origin")
        if origin and origin not in C.ALLOWED_ORIGINS:
            return JSONResponse({"detail": f"허용되지 않은 Origin: {origin}"}, status_code=403)
    return await call_next(request)


# ---------------------------------------------------------------- API

@app.get("/api/courses")
def get_courses() -> list[dict]:
    return eclass_data.load_courses()


@app.get("/api/status")
def get_status() -> dict:
    eclass_data.deliver()                # F6: 때가 된 마감 알림·마감 변경·수집 실패를 알림 센터로 (1분마다 불린다)
    eclass = eclass_data.status_block()
    calendar = calendar_events.summary()
    counts = calendar["counts"]
    return {
        "updated_at": eclass.get("lastOkAt") or eclass.get("reconciledAt"),   # 마지막으로 e클래스 수집에 성공한 시각
        "sync": eclass_data.sync_state(),
        "counts": {
            "courses": len(eclass_data.load_courses()),
            "deadlines": (eclass.get("counts") or {}).get("total", 0),
            "userEvents": counts["total"],
            "todos": counts["todos"],
            "todosDone": counts["done"],
        },
        "categories": calendar["categories"],
        "eclassDataDir": eclass_data.data_dir(),
        "log": eclass_data.last_log_lines(),
        "calendar": calendar,                # C1: 내 일정 DB 자리 · 못 불러왔으면 error
        "eclass": eclass,                    # F6: 진행 중·지난 마감 수 · 연속 실패 · 로그인 필요 · 재시도 · 다음 주기 · updatedAt
        "academic": academic.status(),       # F1: 원천별 수집 상태 · 확인 필요 건수 · updatedAt
        "graduation": graduation.status(),   # F2: 남은 학점 · 판정 · 한 줄 요약 · updatedAt (기능 타일)
        "attendance": attendance.status(),   # F3: 위험 과목 · 확인 안 한 수업 · 시간표 미입력 · updatedAt (기능 타일)
        "materials": materials.status(),     # F4: 강의자료 수 · 쪽수 · 확인 필요 · updatedAt (기능 타일)
        "exams": exams.status(),             # F5: 오늘 분량 · 다가오는 시험 · 확인 필요 · 밀린 계획 · updatedAt (기능 타일)
    }


@app.post("/api/sync")
def post_sync() -> dict:
    """e클래스 수집(F6)을 백그라운드로 띄운다 — 이미 돌고 있으면 새로 띄우지 않는다. 진행 상황은 /api/status 의 sync 로 본다."""
    return eclass_data.start_sync()


def _profile_changed() -> None:
    """프로필이 바뀌면 F1 '내 해당'·F2 졸업요건 기준·F3 학사경고 안내가 달라진다 — updatedAt 을 올려 화면이 다시 받게 한다 (C2-R08)."""
    academic.touch()
    graduation.touch()
    attendance.touch()


# ---------------------------------------------------------------- 기능 라우터

# C1 캘린더 — /api/events (C1_Calendar_agent/calendar_core/api.py)
# 내 일정·할 일은 C1 이 저장하고, 다른 기능이 캘린더에 얹는 일정은 아래 소스 함수로 넘겨준다 (C1 3절).
CALENDAR_SOURCES = (
    lambda start, end: eclass_data.load_deadline_events(),   # F6 과제·퀴즈·동영상 마감 (kind=deadline)
    academic.calendar_events,                                # F1 학사 일정 (kind=academic, 내 캘린더에 등록된 것만)
    attendance.calendar_events,                              # F3 수업 회차 (kind=class)
    exams.calendar_events,                                   # F5 시험(kind=exam) · 학습 블록(kind=study)
)
if (_c1_router := calendar_events.router(CALENDAR_SOURCES)) is not None:
    app.include_router(_c1_router)

# F6 과제·마감 — /api/assignments* · /api/sources/eclass · /api/sync/login (F6_Eclass_agent/eclass/api.py)
# F1 의 /api/sources/{key} 보다 먼저 붙여야 /api/sources/eclass 가 F6 로 간다.
if (_f6_router := eclass_data.router()) is not None:
    app.include_router(_f6_router)

# C2 프로필·학과 마스터 — /api/profile* · /api/master/* (C2_Profile_agent/student/api.py)
if (_c2_router := student_profile.router(on_change=_profile_changed)) is not None:
    app.include_router(_c2_router)

# F1 학사 일정 — /api/academic/* · /api/sources* · /api/notifications* (F1_Bachelor_agent/bachelor/api.py)
if (_f1_router := academic.router()) is not None:
    app.include_router(_f1_router)

# F2 졸업요건 — /api/graduation/* (F2_Graduation_agent/graduation/api.py)
# 이수 내역을 가져올 때 같이 읽은 평점·학년은 C2 프로필에 '자동'으로 넣고, 그러면 F1 도 다시 판정하게 한다.
if (_f2_router := graduation.router(on_profile_change=academic.touch)) is not None:
    app.include_router(_f2_router)

# F3 출결 — /api/attendance/* (F3_Attendance_agent/attendance/api.py)
# 수업 회차는 /api/events 에 kind=class 로 섞이고, 상태가 올라가면 경고가 알림 센터(F1 notifications)에 들어간다.
if (_f3_router := attendance.router()) is not None:
    app.include_router(_f3_router)

# F4 강의자료 — /api/materials* (F4_Textbook_agent/textbook/api.py)
# F6 가 내려받아 둔 파일을 과목별 자료로 세우고, 원문을 이 서버가 스트림으로 넘겨준다 (밖으로는 나가지 않는다).
if (_f4_router := materials.router()) is not None:
    app.include_router(_f4_router)

# F5 시험 공부 일정 — /api/exams* · /api/study-plans* (F5_Test_agent/exams/api.py)
# e클래스 공지에서 시험을 찾아 '확인 필요'로 세우고, 확인한 계획을 학습 블록(kind=study)으로 캘린더에 넣는다.
if (_f5_router := exams.router()) is not None:
    app.include_router(_f5_router)


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
