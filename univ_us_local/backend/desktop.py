"""데스크톱 앱 사이드카 — Tauri 창이 띄우는 로컬 서버. PyInstaller 로 묶으면 univus-backend 실행 파일 하나가 된다.

    desktop.py [--data-root DIR] [--port N] [--log FILE] [--exit-with-stdin] [--no-browser-install]
        앱 데이터 폴더를 잡고(C0 osenv.appdata), 빈 포트에서 서버를 띄운 뒤 준비되면 표준출력에 한 줄을 쓴다:
            UNIVUS_READY {"port": 51234, "launchUrl": "http://127.0.0.1:51234/desktop/launch?code=…", "dataRoot": "…"}
        Tauri 는 이 줄을 읽어 창을 launchUrl 로 연다 → 서버가 한 번 쓰는 코드를 세션 쿠키로 바꿔 준다(app/main.py).
        --exit-with-stdin: 표준입력이 닫히면(앱이 끝나거나 죽으면) 서버도 끝낸다 — 고아 프로세스 방지.
        처음 실행이면 Playwright Chromium 을 앱 데이터 폴더에 백그라운드로 받는다(약 150MB, logs/browsers.log).

    desktop.py --run-module <모듈> [인자…]
        `python -m <모듈>` 과 같다(현재 폴더를 import 경로 맨 앞에). 묶인 앱에는 기능별 .venv 가 없어서
        수집기·로그인 창·예약 실행이 이 실행 파일을 다시 부른다 (osenv.module_cmd · register-task.ps1 -Command · launchd).

저장소에서 그냥 실행해도 된다(개발용): univ_us_local/backend/.venv 의 python 으로 `python desktop.py --data-root <임시 폴더>`.
묶인 앱의 파일 배치는 저장소와 같은 모양이다 — <번들>/univus/{C0…F6 기능 폴더, univ_us_local/backend/app, …/frontend/out}
(desktop/sidecar/univus-backend.spec). 그래서 기능 config 의 PROJECT_ROOT 기본값이 그대로 맞는다.
"""
from __future__ import annotations

import argparse
import json
import os
import runpy
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
# 저장소(개발) = 이 파일에서 두 단계 위 / 묶인 앱 = PyInstaller 압축 해제 폴더 안의 univus/
BUNDLE = Path(getattr(sys, "_MEIPASS", "")) / "univus" if FROZEN else Path(__file__).resolve().parents[2]
BACKEND_DIR = BUNDLE / "univ_us_local" / "backend"
C0_DIR = BUNDLE / "C0_Platform_agent"
READY_PREFIX = "UNIVUS_READY "

if str(C0_DIR) not in sys.path:
    sys.path.append(str(C0_DIR))
from osenv import INSTALLING_MARK, appdata, chromium_state, module_cmd  # noqa: E402


def run_module(module: str, args: list[str]) -> int:
    """`python -m module args` 흉내. 예약 실행은 환경변수 없이 오므로 묶인 앱이면 앱 데이터 폴더를 스스로 잡는다."""
    if FROZEN:
        appdata.apply(appdata.default_root())
    sys.path.insert(0, os.getcwd())
    sys.argv = [module, *args]
    try:
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    except SystemExit as e:                              # 모듈이 sys.exit(n) 으로 끝내는 것이 보통이다
        return e.code if isinstance(e.code, int) else (0 if e.code is None else 1)
    return 0


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _announce(server, port: int, code: str, root: Path) -> None:
    """서버가 소켓을 열면 Tauri 에 준비 줄을 알린다."""
    while not server.started and not server.should_exit:
        time.sleep(0.05)
    if server.started:
        msg = {"port": port, "launchUrl": f"http://127.0.0.1:{port}/desktop/launch?code={code}", "dataRoot": str(root)}
        print(READY_PREFIX + json.dumps(msg, ensure_ascii=False), flush=True)


def _exit_with_stdin(server) -> None:
    try:
        while sys.stdin.read(1):
            pass
    except Exception:                                    # noqa: BLE001
        pass
    server.should_exit = True


