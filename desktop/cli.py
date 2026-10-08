"""개발용 명령줄 — 기능 모듈(`python -m <패키지> …`)을 개발 모드 데이터(desktop/.dev-data)로 돌린다.

    desktop\\sidecar\\.venv\\Scripts\\python desktop\\cli.py eclass sync --dry-run      (맥: desktop/sidecar/.venv/bin/python desktop/cli.py …)
    … desktop/cli.py bachelor list
    … desktop/cli.py --app eclass status       설치된 앱의 데이터 폴더로 — 앱이 떠 있으면 수집·쓰기 명령은 피할 것

패키지 이름으로 기능 폴더를 찾아 그 폴더에서 돌린다 (-m 은 현재 폴더를 import 경로에 둔다):
    calendar_core(C1) · student(C2) · login(C3) · bachelor(F1) · graduation(F2) · attendance(F3) · textbook(F4)
    exams(F5) · eclass(F6) · tasks(F7) · placement(F8)
데이터 폴더는 desktop.py 와 같은 규칙(C0 osenv.appdata.apply)으로 환경변수에 넣는다. 개발 데이터는 예약 실행을 끈다(F1_TASKS·F6_TASKS=off).
개발 데이터 채우기: C0_Platform_agent 에서 `python -m osenv copy-data --to ../desktop/.dev-data` (설치된 앱 데이터를 복사).
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DESKTOP = Path(__file__).resolve().parent
REPO = DESKTOP.parent
sys.path.append(str(REPO / "C0_Platform_agent"))
from osenv import appdata  # noqa: E402

DEV_DATA = DESKTOP / ".dev-data"


def feature_dir(package: str) -> Path | None:
    top = package.split(".")[0]
    for folder in appdata.LAYOUT:
        if (REPO / folder / top / "__init__.py").exists():
            return REPO / folder
    return None


def main(argv: list[str]) -> int:
    app = argv[:1] == ["--app"]
    if app:
        argv = argv[1:]
    if not argv or argv[0].startswith("-"):
        print(__doc__, file=sys.stderr)
        return 2
    module, args = argv[0], argv[1:]
    cwd = feature_dir(module)
    if cwd is None:
        print(f"기능 패키지를 찾지 못했습니다: {module}", file=sys.stderr)
        return 2
    env = dict(os.environ, PYTHONUTF8="1")
    if app:
        root = appdata.default_root()
    else:
        root = DEV_DATA
        env.setdefault("F1_TASKS", "off")
        env.setdefault("F6_TASKS", "off")
        env.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(Path(sys.prefix) / "pw-browsers"))   # desktop.py 개발 모드와 같은 자리
    appdata.apply(root, env)
    print(f"[cli] {module} · 데이터 {root}", file=sys.stderr, flush=True)
    return subprocess.run([sys.executable, "-X", "utf8", "-m", module, *args], cwd=str(cwd), env=env).returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
