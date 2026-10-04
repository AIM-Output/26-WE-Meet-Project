"""맥 예약 실행 — task_info·register·unregister 가 launchd(C0 osenv.launchd)로 간다. launchctl 은 가짜."""
import plistlib
import subprocess
import sys

import pytest


@pytest.fixture
def mac(monkeypatch, tmp_path):
    from eclass import config as C, jobs
    import osenv
    from osenv import launchd
    calls = []

    def run(args):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "state = not running\n" if args[1] == "print" else "", "")

    monkeypatch.delenv("F6_TASKS", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(osenv, "IS_WINDOWS", False)            # venv_python·script 도 맥처럼
    monkeypatch.setattr(launchd, "AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr(launchd, "_uid", lambda: 501)
    monkeypatch.setattr(launchd, "_run", run)
    py = tmp_path / "c3py"
    py.write_text("")
    monkeypatch.setattr(C, "C3_PYTHON", py)
    jobs._task_cache.update(at=0.0, value=None)
    return jobs, C, launchd, calls


def test_register_info_unregister(mac):
    jobs, C, launchd, calls = mac
    assert jobs.tasks_enabled()
    res = jobs.register_task(6)
    assert res["ok"], res
    pl = plistlib.loads(launchd.plist_path(C.LAUNCHD_LABEL).read_bytes())
    assert [s["Hour"] for s in pl["StartCalendarInterval"]] == [0, 6, 12, 18]
    assert pl["ProgramArguments"][1:] == ["-X", "utf8", "-m", "eclass", "tick", "--log", str(C.LOG_FILE)]
    env = pl["EnvironmentVariables"]
    assert env["F6_STATE_DIR"] == str(C.STATE_DIR) and env["PLAYWRIGHT_BROWSERS_PATH"]
    assert "PATH" not in env                                # 전체 환경을 plist 에 적지 않는다

    info = jobs.task_info(force=True)
    assert info["available"] and info["registered"] and info["pathOk"] and info["nextRun"]

    assert jobs.unregister_task()["ok"]
    assert jobs.task_info(force=True)["registered"] is False


def test_register_needs_c3(mac, tmp_path, monkeypatch):
    jobs, C, launchd, calls = mac
    monkeypatch.setattr(C, "C3_PYTHON", tmp_path / "없음")
    res = jobs.register_task(4)
    assert not res["ok"] and "setup.command" in res["error"]
    assert calls == []
