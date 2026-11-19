"""직접 추가(POST /api/materials) — 파일·sqlite·스캔이 이벤트 루프 밖(스레드풀)에서 도는지."""
import asyncio

from conftest import make_pdf
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _on_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def test_upload_runs_blocking_work_off_event_loop(eclass, monkeypatch):
    from test_service import courses_getter
    from textbook import api, service
    seen = {}
    for name in ("upload_target", "finish_upload"):
        real = getattr(service, name)

        def wrap(*a, _real=real, _name=name, **kw):
            seen[_name] = _on_loop()
            return _real(*a, **kw)
        monkeypatch.setattr(service, name, wrap)
    app = FastAPI()
    app.include_router(api.build_router(courses_getter))
    r = TestClient(app).post("/api/materials", params={"course": "100", "name": "보충.pdf"}, content=make_pdf(3))
    assert r.status_code == 200, r.text
    assert r.json()["material"]["pages"] == 3
    assert seen == {"upload_target": False, "finish_upload": False}
