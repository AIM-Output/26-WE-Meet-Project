"""macOS 예약 실행 — launchd 사용자 에이전트 (~/Library/LaunchAgents/<label>.plist). Windows 작업 스케줄러 자리.

    register(label, args, workdir=, times=[(h, m), ...], env=, log=)   plist 를 쓰고 다시 불러온다 (이미 있으면 덮어쓴다)
    unregister(label)                                                 내리고 plist 를 지운다
    info(label, root)                                                 {available, registered, name, state, lastResult, pathOk, args}

Windows 작업과 같은 규칙이 되도록 (F6·F1 register-task.ps1 참고):
  - StartCalendarInterval  정해진 시각마다. 그 시각에 잠자기였으면 깨어나는 대로 한 번(launchd 가 묶어서 한 번만) = StartWhenAvailable
  - RunAtLoad              로그인할 때(에이전트가 올라올 때)와 '켜기'를 누른 직후 한 번 = AtLogOn + 놓친 주기 따라잡기
  - 밀린 주기를 몰아서 돌리지 않는 것·네트워크 재시도(5·15·45분)·겹침 방지는 tick 이 직접 한다(잠금·이력)
  - 사용자 에이전트라 이 맥 사용자가 로그인해 있을 때만 돈다 (비밀번호 저장 불필요)
명령은 launchctl bootstrap/bootout (macOS 10.10+). 테스트는 _run·_uid·AGENTS_DIR 을 바꿔 끼운다.
"""
from __future__ import annotations

import os
import plistlib
import re
import subprocess
from pathlib import Path
from typing import Optional

AGENTS_DIR = Path.home() / "Library" / "LaunchAgents"


def _uid() -> int:
    return os.getuid()                                     # type: ignore[attr-defined]  (맥·리눅스만)


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, errors="replace", timeout=30)


def plist_path(label: str) -> Path:
    return AGENTS_DIR / f"{label}.plist"


def _domain() -> str:
    return f"gui/{_uid()}"


def build(label: str, args: list[str], *, workdir: str | os.PathLike, times: list[tuple[int, int]],
          env: Optional[dict] = None, log: Optional[str | os.PathLike] = None) -> dict:
    d: dict = {
        "Label": label,
        "ProgramArguments": [str(a) for a in args],
        "WorkingDirectory": str(workdir),
        "StartCalendarInterval": [{"Hour": h, "Minute": m} for h, m in times],
        "RunAtLoad": True,
        "ProcessType": "Background",                      # 배터리·성능에 덜 끼어들게 (사람이 기다리는 작업이 아니다)
        "EnvironmentVariables": {"PYTHONUTF8": "1", **{k: str(v) for k, v in (env or {}).items()}},
    }
    if log:                                                # tick 은 --log 로 자기 로그를 쓴다. 여기는 그 밖의 출력(시작 실패 등)
        d["StandardOutPath"] = d["StandardErrorPath"] = str(log)
    return d


def register(label: str, args: list[str], *, workdir: str | os.PathLike, times: list[tuple[int, int]],
             env: Optional[dict] = None, log: Optional[str | os.PathLike] = None) -> dict:
    """{ok, output, error}. 같은 label 이 올라가 있으면 내렸다가 새 plist 로 다시 올린다."""
    path = plist_path(label)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            plistlib.dump(build(label, args, workdir=workdir, times=times, env=env, log=log), f)
        _run(["launchctl", "bootout", f"{_domain()}/{label}"])            # 없으면 실패 — 무시
        p = _run(["launchctl", "bootstrap", _domain(), str(path)])
    except Exception as e:                                 # noqa: BLE001
        return {"ok": False, "output": str(e)[-800:], "error": "예약 실행(launchd)에 등록하지 못했습니다"}
    text = (p.stdout + p.stderr).strip()
    ok = p.returncode == 0
    slots = "·".join(f"{h:02d}:{m:02d}" for h, m in times)
    return {"ok": ok, "output": (text or f"'{label}' 등록 완료 ({slots} + 로그인 시)")[-800:],
            "error": None if ok else "예약 실행(launchd)에 등록하지 못했습니다"}


def unregister(label: str) -> dict:
    path = plist_path(label)
    try:
        p = _run(["launchctl", "bootout", f"{_domain()}/{label}"])
        existed = path.exists()
        path.unlink(missing_ok=True)
    except Exception as e:                                 # noqa: BLE001
        return {"ok": False, "output": str(e)[-800:], "error": "예약 실행을 지우지 못했습니다"}
    return {"ok": True, "output": f"'{label}' 삭제됨." if existed or p.returncode == 0 else f"'{label}' 이(가) 없습니다."}


def info(label: str, root: str | os.PathLike) -> dict:
    """작업 스케줄러 task_info 와 같은 모양. nextRun·lastRun 은 쓰는 쪽이 채운다(주기·실행 이력을 아는 쪽)."""
    path = plist_path(label)
    out: dict = {"available": True, "registered": False, "name": label}
    if not path.exists():
        return out
    try:
        with open(path, "rb") as f:
            pl = plistlib.load(f)
    except Exception:                                      # noqa: BLE001 — 깨진 plist 면 다시 등록하게
        return {**out, "registered": True, "pathOk": False, "state": "broken"}
    args = " ".join(pl.get("ProgramArguments") or []) + " " + str(pl.get("WorkingDirectory") or "")
    out.update(registered=True, args=args, pathOk=str(root) in args, state="not loaded")
    try:
        p = _run(["launchctl", "print", f"{_domain()}/{label}"])
    except Exception:                                      # noqa: BLE001
        return out
    if p.returncode == 0:
        m = re.search(r"^\s*state = (.+)$", p.stdout, re.M)
        out["state"] = m.group(1).strip() if m else "loaded"
        m = re.search(r"last exit code = (-?\d+)", p.stdout)
        if m:
            out["lastResult"] = int(m.group(1))
    return out
