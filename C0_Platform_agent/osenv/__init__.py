"""C0 OS 공통 계층 — Windows·macOS(·리눅스)에서 달라지는 것만 여기 모은다. 표준 라이브러리만.

기능 폴더는 OS 를 직접 묻지 않고 이 함수를 부른다 (WE-Meet_데스크톱앱_맥지원_계획.md 3·6절).

    venv_python(dir)   가상환경 안의 python   Windows .venv\\Scripts\\python.exe / 그 외 .venv/bin/python
    pid_alive(pid)     그 pid 가 살아 있는 python 프로세스인가   Windows tasklist / 그 외 os.kill(pid, 0)
    NO_WINDOW          subprocess creationflags — Windows 는 콘솔 창을 띄우지 않고, 그 외는 0
    run_group(cmd, timeout, **kw)   자식을 새 프로세스 그룹으로 띄워 기다림 — 시간 초과·kill_children()(사이드카 종료) 때 그룹째 끈다
    venv.ensure(...)   가상환경 만들기·패키지·Chromium (osenv/venv.py — 사이드카 빌드·개발용 desktop/sidecar/.venv)

기능마다 .venv 를 두지 않는다 — 데스크톱 앱(PyInstaller 로 묶은 실행 파일 하나 — FROZEN)이든 개발 모드(desktop/sidecar/.venv
의 python 으로 desktop.py)든, 자식 프로세스(수집기·로그인 창·예약 실행)는 **지금 도는 python 을 다른 모드로** 띄운다.
    FROZEN                    묶인 실행 파일로 도는 중인가
    module_cmd(mod, *args)    <python> -X utf8 -m mod … / 묶였으면 <실행 파일> --run-module mod … (univ_us_local/backend/desktop.py)
    task_command(mod, *args)  작업 스케줄러용 PowerShell 명령 (register-task.ps1 -Command)
    browsers_dir()            Playwright Chromium 자리 — PLAYWRIGHT_BROWSERS_PATH(앱 데이터 폴더) 또는 지금 python 의 venv/pw-browsers
    appdata                   앱 데이터 폴더 (osenv/appdata.py)

빌려 쓰는 법 (다른 기능 폴더를 빌리는 기존 방식과 같다 — 폴더 경로 환경변수 + sys.path):

    C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
    if str(C0_AGENT_DIR) not in sys.path:
        sys.path.append(str(C0_AGENT_DIR))
    from osenv import venv_python

패키지 이름이 `platform` 이 아닌 이유: 표준 라이브러리 platform 을 가린다 (C1 의 calendar 와 같은 함정).
"""
from __future__ import annotations

import atexit
import os
import re
import signal
import subprocess
import sys
import threading
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FROZEN = bool(getattr(sys, "frozen", False))


def venv_python(venv_dir: str | os.PathLike) -> Path:
    """가상환경 폴더 안의 python 실행 파일 자리 (있는지는 보지 않는다)."""
    d = Path(venv_dir)
    return d / "Scripts" / "python.exe" if IS_WINDOWS else d / "bin" / "python"


def module_cmd(module: str, *args: str) -> list[str]:
    """`python -m module args` 를 지금 도는 python 으로 띄울 명령. 묶인 앱이면 같은 실행 파일(--run-module).
    -m 처럼 현재 폴더(cwd)를 import 경로 맨 앞에 두므로, 부르는 쪽은 cwd 를 기능 폴더로 준다."""
    if FROZEN:
        return [sys.executable, "--run-module", module, *args]
    return [sys.executable, "-X", "utf8", "-m", module, *args]


def task_command(module: str, *args: str) -> str:
    """Windows 작업 스케줄러(register-task.ps1 -Command)가 부를 PowerShell 명령 — module_cmd 를 `& '<실행 파일>' …` 로.
    묶인 앱이면 `& '<앱 실행 파일>' --run-module <mod> …`. 작업은 환경변수 없이 돌고 WorkingDirectory 가 기능 폴더다."""
    exe, *rest = module_cmd(module, *args)
    q = lambda s: "'" + str(s).replace("'", "''") + "'"   # noqa: E731 — PowerShell 작은따옴표 문자열
    return " ".join(["&", q(exe), *(a if re.fullmatch(r"[\w.-]+", a) else q(a) for a in rest)])


