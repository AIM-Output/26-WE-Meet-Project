"""C0 OS 공통 계층 — Windows·macOS(·리눅스)에서 달라지는 것만 여기 모은다. 표준 라이브러리만.

기능 폴더는 OS 를 직접 묻지 않고 이 함수를 부른다 (WE-Meet_데스크톱앱_맥지원_계획.md 3·6절).

    venv_python(dir)   가상환경 안의 python   Windows .venv\\Scripts\\python.exe / 그 외 .venv/bin/python
    pid_alive(pid)     그 pid 가 살아 있는 python 프로세스인가   Windows tasklist / 그 외 os.kill(pid, 0)
    NO_WINDOW          subprocess creationflags — Windows 는 콘솔 창을 띄우지 않고, 그 외는 0
    script(name)       이 OS 의 런처 파일 이름 (안내 문구용)   Windows setup.cmd / 맥 setup.command
    venv.ensure(...)   가상환경 만들기·패키지·Chromium (osenv/venv.py — setup.cmd 가 하던 일)

데스크톱 앱(PyInstaller 로 묶은 실행 파일 하나 — FROZEN)에서는 기능마다 .venv 가 없다. 자식 프로세스는
'같은 실행 파일을 다른 모드로' 띄운다 (univ_us_local/backend/desktop.py 의 --run-module).
    FROZEN                          묶인 실행 파일로 도는 중인가
    module_cmd(venv, mod, *args)    venv python -X utf8 -m mod … / 묶였으면 <실행 파일> --run-module mod …
    python_ready(venv)              그 명령을 띄울 수 있는가 (venv python 이 있거나 묶였거나)
    browsers_dir(venv)              Playwright Chromium 자리 — PLAYWRIGHT_BROWSERS_PATH 가 있으면 그것(앱 데이터 폴더)
    appdata                         앱 데이터 폴더 (osenv/appdata.py)

빌려 쓰는 법 (다른 기능 폴더를 빌리는 기존 방식과 같다 — 폴더 경로 환경변수 + sys.path):

    C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
    if str(C0_AGENT_DIR) not in sys.path:
        sys.path.append(str(C0_AGENT_DIR))
    from osenv import venv_python

패키지 이름이 `platform` 이 아닌 이유: 표준 라이브러리 platform 을 가린다 (C1 의 calendar 와 같은 함정).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

IS_WINDOWS = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FROZEN = bool(getattr(sys, "frozen", False))


def venv_python(venv_dir: str | os.PathLike) -> Path:
    """가상환경 폴더 안의 python 실행 파일 자리 (있는지는 보지 않는다)."""
    d = Path(venv_dir)
    return d / "Scripts" / "python.exe" if IS_WINDOWS else d / "bin" / "python"


def module_cmd(venv_dir: str | os.PathLike, module: str, *args: str) -> list[str]:
    """`python -m module args` 를 띄울 명령. 묶인 앱이면 venv 대신 같은 실행 파일(--run-module).
    -m 처럼 현재 폴더(cwd)를 import 경로 맨 앞에 두므로, 부르는 쪽은 지금처럼 cwd 를 기능 폴더로 준다."""
    if FROZEN:
        return [sys.executable, "--run-module", module, *args]
    return [str(venv_python(venv_dir)), "-X", "utf8", "-m", module, *args]


def python_ready(venv_dir: str | os.PathLike) -> bool:
    return FROZEN or venv_python(venv_dir).exists()


def browsers_dir(venv_dir: str | os.PathLike) -> Path:
    """Playwright Chromium 폴더. 앱 데이터 폴더를 쓰면(appdata.apply) PLAYWRIGHT_BROWSERS_PATH 가 그곳을 가리킨다."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    return Path(env) if env and env != "0" else Path(venv_dir) / "pw-browsers"


INSTALLING_MARK = ".univus-installing"                     # 데스크톱 앱이 첫 실행 때 Chromium 을 받는 동안 둔다


def chromium_state(path: str | os.PathLike) -> str:
    """'ready' · 'installing'(내려받는 중) · 'missing'. 폴더가 있으면 준비된 것으로 본다 (저장소 setup 과 같은 기준)."""
    p = Path(path)
    if (p / INSTALLING_MARK).exists():
        return "installing"
    return "ready" if p.is_dir() else "missing"


def script(name: str) -> str:
    """런처 파일 이름 — 안내 문구가 Windows 사용자에게는 .cmd, 맥 사용자에게는 .command 를 말하게."""
    return f"{name}.cmd" if IS_WINDOWS else f"{name}.command"


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
    except PermissionError:                                 # 살아 있지만 남의 프로세스
        pass
    except OSError:
        return False
    return True


__all__ = ["IS_WINDOWS", "IS_MAC", "NO_WINDOW", "FROZEN", "venv_python", "module_cmd", "python_ready", "browsers_dir",
           "INSTALLING_MARK", "chromium_state",
           "script", "pid_alive"]
