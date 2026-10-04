"""C0 osenv.launchd · osenv.creds(키체인) — launchctl·keyring 을 가짜로 바꿔 Windows 에서도 돈다."""
import plistlib
import subprocess
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from osenv import creds, launchd  # noqa: E402


@pytest.fixture
def lctl(monkeypatch, tmp_path):
    """launchctl 호출을 기록. print 는 올라가 있는 것처럼 답한다."""
    calls = []

    def run(args):
        calls.append(args)
        out = "state = not running\n\tlast exit code = 0\n" if args[1] == "print" else ""
        return subprocess.CompletedProcess(args, 0, out, "")

    monkeypatch.setattr(launchd, "AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr(launchd, "_uid", lambda: 501)
    monkeypatch.setattr(launchd, "_run", run)
    return calls


def test_register_writes_plist_and_bootstraps(lctl, tmp_path):
    root = tmp_path / "F6_Eclass_agent"
    res = launchd.register("kr.univus.test", ["/py", "-m", "eclass", "tick"], workdir=root,
                           times=[(0, 0), (4, 0)], env={"F6_STATE_DIR": "/s"}, log=tmp_path / "launchd.log")
    assert res["ok"]
    pl = plistlib.loads(launchd.plist_path("kr.univus.test").read_bytes())
    assert pl["ProgramArguments"] == ["/py", "-m", "eclass", "tick"]
    assert pl["StartCalendarInterval"] == [{"Hour": 0, "Minute": 0}, {"Hour": 4, "Minute": 0}]
    assert pl["RunAtLoad"] is True                          # 로그인할 때·켠 직후 한 번 (놓친 주기 따라잡기)
    assert pl["EnvironmentVariables"] == {"PYTHONUTF8": "1", "F6_STATE_DIR": "/s"}
    assert pl["WorkingDirectory"] == str(root)
    assert lctl[0] == ["launchctl", "bootout", "gui/501/kr.univus.test"]
    assert lctl[1][:3] == ["launchctl", "bootstrap", "gui/501"]


def test_info_and_unregister(lctl, tmp_path):
    root = tmp_path / "F1_Bachelor_agent"
    assert launchd.info("kr.univus.t", root) == {"available": True, "registered": False, "name": "kr.univus.t"}
    launchd.register("kr.univus.t", ["/py"], workdir=root, times=[(8, 0)])
    i = launchd.info("kr.univus.t", root)
    assert i["registered"] and i["pathOk"] and i["state"] == "not running" and i["lastResult"] == 0
    assert launchd.info("kr.univus.t", tmp_path / "옛 폴더")["pathOk"] is False      # 폴더를 옮기면 다시 등록하라고
    assert launchd.unregister("kr.univus.t")["ok"]
    assert not launchd.plist_path("kr.univus.t").exists()


@pytest.fixture
def fake_keyring(monkeypatch):
    store = {}

    class PasswordDeleteError(Exception):
        pass

    def delete(s, a):
        if (s, a) not in store:
            raise PasswordDeleteError
        del store[(s, a)]

    mod = types.SimpleNamespace(set_password=lambda s, a, p: store.__setitem__((s, a), p),
                                get_password=lambda s, a: store.get((s, a)), delete_password=delete)
    monkeypatch.setitem(sys.modules, "keyring", mod)
    return store


def test_keychain_roundtrip(fake_keyring):
    creds.keychain_set("svc", "acc", "비밀")
    assert creds.keychain_get("svc", "acc") == "비밀"
    assert creds.keychain_delete("svc", "acc") is True
    assert creds.keychain_delete("svc", "acc") is False
    assert creds.keychain_get("svc", "acc") is None


def test_keychain_without_keyring(monkeypatch):
    monkeypatch.setitem(sys.modules, "keyring", None)      # import keyring → ImportError
    with pytest.raises(creds.CredsError):
        creds.keychain_get("svc", "acc")
