"""새로 로그인할 때 싣는 쿠키(fresh_state) — 끝났을 수 있는 SSO 세션 쿠키만 빼고, 신뢰 기기·e클래스 쿠키는 남긴다.
남기면 'SSO 로그인'이 e클래스 첫 화면으로 되돌아오는 고리가 됐다 (2026-10-09). 쿠키 값은 가짜."""
import json


def _cookie(domain, name, expires=-1):
    return {"name": name, "value": "x", "domain": domain, "path": "/", "expires": expires,
            "httpOnly": True, "secure": True, "sameSite": "Lax"}


def test_fresh_state_drops_only_sso_session_cookies(monkeypatch, tmp_path):
    from login import config as C
    from login import session
    f = tmp_path / "storage_state.json"
    f.write_text(json.dumps({"cookies": [
        _cookie("idpm.jnu.ac.kr", "RathonSSO_TrustDevice_abc", 1_900_000_000),   # 신뢰 기기 — 남긴다
        _cookie("idpm.jnu.ac.kr", "WMONID", 1_900_000_000),
        _cookie(".jnu.ac.kr", "RathonSSO_SESSION"),                                # SSO 세션 — 뺀다
        _cookie(".jnu.ac.kr", "SSOValidate"),
        _cookie("sso.jnu.ac.kr", "ASP.NET_SessionId"),
        _cookie("sel.jnu.ac.kr", "MoodleSession"),                                 # e클래스 — 남긴다
    ], "origins": []}), encoding="utf-8")
    monkeypatch.setattr(C, "STATE_FILE", f)
    st = session.fresh_state()
    assert sorted(c["name"] for c in st["cookies"]) == ["MoodleSession", "RathonSSO_TrustDevice_abc", "WMONID"]
    assert st["origins"] == []
    assert len(json.loads(f.read_text(encoding="utf-8"))["cookies"]) == 6     # 저장 파일은 그대로


def test_fresh_state_without_file(monkeypatch, tmp_path):
    from login import config as C
    from login import session
    monkeypatch.setattr(C, "STATE_FILE", tmp_path / "none.json")
    assert session.fresh_state() is None
