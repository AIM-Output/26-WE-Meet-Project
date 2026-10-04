"""C0 osenv — OS 분기 (python -m pytest C0_Platform_agent/tests -q)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import osenv  # noqa: E402


def test_venv_python_windows(monkeypatch):
    monkeypatch.setattr(osenv, "IS_WINDOWS", True)
    assert osenv.venv_python("x/.venv") == Path("x/.venv/Scripts/python.exe")


def test_venv_python_posix(monkeypatch):
    monkeypatch.setattr(osenv, "IS_WINDOWS", False)
    assert osenv.venv_python(Path("x/.venv")) == Path("x/.venv/bin/python")


def test_pid_alive_self():
    assert osenv.pid_alive(os.getpid())                     # 이 테스트를 돌리는 python


def test_pid_alive_dead():
    assert not osenv.pid_alive(2 ** 22 + 12345)             # 쓰이지 않을 pid
