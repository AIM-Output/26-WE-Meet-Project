"""맥 예약 수집 — 매일 SCHEDULE_AT + 로그인 시, launchd(C0 osenv.launchd)로. launchctl·venv 생성은 가짜."""
import plistlib
import subprocess
import sys
from pathlib import Path


def test_register_info_unregister(monkeypatch, tmp_path):
    from bachelor import config as C, runner
    import osenv
    from osenv import launchd

    def run(args):
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(sys, "platform", "darwin")
    monkeypatch.setattr(osenv, "IS_WINDOWS", False)            # venv_python·script 도 맥처럼
    monkeypatch.setattr(launchd, "AGENTS_DIR", tmp_path / "LaunchAgents")
    monkeypatch.setattr(launchd, "_uid", lambda: 501)
    monkeypatch.setattr(launchd, "_run", run)
    monkeypatch.setattr(runner, "_prepare", lambda: None)  # .venv 만들기는 건너뛴다
    runner._task_cache.update(at=0.0, value=None)

    assert C.tasks_enabled()
    assert runner.register_task()["ok"]
    pl = plistlib.loads(launchd.plist_path(C.LAUNCHD_LABEL).read_bytes())
    h, m = (int(x) for x in C.SCHEDULE_AT.split(":"))
    assert pl["StartCalendarInterval"] == [{"Hour": h, "Minute": m}]
    assert pl["ProgramArguments"][1:] == ["-X", "utf8", "-m", "bachelor", "tick", "--log", str(C.LOG_FILE)]
    assert Path(pl["ProgramArguments"][0]).parts[-3:] == (".venv", "bin", "python")

    info = runner.task_info(force=True)
    assert info["registered"] and info["scheduled"] and info["pathOk"] and info["at"] == C.SCHEDULE_AT and info["nextRun"]
    assert runner.unregister_task()["ok"]
    assert runner.task_info(force=True)["registered"] is False
