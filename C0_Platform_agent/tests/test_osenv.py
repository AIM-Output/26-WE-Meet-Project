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


def test_pid_alive_other_users_pid_is_not_ours(monkeypatch):
    if osenv.IS_WINDOWS:
        return
    def eperm(pid, sig):
        raise PermissionError
    monkeypatch.setattr(osenv.os, "kill", eperm)
    assert not osenv.pid_alive(1)                           # 재부팅 뒤 남의 프로세스가 같은 pid → 남은 잠금은 죽은 것


def test_pid_alive_dead():
    assert not osenv.pid_alive(2 ** 22 + 12345)             # 쓰이지 않을 pid


def _wait_dead(pid, secs=3.0):
    import time
    end = time.time() + secs
    while time.time() < end and osenv.pid_alive(pid):
        time.sleep(0.05)
    return not osenv.pid_alive(pid)


def test_run_group_timeout_kills_grandchild(tmp_path):
    """시간 초과면 자식만이 아니라 손자(Chromium 같은)까지 그룹째 끈다 — subprocess.run 은 손자를 남겼다."""
    if osenv.IS_WINDOWS:
        return
    import subprocess
    import pytest
    f = tmp_path / "pid"
    with pytest.raises(subprocess.TimeoutExpired):
        osenv.run_group(["sh", "-c", f"sleep 30 & echo $! > {f}; wait"], 1)
    assert _wait_dead(int(f.read_text()))


def test_kill_children_stops_running_group(tmp_path):
    """사이드카 종료(kill_children) 때 아직 도는 자식 그룹을 끈다 — 기다리던 run_group 도 곧바로 돌아온다."""
    if osenv.IS_WINDOWS:
        return
    import threading
    import time
    f = tmp_path / "pid"
    codes = []
    t = threading.Thread(target=lambda: codes.append(
        osenv.run_group(["sh", "-c", f"sleep 30 & echo $! > {f}; wait"], 60)))
    t.start()
    end = time.time() + 5
    while time.time() < end and not (f.exists() and f.read_text().strip()):
        time.sleep(0.05)
    osenv.kill_children()
    osenv.kill_children()                                   # 여러 번 불러도 된다
    t.join(5)
    assert not t.is_alive() and codes and codes[0] != 0
    assert _wait_dead(int(f.read_text()))
