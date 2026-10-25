"""대시보드에서 수집 띄우기 — `-m scholarship sync` 를 백그라운드로 실행하고 진행 상태를 알려 준다. 표준 라이브러리만.

수집은 자식 프로세스(지금 도는 python / 묶인 앱 실행 파일 — osenv.module_cmd)에서 돈다.
새 예약 작업(작업 스케줄러·launchd)은 만들지 않는다 — 앱이 떠 있는 동안 06:00·18:00 이 지나면 /api/status 가
maybe_autosync 로 한 번 띄우고, 앱이 꺼져 있었으면 켜졌을 때 따라잡는다 (트레이에 숨어 있어도 돈다).
"""
from __future__ import annotations

import json
import subprocess
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

from . import config as C

_lock = threading.Lock()
_state: dict[str, Any] = {"running": False, "started_at": None, "finished_at": None, "exit_code": None, "by": None}
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _read_json(path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def sync_state() -> dict:
    """{running, started_at, finished_at, exit_code, by, results}"""
    with _lock:
        mine = dict(_state)
    if mine["running"]:
        return {**mine, "results": None}
    lock = _read_json(C.LOCK_FILE)
    if isinstance(lock, dict) and isinstance(lock.get("pid"), int) and C.pid_alive(lock["pid"]):
        return {"running": True, "started_at": lock.get("started_at"), "finished_at": None, "exit_code": None,
                "by": "external", "results": None}
    last = _read_json(C.LAST_RUN_FILE)
    if isinstance(last, dict) and (last.get("started_at") or "") >= (mine["started_at"] or ""):
        return {"running": False, "started_at": last.get("started_at"), "finished_at": last.get("finished_at"),
                "exit_code": last.get("exit_code"), "by": last.get("by"), "results": last.get("sources")}
    return {**mine, "results": None}


def _command(keys: Optional[list[str]], profile: Optional[dict], by: str) -> list[str]:
    extra = ["--by", by]
    p = profile or {}
    for flag, key in (("--college", "college"), ("--dept", "department"), ("--major", "major")):
        if p.get(key):
            extra += [flag, str(p[key])]
    for k in keys or []:
        extra += ["--source", k]
    return C.module_cmd("scholarship", "sync", *extra)


def _run(cmd: list[str]) -> None:
    try:
        proc = subprocess.run(cmd, cwd=str(C.ROOT), capture_output=True, timeout=C.SYNC_TIMEOUT_MIN * 60,
                              creationflags=NO_WINDOW)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = -1
    except Exception:                                    # noqa: BLE001 — 띄우지 못함 — 이유는 sync.log 에
        code = -2
    with _lock:
        _state.update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"), exit_code=code)


def start_sync(keys: Optional[list[str]] = None, profile: Optional[dict] = None, by: str = "button") -> dict:
    st = sync_state()
    if st["running"]:
        return {**st, "already_running": True}
    with _lock:
        if _state["running"]:
            return {**dict(_state), "already_running": True}
        _state.update(running=True, started_at=datetime.now().isoformat(timespec="seconds"), finished_at=None,
                      exit_code=None, by=by)
    threading.Thread(target=_run, args=(_command(keys, profile, by),), daemon=True).start()
    return sync_state()


def last_slot(now: datetime) -> datetime:
    """가장 최근에 지난 수집 시각(06:00·18:00)."""
    cands = []
    for day in (now.date(), now.date() - timedelta(days=1)):
        for s in C.SYNC_SLOTS:
            h, m = (int(x) for x in s.split(":"))
            t = datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)
            if t <= now:
                cands.append(t)
    return max(cands)


def due(now: Optional[datetime] = None) -> Optional[str]:
    """지금 자동 수집을 띄울 때인가 → 'schedule'(제때) · 'catchup'(놓친 주기) · None."""
    now = now or datetime.now()
    st = sync_state()
    if st["running"]:
        return None
    slot = last_slot(now)
    started = st.get("started_at")
    if started and datetime.fromisoformat(started) >= slot:
        return None
    if started and st.get("exit_code") not in (0, 2, None) and datetime.fromisoformat(started) > now - timedelta(minutes=30):
        return None                                      # 방금 실패했다 — 30분 뒤에 다시
    return "schedule" if now - slot < timedelta(minutes=30) else "catchup"


def maybe_autosync(profile: Optional[dict], now: Optional[datetime] = None) -> Optional[dict]:
    by = due(now)
    return start_sync(None, profile, by) if by else None


def last_log_lines(n: int = 15) -> list[str]:
    try:
        lines = C.LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    return [l for l in lines if l.strip()][-n:]