def browsers_dir() -> Path:
    """Playwright Chromium 폴더. 앱·개발 모드는 desktop.py 가 PLAYWRIGHT_BROWSERS_PATH 를 정한다(앱 데이터 폴더 / venv).
    명령줄에서 python -m … 으로 바로 부르면 그 python 의 venv 안 pw-browsers."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    return Path(env) if env and env != "0" else Path(sys.prefix) / "pw-browsers"


INSTALLING_MARK = ".univus-installing"                     # 데스크톱 앱이 첫 실행 때 Chromium 을 받는 동안 둔다


def chromium_state(path: str | os.PathLike) -> str:
    """'ready' · 'installing'(내려받는 중) · 'missing'. 폴더가 있으면 준비된 것으로 본다 (저장소 setup 과 같은 기준)."""
    p = Path(path)
    if (p / INSTALLING_MARK).exists():
        return "installing"
    return "ready" if p.is_dir() else "missing"


def pid_alive(pid: int) -> bool:
    """pid 가 살아 있는 python 프로세스인가.
    Windows 는 tasklist 로 본다 (os.kill 은 Windows 에서 신호 확인이 아니라 프로세스를 죽인다).
    이름에 python 이 있는지까지 보는 것은 pid 재사용으로 남의 프로세스를 잠금 주인으로 오인하지 않기 위해서다."""
    if IS_WINDOWS:
        try:
            out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                                 capture_output=True, text=True, errors="replace", timeout=10,
                                 creationflags=NO_WINDOW).stdout
        except Exception:                                   # noqa: BLE001
            return False
        low = out.lower()
        return f'"{pid}"' in out and ("python" in low or (FROZEN and Path(sys.executable).name.lower() in low))
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:                                 # 다른 사용자의 프로세스 — 잠금을 쓰는 건 늘 내 프로세스이니
        return False                                        # pid 가 재사용된 것 (그대로 두면 sync.lock 이 영영 안 풀린다)
    except OSError:
        return False
    return True


_children: set = set()
_children_lock = threading.Lock()


def _kill_group(p: subprocess.Popen) -> None:
    """맥·리눅스는 프로세스 그룹째(Chromium 손자까지) SIGKILL. Windows 는 taskkill /T 로 자식 트리째."""
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True, timeout=5,
                           creationflags=NO_WINDOW)
            p.kill()                                        # taskkill 이 없거나 실패해도 자식은 끈다
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except Exception:                                       # noqa: BLE001 — 이미 끝났다
        pass


def run_group(cmd: list[str], timeout: float, **kw) -> int:
    """subprocess.run(cmd, timeout=…) 대신 — 자식(수집기·로그인 창)을 새 프로세스 그룹으로 띄워 끝날 때까지 기다리고 종료 코드를 돌려준다.
    시간 초과면 그룹째 끄고 TimeoutExpired 를 그대로 올린다. 사이드카가 끝날 때(kill_children) 살아 있는 자식도 그룹째 끈다.
    stdout·stderr 를 주지 않으면 버린다 (수집기는 --log 파일에 쓴다)."""
    kw.setdefault("stdout", subprocess.DEVNULL)
    kw.setdefault("stderr", subprocess.DEVNULL)
    with subprocess.Popen(cmd, start_new_session=not IS_WINDOWS, **kw) as p:
        with _children_lock:
            _children.add(p)
        try:
            return p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(p)
            raise
        finally:
            with _children_lock:
                _children.discard(p)


def kill_children() -> None:
    """run_group 으로 띄운 아직 살아 있는 자식을 그룹째 끈다. 여러 번 불러도 되고 예외를 내지 않는다 (atexit · 사이드카 종료 처리)."""
    with _children_lock:
        alive = list(_children)
    for p in alive:
        _kill_group(p)


atexit.register(kill_children)

__all__ = ["IS_WINDOWS", "IS_MAC", "NO_WINDOW", "FROZEN", "venv_python", "module_cmd", "task_command", "browsers_dir",
           "INSTALLING_MARK", "chromium_state", "pid_alive", "run_group", "kill_children"]
