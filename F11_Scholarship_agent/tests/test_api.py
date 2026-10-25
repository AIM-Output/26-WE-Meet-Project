"""API — 라우터를 작은 FastAPI 앱에 붙여 부른다 (대시보드와 같은 방식)."""
from conftest import PROFILE, add_notice
from fastapi import FastAPI
from fastapi.testclient import TestClient

from scholarship import api, store

FULL = ("1. 지원자격: 본교 2학년 이상 재학생\n2. 성적기준: 직전학기 평점 3.0/4.5 이상\n"
        "3. 신청기간: 2026. 10. 1.(수) ~ 2099. 10. 20.(월) 18:00\n4. 제출서류: 장학금 신청서 1부\n")


def client(events=None):
    app = FastAPI()
    made = events if events is not None else []
    app.include_router(api.build_router(lambda: dict(PROFILE), lambda ev: made.append(ev) or {"id": "9", **ev}))
    return TestClient(app)


def test_flow():
    with store.connect() as con:
        add_notice(con, "www:1", "[장학안내] [(재)좋은장학재단] 장학생 선발", FULL)
    c = client()
    ov = c.get("/api/scholarships").json()
    assert ov["items"][0]["id"] == "www:1" and "sync" in ov
    d = c.get("/api/scholarships/items/www:1").json()
    assert d["reasons"] and d["documents"] == ["장학금 신청서 1부"]
    assert c.post("/api/scholarships/items/www:1/draft", json={}).status_code == 409    # 재료부터
    assert c.put("/api/scholarships/materials", json={"careerGoal": "AI 연구"}).json()["exists"]
    d = c.post("/api/scholarships/items/www:1/draft", json={}).json()
    assert d["draft"]["body"].startswith("# [신청서 초안]")
    d = c.put("/api/scholarships/items/www:1/draft", json={"body": "고친 초안"}).json()
    assert d["draft"]["body"] == "고친 초안"
    d = c.patch("/api/scholarships/items/www:1", json={"progress": "approved"}).json()
    assert d["progress"] == "approved"
    assert c.patch("/api/scholarships/items/www:1", json={"progress": "bogus"}).status_code == 422
    d = c.post("/api/scholarships/items/www:1/calendar").json()
    assert d["onCalendar"]
    assert c.get("/api/scholarships/items/nope").status_code == 404
    assert c.delete("/api/scholarships/materials").json()["exists"] is False


def test_sources_endpoint():
    c = client()
    rows = c.get("/api/scholarships/sources").json()["sources"]
    assert any(r["key"] == "aicoss" and r["enabled"] for r in rows)
    r = c.patch("/api/scholarships/sources/greenbio", json={"enabled": True}).json()
    assert r["enabled"] and r["userSet"]
    assert c.patch("/api/scholarships/sources/nope", json={"enabled": True}).status_code == 404


def test_status_summary_with_push():
    pushed = []
    with store.connect() as con:
        add_notice(con, "www:1", "[장학안내] [(재)좋은장학재단] 장학생 선발", FULL)
    st = api.status_summary(lambda: dict(PROFILE), lambda *a: pushed.append(a))
    assert st["available"] and st["eligible"] == 1 and "sync" in st
