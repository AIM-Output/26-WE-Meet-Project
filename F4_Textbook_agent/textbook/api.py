"""대시보드(univ_us_local)에 붙이는 F4 API — FastAPI APIRouter. (Frontend-Route 9-8)

    GET    /api/materials?course=&kind=&q=      과목 요약 + 자료 목록 (F4-S01·S02)
    GET    /api/materials/status                가벼운 상태 — 마지막 스캔·건수 (화면 폴링용)
    POST   /api/materials/scan                  수집 폴더를 다시 훑는다 (쪽수·해시 다시 읽기: ?force=1)
    POST   /api/materials?course=&name=         직접 추가 — **본문이 파일 그대로** (F4-R02)
    GET    /api/materials/{id}                  자료 하나 (같은 활동의 다른 파일·중복 여부 포함)
    DELETE /api/materials/{id}                  직접 추가한 파일만 삭제 (F4-R08)
    GET    /api/materials/{id}/file?download=1  원문 열기 / 내려받기 (F4-S05)

업로드가 multipart 가 아닌 이유: 사이드카에 python-multipart 를 더 묶지 않으려고 **본문에 파일을 그대로**
받는다(`fetch(url, {method:'POST', body: file})`). 파일 이름·과목은 쿼리로 온다. 설치할 것이 없다는 규칙이 먼저다.

요약·예상 문제·질문(F4-R10~R34)은 아직 없다. 자리를 비워 두었을 뿐이므로 `analysis.available = false` 로 알린다.
의존성: fastapi + 표준 라이브러리. 과목 목록은 get_courses() (e클래스 courses.json 을 백엔드가 읽은 모양).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from . import config as C
from . import catalog, service, store

CoursesGetter = Callable[[], list[dict]]


def _errors(fn: Callable[[], Any]) -> Any:
    try:
        return fn()
    except service.Invalid as e:
        raise HTTPException(422, str(e))
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except service.Conflict as e:
        raise HTTPException(409, str(e))
    except ValueError as e:                              # catalog.abs_path — 자료 폴더 밖의 경로
        raise HTTPException(400, str(e))


# ---------------------------------------------------------------- 백엔드가 직접 부르는 것

def status_summary() -> dict:
    """/api/status 의 materials 칸 — 기능 타일 숫자 (F4-S01)."""
    with store.connect() as con:
        catalog.ensure_scan(con)
        return service.status_summary(con)


def overview(get_courses: Optional[CoursesGetter] = None, course: Optional[str] = None) -> dict:
    with store.connect() as con:
        scan = catalog.ensure_scan(con)
        return service.overview(con, get_courses, course=course, scan=scan)


def touch() -> None:
    """다른 기능이 자료 목록을 다시 읽게 한다 (e클래스 수집이 끝났을 때 백엔드가 부른다)."""
    with store.connect() as con:
        catalog.ensure_scan(con)


# ---------------------------------------------------------------- 라우터

def build_router(get_courses: Optional[CoursesGetter] = None) -> APIRouter:
    r = APIRouter(tags=["F4 강의자료"])

    @r.get("/api/materials")
    def list_materials(course: Optional[str] = None, kind: Optional[str] = Query(None),
                       q: Optional[str] = None, force: bool = False) -> dict:
        if kind and kind not in C.KIND_LABEL:
            raise HTTPException(422, f"종류는 {', '.join(C.KIND_LABEL)} 중 하나입니다")
        with store.connect() as con:
            scan = catalog.ensure_scan(con, force=force)
            return service.overview(con, get_courses, course=course, kind=kind, q=q, scan=scan)

    @r.get("/api/materials/status")
    def materials_status() -> dict:
        with store.connect() as con:
            scan = catalog.ensure_scan(con)
            return {**service.status_summary(con), "scan": scan, "source": service.source_block()}

    @r.post("/api/materials/scan")
    def rescan(force: bool = False) -> dict:
        """수집 폴더를 다시 훑는다. force=1 이면 쪽수·해시까지 전부 다시 읽는다 (F4-R07)."""
        with store.connect() as con:
            scan = catalog.scan(con, force=force)
            return service.overview(con, get_courses, scan=scan)

    @r.post("/api/materials")
    async def add_material(request: Request, course: str = Query(..., description="e클래스 과목 id"),
                           name: str = Query(..., description="파일 이름 (확장자 포함)")) -> dict:
        """직접 추가 (F4-R02) — 요청 본문이 파일 내용 그대로다."""
        limit = C.MAX_FILE_MB * 1024 * 1024
        declared = request.headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > limit:
            raise HTTPException(413, f"{C.MAX_FILE_MB}MB 가 넘는 파일은 받지 않습니다")
        with store.connect() as con:
            dest = _errors(lambda: service.upload_target(con, course, name, get_courses))
        tmp = dest.with_name(dest.name + ".part")
        written = 0
        try:
            with tmp.open("wb") as f:
                async for chunk in request.stream():
                    written += len(chunk)
                    if written > limit:
                        raise HTTPException(413, f"{C.MAX_FILE_MB}MB 가 넘는 파일은 받지 않습니다")
                    f.write(chunk)
            if written == 0:
                raise HTTPException(422, "빈 파일입니다")
            tmp.replace(dest)
        except HTTPException:
            tmp.unlink(missing_ok=True)
            raise
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise HTTPException(500, f"파일을 저장하지 못했습니다: {e}")
        with store.connect() as con:
            material = _errors(lambda: service.finish_upload(con, dest, get_courses))
        return {"material": material, "updatedAt": material["addedAt"]}

    @r.get("/api/materials/{material_id}")
    def get_material(material_id: str) -> dict:
        with store.connect() as con:
            return _errors(lambda: service.detail(con, material_id))

    @r.delete("/api/materials/{material_id}")
    def delete_material(material_id: str) -> dict:
        with store.connect() as con:
            out = _errors(lambda: service.delete(con, material_id))
            return {**out, "updatedAt": store.updated_at(con)}

    @r.get("/api/materials/{material_id}/file")
    def get_file(material_id: str, download: bool = False, page: Optional[int] = None) -> FileResponse:
        """원문 열기 (F4-S05) — 브라우저에 바로 그리거나(inline) 내려받는다(download=1).

        `page` 는 화면이 `#page=12` 로 붙여 쓰는 값이라 서버는 쓰지 않는다 — 주소를 그대로 공유해도 같은 쪽이 열리게."""
        with store.connect() as con:
            path, filename, mime = _errors(lambda: service.file_target(con, material_id))
        return FileResponse(path, media_type=mime, filename=filename,
                            content_disposition_type="attachment" if download else "inline",
                            headers={"Cache-Control": "private, max-age=60"})

    return r


__all__ = ["build_router", "status_summary", "overview", "touch"]
