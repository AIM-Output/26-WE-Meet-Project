"""C0 osenv.venv — 이미 된 단계는 건너뛰고, requirements 가 바뀌면 다시 설치하는가 (네트워크 없이 _run 을 가짜로)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import osenv  # noqa: E402
from osenv import venv as V  # noqa: E402


@pytest.fixture
def fake(monkeypatch, tmp_path):
    """명령을 기록하고, venv 생성을 흉내 낸다."""
    calls = []

    def run(cmd, log):
        calls.append(cmd)
        if cmd[1:3] == ["-m", "venv"]:
            py = osenv.venv_python(cmd[3])
            py.parent.mkdir(parents=True, exist_ok=True)
            py.write_text("")
        return 0

    monkeypatch.setattr(V, "_run", run)
    req = tmp_path / "requirements.txt"
    req.write_text("requests\n")
    return calls, tmp_path / ".venv", req


def kinds(calls):
    return [c[2] for c in calls]                            # venv · pip


def test_creates_installs_then_skips(fake):
    calls, venv, req = fake
    py = V.ensure(venv, req)
    assert py == osenv.venv_python(venv)
    assert kinds(calls) == ["venv", "pip"]
    calls.clear()
    V.ensure(venv, req)                                     # 두 번째: 할 일 없음
    assert calls == []


def test_reinstalls_when_requirements_change(fake):
    calls, venv, req = fake
    V.ensure(venv, req)
    calls.clear()
    req.write_text("requests\nbeautifulsoup4\n")            # git pull 로 목록이 바뀜
    V.ensure(venv, req)
    assert kinds(calls) == ["pip"]


def test_pip_failure_raises_and_keeps_stamp_unset(fake, monkeypatch):
    calls, venv, req = fake
    V.ensure(venv, None)                                    # venv 만
    monkeypatch.setattr(V, "_run", lambda cmd, log: 1)
    with pytest.raises(V.VenvError):
        V.ensure(venv, req)
    assert not (venv / V.STAMP).exists()                    # 다음 실행에서 다시 시도
