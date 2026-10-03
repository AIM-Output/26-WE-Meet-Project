"""대시보드에서 수집 띄우기 — run-sync.cmd 를 백그라운드로 실행하고 진행 상태를 알려 준다 (F1-R05, D7).

수집은 이 폴더의 .venv(requests·bs4) 에서 돈다. 대시보드 백엔드는 이 파일(표준 라이브러리만)만 import 한다.
univ_us_local/backend/app/eclass_data.py 의 e클래스 동기화와 같은 방식:
  - 이 서버가 띄운 실행은 _state 로, 예약 작업·수동 실행은 state/sync.lock(pid) 으로 안다.
  - 이미 돌고 있으면 새로 띄우지 않는다 (진짜 중복 방지는 pipeline 의 잠금이 한다 → exit 3).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from datetime import datetime
from typing import Any, Optional

from . import config as C

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "keys": None}


def _read_json(path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, errors="replace", timeout=10).stdout
        except Exception:
            return False
        return f'"{pid}"' in out and "python" in out.lower()
    import os
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def sync_state() -> dict:
    """{running, started_at, finished_at, exit_code, source(button|external), by(button|manual|schedule|catchup|retry),
    keys, results, retry({attempt, next_at} — 예약 수집이 재시도를 기다리는 중)}"""
    from .schedule import pending_retry
    retry = pending_retry(_pid_alive)
    with _lock:
        mine = dict(_state)
    if mine["running"]:
        return {**mine, "source": "button", "by": "button", "results": None, "retry": retry}
    lock = _read_json(C.LOCK_FILE)
    if isinstance(lock, dict) and isinstance(lock.get("pid"), int) and _pid_alive(lock["pid"]):
        return {"running": True, "started_at": lock.get("started_at"), "finished_at": None, "exit_code": None,
                "source": "external", "by": lock.get("by"), "keys": None, "results": None, "retry": retry}
    last = _read_json(C.LAST_RUN_FILE)
    if isinstance(last, dict) and (last.get("started_at") or "") >= (mine["started_at"] or ""):
        return {"running": False, "started_at": last.get("started_at"), "finished_at": last.get("finished_at"),
                "exit_code": last.get("exit_code"), "source": "external" if not mine["started_at"] else "button",
                "by": last.get("by"), "keys": None, "results": last.get("sources"), "retry": retry}
    return {**mine, "source": "button" if mine["started_at"] else None, "by": "button" if mine["started_at"] else None,
            "results": None, "retry": retry}


def _command(keys: Optional[list[str]]) -> list[str]:
    extra: list[str] = ["--by", "button"]
    for k in keys or []:
        extra += ["--source", k]
    if sys.platform == "win32":
        return ["cmd", "/c", str(C.RUN_SYNC_CMD), *extra]
    py = C.ROOT / ".venv" / "bin" / "python"
    return [str(py if py.exists() else sys.executable), "-m", "bachelor", "sync", "--log", str(C.LOG_FILE), *extra]


def _run(keys: Optional[list[str]]) -> None:
    try:
        proc = subprocess.run(_command(keys), cwd=str(C.ROOT), capture_output=True, timeout=20 * 60)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = -1
    except Exception:
        code = -2
    with _lock:
        _state.update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"), exit_code=code)


def start_sync(keys: Optional[list[str]] = None) -> dict:
    """수집을 백그라운드로 시작. 이미 돌고 있으면 띄우지 않고 already_running 을 붙인다."""
    if sys.platform == "win32" and not C.RUN_SYNC_CMD.exists():
        return {**sync_state(), "error": f"run-sync.cmd 가 없습니다: {C.RUN_SYNC_CMD}"}
    st = sync_state()
    if st["running"]:
        return {**st, "already_running": True}
    with _lock:
        if _state["running"]:
            return {**dict(_state), "source": "button", "already_running": True}
        _state.update(running=True, started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None,
                      exit_code=None, keys=keys)
    threading.Thread(target=_run, args=(keys,), daemon=True).start()
    return sync_state()


# ── 작업 스케줄러 (예약 수집 — schedule.py) ─────────────────

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_task_cache: dict[str, Any] = {"at": 0.0, "value": None}


def task_info(force: bool = False) -> dict:
    """예약 작업 {available, registered, name, at, state, nextRun, lastRun, lastResult, pathOk, scheduled(새 방식인가)}.
    PowerShell 이라 1~2초 걸려 1분 동안 기억한다."""
    import time as _t
    if not C.tasks_enabled():
        return {"available": False, "registered": False, "at": C.SCHEDULE_AT}
    if not force and _task_cache["value"] is not None and _t.time() - _task_cache["at"] < 60:
        return _task_cache["value"]
    n = C.TASK_NAME
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              f"$t = Get-ScheduledTask -TaskName '{n}' -ErrorAction SilentlyContinue; if ($t) {{ "
              f"$i = Get-ScheduledTaskInfo -TaskName '{n}'; "
              "[pscustomobject]@{ state = [string]$t.State; "
              "args = (($t.Actions | ForEach-Object { \"$($_.Execute) $($_.Arguments)\" }) -join ' | '); "
              "next = if ($i.NextRunTime) { $i.NextRunTime.ToString('s') } else { $null }; "
              "last = if ($i.LastRunTime -and $i.LastRunTime.Year -gt 2000) { $i.LastRunTime.ToString('s') } else { $null }; "
              "result = $i.LastTaskResult } | ConvertTo-Json -Compress }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True,
                             timeout=20, creationflags=NO_WINDOW)
        text = out.stdout.decode("utf-8", "replace").strip()
        t = json.loads(text) if text else None
    except Exception as e:                           # noqa: BLE001
        return {"available": False, "registered": False, "at": C.SCHEDULE_AT,
                "error": f"작업 스케줄러를 읽지 못했습니다: {e}"[:200]}
    info: dict[str, Any] = {"available": True, "registered": False, "name": n, "at": C.SCHEDULE_AT}
    if isinstance(t, dict):
        args = str(t.get("args") or "").lower()
        info.update(registered=True, state=t.get("state"), nextRun=t.get("next"), lastRun=t.get("last"),
                    lastResult=t.get("result"), pathOk=str(C.ROOT).lower() in args,
                    scheduled="run-scheduled.cmd" in args)        # 예전 등록(06·18시 run-sync.cmd)이면 False → 다시 등록
    _task_cache.update(at=_t.time(), value=info)
    return info


def _task_script(*extra: str) -> dict:
    if not C.tasks_enabled():
        return {"ok": False, "error": "이 서버에서는 작업 스케줄러를 쓰지 않습니다 (F1_TASKS=off)"}
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File",
           str(C.ROOT / "register-task.ps1"), *extra]
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=60, creationflags=NO_WINDOW)
        ok, text = p.returncode == 0, (p.stdout + p.stderr).decode("utf-8", "replace").strip()
    except Exception as e:                           # noqa: BLE001
        ok, text = False, str(e)
    _task_cache.update(at=0.0, value=None)
    return {"ok": ok, "output": text[-800:], "error": None if ok else "작업 스케줄러를 바꾸지 못했습니다"}


def register_task() -> dict:
    """매일 SCHEDULE_AT + 로그인 시 예약 수집 (register-task.ps1)."""
    return _task_script("-At", C.SCHEDULE_AT)


def unregister_task() -> dict:
    return _task_script("-Remove")


def last_log_lines(n: int = 15) -> list[str]:
    try:
        lines = C.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [l for l in lines if l.strip()][-n:]
