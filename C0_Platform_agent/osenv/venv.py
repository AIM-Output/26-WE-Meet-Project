"""가상환경 만들기·패키지 맞추기·Chromium 받기 — Windows setup.cmd 가 하던 일을 OS 무관하게.

    ensure(venv_dir, requirements, chromium=False, log=None)   없으면 만들고, requirements 가 바뀌었으면 다시 설치

맥 런처(*.command)와 대시보드(F1 학사일정 동기화 버튼)가 같이 쓴다. 다시 불러도 안전하다 — 이미 된 단계는 건너뛴다.
requirements 는 내용 해시를 .venv/.univus-requirements 에 적어 두고, `git pull` 로 목록이 바뀌었을 때만 pip 를 다시 돌린다.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import IO, Optional

from . import NO_WINDOW, venv_python

STAMP = ".univus-requirements"


class VenvError(RuntimeError):
    """사람이 읽을 이유를 담는다 (화면·로그에 그대로 쓴다)."""


def browsers_dir(venv_dir: str | os.PathLike) -> Path:
    """Playwright Chromium 자리 — C3 config.BROWSERS 와 같은 규칙(.venv/pw-browsers)."""
    return Path(venv_dir) / "pw-browsers"


def has_chromium(venv_dir: str | os.PathLike) -> bool:
    d = browsers_dir(venv_dir)
    return d.is_dir() and any(p.name.startswith("chromium") for p in d.iterdir())


def _req_hash(req: Path) -> str:
    return hashlib.sha256(req.read_bytes()).hexdigest()


def _run(cmd: list[str], log: Optional[IO[str]], env: Optional[dict] = None) -> int:
    if log is None:                                   # 터미널: 진행 상황을 그대로 보여 준다
        return subprocess.run(cmd, env=env).returncode
    log.flush()
    return subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, creationflags=NO_WINDOW).returncode


def _say(log: Optional[IO[str]], msg: str) -> None:
    print(msg, file=log or sys.stdout, flush=True)


def ensure(venv_dir: str | os.PathLike, requirements: str | os.PathLike | None = None, *, chromium: bool = False,
           log: Optional[IO[str]] = None, base_python: Optional[str] = None) -> Path:
    """venv 의 python 경로를 돌려준다. 실패하면 VenvError."""
    venv_dir = Path(venv_dir)
    py = venv_python(venv_dir)
    steps = 1 + bool(requirements) + bool(chromium)
    n = 0

    n += 1
    if not py.exists():
        _say(log, f"[{n}/{steps}] 가상환경(.venv) 만드는 중...")
        if _run([base_python or sys.executable, "-m", "venv", str(venv_dir)], log) != 0 or not py.exists():
            raise VenvError(f"가상환경을 만들지 못했습니다: {venv_dir} — Python 3.10 이상이 설치돼 있는지 확인하세요")

    if requirements:
        n += 1
        req = Path(requirements)
        stamp = venv_dir / STAMP
        want = _req_hash(req)
        try:
            have = stamp.read_text(encoding="utf-8").strip()
        except OSError:
            have = ""
        if have != want:
            _say(log, f"[{n}/{steps}] 패키지 설치 중... ({req.name})")
            if _run([str(py), "-m", "pip", "install", "--disable-pip-version-check", "-q", "-r", str(req)], log) != 0:
                raise VenvError("패키지 설치에 실패했습니다 — 인터넷 연결을 확인하고 다시 실행하세요")
            stamp.write_text(want, encoding="utf-8")

    if chromium:
        n += 1
        if not has_chromium(venv_dir):
            _say(log, f"[{n}/{steps}] 브라우저(Chromium) 내려받는 중... (수백 MB, 몇 분 걸릴 수 있음)")
            env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(browsers_dir(venv_dir))}
            if _run([str(py), "-m", "playwright", "install", "chromium"], log, env) != 0:
                raise VenvError("브라우저 내려받기에 실패했습니다 — 인터넷 연결을 확인하고 다시 실행하세요")
    return py
