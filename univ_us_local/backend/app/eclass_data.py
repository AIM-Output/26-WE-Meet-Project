"""eclass_agent 가 내려받은 JSON(courses / deadlines / assignments)을 캘린더 이벤트로 바꾼다.

읽기만 한다. 수집(sync)은 eclass_agent/run-sync.cmd 를 백그라운드로 띄우는 것으로 끝이고,
결과는 다음 요청 때 파일에서 다시 읽는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import config as C

COURSE_RE = re.compile(r"^(?P<short>.*?)\s*\[(?P<section>\d+)\]\s*\((?P<code>[A-Za-z0-9]+)\)\s*$")


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except Exception:
        return default


def _iso(s: str) -> Optional[str]:
    """'2026-09-16 16:00' → '2026-09-16T16:00:00' (로컬 시각, tz 없음)."""
    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            continue
    return None


def split_course(name: str) -> dict:
    m = COURSE_RE.match(name or "")
    if not m:
        return {"short": name, "section": "", "code": ""}
    return {"short": m.group("short").strip(), "section": m.group("section"), "code": m.group("code")}


# ---------------------------------------------------------------- 과목

def load_courses() -> list[dict]:
    raw = _read_json(C.ECLASS_DATA_DIR / "courses.json", [])
    out = []
    for i, c in enumerate(raw):
        parts = split_course(c.get("name", ""))
        out.append({
            "id": str(c.get("id", i)),
            "name": c.get("name", ""),
            "short": parts["short"],
            "code": parts["code"],
            "section": parts["section"],
            "url": c.get("url", ""),
            "color": C.COURSE_PALETTE[i % len(C.COURSE_PALETTE)],
            "activityCount": len(c.get("activities", []) or []),
        })
    return out


def _course_index(courses: list[dict]) -> dict[str, dict]:
    return {c["name"]: c for c in courses}


# ---------------------------------------------------------------- 마감 → 이벤트

def _deadline_id(item: dict) -> str:
    key = f"{item.get('url','')}|{item.get('course','')}|{item.get('name','')}|{item.get('due','')}"
    return "dl:" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def load_deadline_events() -> tuple[list[dict], Optional[str]]:
    """deadlines.json (+ assignments.json 의 설명·채점 상태) → FullCalendar 이벤트 목록, updated_at."""
    dl = _read_json(C.ECLASS_DATA_DIR / "deadlines.json", {})
    items = dl.get("items", []) if isinstance(dl, dict) else (dl or [])
    updated_at = dl.get("updated_at") if isinstance(dl, dict) else None

    assigns = {a.get("url"): a for a in _read_json(C.ECLASS_DATA_DIR / "assignments.json", []) or []}
    courses = _course_index(load_courses())

    events = []
    for it in items:
        due = _iso(it.get("due", ""))
        if not due:
            continue
        start = _iso(it.get("start", ""))
        course = courses.get(it.get("course", ""), None)
        parts = split_course(it.get("course", ""))
        status = it.get("status", "") or ""
        submitted = "완료" in status
        a = assigns.get(it.get("url"), {})
        ev = {
            "id": _deadline_id(it),
            "title": it.get("name", ""),
            "start": start or due,
            "end": due if start else None,
            "allDay": False,
            "editable": False,
            "extendedProps": {
                "kind": "deadline",
                "type": it.get("type", ""),
                "source": it.get("source", ""),
                "due": due,
                "course": it.get("course", ""),
                "courseShort": parts["short"],
                "courseCode": parts["code"],
                "courseColor": course["color"] if course else "#64748b",
                "status": status,
                "submitted": submitted,
                "graded": a.get("graded", ""),
                "description": a.get("description", ""),
                "attachmentCount": len(a.get("attachments", []) or []),
                "url": it.get("url", ""),
            },
        }
        events.append(ev)
    return events, updated_at


# ---------------------------------------------------------------- 동기화(수집) 실행
#
# 이 서버가 띄운 실행은 _sync_state 로, 예약 작업(작업 스케줄러)·수동 실행은 sync.py 가 잡는
# state/sync.lock(pid) 으로 안다. 버튼을 누르면 둘 다 보고, 잠금 파일이 없어도 sync.py 프로세스가 있으면
# 새로 띄우지 않는다. 진짜 중복 방지는 sync.py 쪽 잠금이 한다 (겹치면 그쪽이 exit 3 으로 물러난다).

_sync_lock = threading.Lock()
_sync_state: dict[str, Any] = {"running": False, "started_at": None, "finished_at": None, "exit_code": None}


def _pid_alive(pid: int) -> bool:
    """pid 가 살아 있는 python 프로세스인가. Windows 는 tasklist 로 본다 (os.kill 은 Windows 에서 프로세스를 죽인다)."""
    if sys.platform == "win32":
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, errors="replace", timeout=10).stdout
        except Exception:
            return False
        return f'"{pid}"' in out and "python" in out.lower()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _external_run() -> Optional[dict]:
    """sync.lock 이 있고 그 pid 가 살아 있으면 그 내용 — 예약 작업이나 수동 실행이 도는 중."""
    info = _read_json(C.ECLASS_LOCK_FILE, None)
    if isinstance(info, dict) and isinstance(info.get("pid"), int) and _pid_alive(info["pid"]):
        return info
    return None


def _sync_processes() -> list[int]:
    """eclass_agent 의 sync.py 를 돌리고 있는 프로세스 pid 목록 — 잠금 파일이 없어도(지웠거나 옛 버전) 잡아낸다.
    Windows 는 PowerShell CIM 으로 명령줄을 본다 (1초쯤 걸리므로 버튼을 누를 때만 부른다)."""
    if sys.platform == "win32":
        script = ("Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | Where-Object { "
                  "$_.CommandLine -match 'sync\\.py' -and "
                  "\"$($_.ExecutablePath)\".StartsWith($env:ECLASS_AGENT_DIR, 'OrdinalIgnoreCase') } | "
                  "ForEach-Object { $_.ProcessId }")
        cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]
        env = {**os.environ, "ECLASS_AGENT_DIR": str(C.ECLASS_AGENT_DIR)}
    else:
        cmd, env = ["pgrep", "-f", f"{C.ECLASS_AGENT_DIR}.*sync\\.py"], None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=15, env=env).stdout
    except Exception:
        return []
    return [int(x) for x in out.split() if x.isdigit()]


def sync_state() -> dict:
    """진행 상태. source: button(이 서버가 띄움) / external(예약 작업·수동). 안 돌고 있으면 가장 최근 실행의 결과."""
    with _sync_lock:
        mine = dict(_sync_state)
    if mine["running"]:
        return {**mine, "source": "button", "pid": None}
    ext = _external_run()
    if ext:
        return {"running": True, "started_at": ext.get("started_at"), "finished_at": None, "exit_code": None,
                "source": "external", "pid": ext["pid"]}
    last = _read_json(C.ECLASS_LAST_RUN_FILE, {})
    if isinstance(last, dict) and (last.get("started_at") or "") > (mine["started_at"] or ""):
        return {"running": False, "started_at": last.get("started_at"), "finished_at": last.get("finished_at"),
                "exit_code": last.get("exit_code"), "source": "external", "pid": None}
    return {**mine, "source": "button" if mine["started_at"] else None, "pid": None}


def _run_sync() -> None:
    try:
        proc = subprocess.run(
            ["cmd", "/c", str(C.ECLASS_SYNC_CMD)],
            cwd=str(C.ECLASS_AGENT_DIR),
            capture_output=True,
            timeout=30 * 60,
        )
        code = proc.returncode
    except subprocess.TimeoutExpired:
        code = -1
    except Exception:
        code = -2
    with _sync_lock:
        _sync_state.update(running=False, finished_at=datetime.now().isoformat(timespec="seconds"), exit_code=code)


def start_sync() -> dict:
    """run-sync.cmd 를 백그라운드 스레드에서 실행. 이미 도는 중이면(이 서버·예약 작업·잠금 없는 프로세스) 띄우지 않고
    already_running 을 붙여 상태만 돌려준다."""
    if not C.ECLASS_SYNC_CMD.exists():
        return {**sync_state(), "error": f"run-sync.cmd 가 없습니다: {C.ECLASS_SYNC_CMD}"}
    st = sync_state()
    if st["running"]:
        return {**st, "already_running": True}
    if pids := _sync_processes():
        return {**st, "already_running": True,
                "error": f"sync.py 가 이미 돌고 있습니다 (pid {pids[0]}, 잠금 파일 없음) — 끝난 뒤 다시 누르세요."}
    with _sync_lock:
        if _sync_state["running"]:
            return {**sync_state(), "already_running": True}
        _sync_state.update(running=True, started_at=datetime.now().isoformat(timespec="seconds"),
                           finished_at=None, exit_code=None)
    threading.Thread(target=_run_sync, daemon=True).start()
    return sync_state()


def last_log_lines(n: int = 12) -> list[str]:
    p = C.ECLASS_STATE_DIR / "sync.log"
    try:
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return []
    return [l for l in lines if l.strip()][-n:]
