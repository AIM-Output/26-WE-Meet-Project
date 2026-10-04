"""자격증명 저장 — 맥은 키체인(가짜 keyring)에 비밀, state 에는 표시 파일만. Windows 형식(ENTROPY 등)은 그대로인지."""
import json
import sys
import types

import pytest


@pytest.fixture
def mac(monkeypatch, tmp_path):
    from login import auth, config as C
    store = {}

    def delete(s, a):
        if (s, a) not in store:
            raise KeyError
        del store[(s, a)]

    monkeypatch.setitem(sys.modules, "keyring", types.SimpleNamespace(
        set_password=lambda s, a, p: store.__setitem__((s, a), p), get_password=lambda s, a: store.get((s, a)),
        delete_password=delete))
    monkeypatch.setattr(auth, "IS_WINDOWS", False)
    monkeypatch.setattr(C, "CRED_FILE", tmp_path / "cred.keychain.json")
    return auth, C, store


def test_keychain_save_load_clear(mac):
    auth, C, store = mac
    assert auth.load() is None
    auth.save("student01", "pw!")
    assert auth.load() == {"username": "student01", "password": "pw!"}
    marker = C.CRED_FILE.read_text(encoding="utf-8")
    assert "pw!" not in marker and json.loads(marker)["store"] == "keychain"      # 디스크에는 비밀이 없다
    assert auth.has_creds()
    assert auth.clear() is True
    assert store == {} and not C.CRED_FILE.exists() and auth.load() is None


def test_marker_without_keychain_item(mac):
    auth, C, store = mac
    C.CRED_FILE.write_text("{}", encoding="utf-8")         # 키체인에서 지워졌으면 None (재로그인은 반자동으로)
    assert auth.load() is None


def test_windows_key_material_unchanged():
    from login import auth
    assert auth.ENTROPY == b"eclass-agent/jnu/v1" and auth.DESCRIPTION == "eclass-agent"
    assert (auth.KEYCHAIN_SERVICE, auth.KEYCHAIN_ACCOUNT) == ("univus-jnu-sso", "default")
