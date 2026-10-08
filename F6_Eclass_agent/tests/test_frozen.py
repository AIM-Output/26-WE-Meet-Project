"""예약 실행·수집 명령 — 묶인 데스크톱 앱(FROZEN)은 앱 실행 파일(--run-module), 개발 모드는 지금 도는 python -m."""
import sys


def test_frozen_commands(monkeypatch):
    import osenv
    from eclass import config as C, jobs
    monkeypatch.setattr(osenv, "FROZEN", True)
    monkeypatch.setattr(C, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", r"C:\Users\학생\AppData\Local\UnivUs\sidecar\univus-backend.exe")
    monkeypatch.setattr(C, "LOG_FILE", r"C:\Users\O'Neil\UnivUs\F6_Eclass_agent\state\sync.log")

    assert C.module_cmd("eclass", "sync") == [sys.executable, "--run-module", "eclass", "sync"]
    args = jobs._task_args()
    assert args[0] == "-Command"
    assert args[1].startswith(f"& '{sys.executable}' --run-module eclass tick --log ")   # 설치본이 등록해 온 모양 그대로
    assert "O''Neil" in args[1]                                    # PowerShell 작은따옴표 이스케이프


def test_dev_mode_uses_running_python(monkeypatch):
    import osenv
    from eclass import jobs
    monkeypatch.setattr(osenv, "FROZEN", False)
    args = jobs._task_args()
    assert args[1].startswith(f"& '{sys.executable}' -X utf8 -m eclass tick --log ")
