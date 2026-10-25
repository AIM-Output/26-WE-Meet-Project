"""설정(켜기·시각·보관 기간)과 라우터 (Frontend-Route 15-6)."""
import pytest
from conftest import FakeSources

from briefing import service, settings as S


def test_defaults_and_changed():
    v = service.settings_view()
    assert (v["enabled"], v["time"], v["keepDays"]) == (True, "08:00", 30)
    assert v["changed"] == [] and v["keepDaysChoices"] == [7, 14, 30, 60] and v["llm"] is False
    v = service.save_settings({"time": "7:05", "keepDays": 14})
    assert v["time"] == "07:05" and v["keepDays"] == 14 and set(v["changed"]) == {"time", "keepDays"}
    v = service.save_settings({"time": None})
    assert v["time"] == "08:00" and v["changed"] == ["keepDays"]
    v = service.save_settings({}, reset=True)
    assert v["changed"] == []


@pytest.mark.parametrize("patch", [{"time": "25:00"}, {"time": "아침"}, {"keepDays": 10}, {"enabled": "yes"}, {"color": 1}])
def test_invalid_settings(patch):
    with pytest.raises(S.Invalid):
        service.save_settings(patch)


def test_router_roundtrip():
    pytest.importorskip("httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from briefing import api

    f = FakeSources()
    changed = []
    app = FastAPI()
    app.include_router(api.build_router(f.src, on_change=lambda: changed.append(1)))
    c = TestClient(app)

    r = c.patch("/api/settings/briefing", json={"time": "00:00"})          # 언제 돌려도 '예정 시각이 지났다'
    assert r.status_code == 200 and r.json()["time"] == "00:00" and changed == [1]
    assert c.patch("/api/settings/briefing", json={"keepDays": 3}).status_code == 422

    t = c.get("/api/briefing/today").json()
    assert t["state"] == "ready" and t["briefing"]["sections"]
    day = t["briefing"]["date"]

    lst = c.get("/api/briefings?limit=30").json()
    assert [i["date"] for i in lst["items"]] == [day] and "sections" not in lst["items"][0] and lst["keepDays"] == 30
    assert c.get(f"/api/briefings/{day}").json()["id"] == f"br:{day}"
    assert c.get("/api/briefings/2020-01-01").status_code == 404
    assert c.get("/api/briefings/어제").status_code == 422

    b = c.post("/api/briefing/regenerate").json()
    assert b["source"] == "manual" and changed == [1, 1]
    assert c.get("/api/settings/briefing").json()["changed"] == ["time"]
