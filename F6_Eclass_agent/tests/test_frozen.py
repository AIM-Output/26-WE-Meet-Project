"""묶인 데스크톱 앱(FROZEN) — 수집·로그인·예약 실행이 venv python 대신 앱 실행 파일(--run-module)을 부른다."""
import sys


def test_frozen_commands(monkeypatch):
    import osenv
    from eclass import config as C, jobs
    monkeypatch.setattr(osenv, "FROZEN", True)
    monkeypatch.setattr(C, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", r"C:\Users\학생\AppData\Local\UnivUs\sidecar\univus-backend.exe")

    assert C.module_cmd(C.C3_VENV, "eclass", "sync") == [sys.executable, "--run-module", "eclass", "sync"]
    args = jobs._frozen_task_args("eclass", r"C:\Users\O'Neil\UnivUs\F6_Eclass_agent\state\sync.log")
    assert args[0] == "-Command"
    assert args[1].startswith(f"& '{sys.executable}' --run-module eclass tick --log ")
    assert "O''Neil" in args[1]                                    # PowerShell 작은따옴표 이스케이프


def test_not_frozen_keeps_cmd(monkeypatch):
    from eclass import config as C, jobs
    monkeypatch.setattr(C, "FROZEN", False)
    assert jobs._frozen_task_args("eclass", "x.log") == []           # 저장소 실행은 run-scheduled.cmd 그대로