def _ensure_browsers(root: Path) -> None:
    """첫 실행이면 Chromium 을 앱 데이터 폴더에 받는다 — 그동안 C3·C2·F2 는 '내려받는 중'이라고 답한다."""
    target = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
    have = target.is_dir() and any(p.name.startswith("chromium") for p in target.iterdir())
    if have and chromium_state(target) != "installing":  # 표시가 남아 있으면 지난 실행이 받다가 끊긴 것 — 다시 받는다
        return
    target.mkdir(parents=True, exist_ok=True)
    mark = target / INSTALLING_MARK
    mark.write_text(str(os.getpid()), encoding="utf-8")
    log = root / "logs" / "browsers.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    venv = BUNDLE / "C3_Login_agent" / ".venv"          # 묶인 앱은 무시되고 같은 실행 파일이 쓰인다
    try:
        with open(log, "a", encoding="utf-8") as f:
            subprocess.run(module_cmd(venv, "playwright", "install", "chromium"), stdout=f, stderr=subprocess.STDOUT,
                           cwd=str(root), timeout=30 * 60,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except Exception as e:                               # noqa: BLE001
        with open(log, "a", encoding="utf-8") as f:
            print(f"Chromium 내려받기 실패: {e}", file=f)
    finally:
        mark.unlink(missing_ok=True)


def serve(a: argparse.Namespace) -> int:
    root = Path(a.data_root) if a.data_root else appdata.default_root()
    root.mkdir(parents=True, exist_ok=True)
    # 묶인 앱은 Tauri 가 stderr 를 버리므로 기본으로 앱 데이터 폴더/logs/backend.log 에 쓴다
    log = Path(a.log) if a.log else (root / "logs" / "backend.log" if FROZEN else None)
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        sys.stderr = open(log, "a", encoding="utf-8", buffering=1)        # noqa: SIM115 — 프로세스 끝까지 쓴다
    # 저장소에서 개발용으로 띄울 때는 C3 .venv 에 이미 받아 둔 Chromium 을 그대로 쓴다
    repo_browsers = BUNDLE / "C3_Login_agent" / ".venv" / "pw-browsers"
    if not FROZEN and repo_browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(repo_browsers))
    appdata.apply(root)
    # C1 은 시작할 때 옛 자리(univ_us_local/data/univus.db)의 일정 DB 를 옮겨 온다 — 데스크톱 앱에서는 하지 않는다
    # (저장소에서 개발용으로 띄울 때 저장소 데이터를 앱 데이터 폴더로 끌고 가지 않게). 옮기려면 python -m osenv migrate-data.
    os.environ.setdefault("C1_LEGACY_DB", str(root / "C1_Calendar_agent" / "data" / "univus.db"))

    port = a.port or _free_port()
    code = secrets.token_urlsafe(18)
    os.environ.update(UNIVUS_PORT=str(port), UNIVUS_SESSION_TOKEN=secrets.token_urlsafe(32), UNIVUS_LAUNCH_CODE=code)
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))

    import uvicorn
    from app import main as app_main                     # config 가 세션 값을 읽고 환경변수에서 지운다

    server = uvicorn.Server(uvicorn.Config(app_main.app, host="127.0.0.1", port=port, log_level="warning",
                                           access_log=False))
    threading.Thread(target=_announce, args=(server, port, code, root), daemon=True).start()
    if a.exit_with_stdin:
        threading.Thread(target=_exit_with_stdin, args=(server,), daemon=True).start()
    if not (a.no_browser_install or os.environ.get("UNIVUS_NO_BROWSER_INSTALL") == "1"):   # 환경변수: CI·시험 실행용
        threading.Thread(target=_ensure_browsers, args=(root,), daemon=True).start()
    print(f"desktop: 서버 시작 127.0.0.1:{port} · 데이터 {root}", file=sys.stderr, flush=True)
    server.run()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--run-module"]:
        if len(argv) < 2:
            print("사용법: --run-module <모듈> [인자…]", file=sys.stderr)
            return 2
        return run_module(argv[1], argv[2:])
    ap = argparse.ArgumentParser(prog="univus-backend", description="유니버스 데스크톱 앱 로컬 서버")
    ap.add_argument("--data-root", help="앱 데이터 폴더 (기본: OS 별 위치)")
    ap.add_argument("--port", type=int, default=0, help="포트 (기본: 빈 포트)")
    ap.add_argument("--log", help="서버 로그 파일")
    ap.add_argument("--exit-with-stdin", action="store_true", help="표준입력이 닫히면 끝낸다 (Tauri 가 붙인다)")
    ap.add_argument("--no-browser-install", action="store_true", help="Chromium 자동 내려받기를 하지 않는다")
    return serve(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
