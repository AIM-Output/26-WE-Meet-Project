"""자동 로그인 정보 API (/api/login/creds) — 비밀번호는 돌려주지 않고, 잘못된 값은 저장하지 않는다. 저장소(DPAPI·키체인)는 가짜."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    from login import api, auth, config as C
    saved = {}
    monkeypatch.setattr(C, "CRED_FILE", tmp_path / "cred.bin")

    def save(username, password):
        saved.update(username=username, password=password)
        C.CRED_FILE.write_bytes(b"x")

    def clear():
        existed = C.CRED_FILE.exists()
        saved.clear()
        C.CRED_FILE.unlink(missing_ok=True)
        return existed

    monkeypatch.setattr(auth, "save", save)
    monkeypatch.setattr(auth, "load", lambda: dict(saved) if saved else None)
    monkeypatch.setattr(auth, "clear", clear)
    app = FastAPI()
    app.include_router(api.build_router())
    return TestClient(app), saved


def test_save_show_clear(client):
    c, saved = client
    assert c.get("/api/login/creds").json()["saved"] is False
    r = c.put("/api/login/creds", json={"username": " 2024123456 ", "password": "p@ss word"})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] and body["username"] == "2024123456"          # 앞뒤 공백은 지운다
    assert "p@ss word" not in r.text                                   # 비밀번호는 돌려주지 않는다
    assert saved == {"username": "2024123456", "password": "p@ss word"}  # 비밀번호 속 공백은 그대로
    assert "password" not in c.get("/api/login/creds").json()
    assert c.delete("/api/login/creds").json()["saved"] is False
    assert saved == {}


@pytest.mark.parametrize("body", [
    {"username": "", "password": "x"},
    {"username": "20 24", "password": "x"},
    {"username": "2024123456", "password": ""},
    {"username": "2024123456", "password": "a\nb"},
    {"username": "2024123456"},
])
def test_rejects_bad_input(client, body):
    c, saved = client
    assert c.put("/api/login/creds", json=body).status_code == 422
    assert saved == {}
