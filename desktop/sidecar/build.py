"""사이드카 빌드 — 화면(univ_us_local/frontend → out/)을 빌드하고 univ_us_local/backend/desktop.py 를 PyInstaller onedir 로 묶는다.

    py -3.12 desktop/sidecar/build.py          (맥: python3.12 desktop/sidecar/build.py)
    py -3.12 desktop/sidecar/build.py --skip-frontend    frontend/out 을 이미 만들었으면 (npm run build 생략)

결과: desktop/sidecar/dist/univus-backend/univus-backend(.exe) + _internal/  — Tauri 가 resources 로 넣는다 (tauri.conf.json).
빌드용 .venv 는 desktop/sidecar/.venv (C0 osenv.venv.ensure — requirements.txt 가 바뀌었을 때만 다시 설치). 개발 모드도 이 venv 를 쓴다.
frontend/out 은 커밋하지 않는다 — 여기서 매번 만든다 (node_modules 가 없으면 npm ci 먼저).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
FRONTEND = REPO / "univ_us_local" / "frontend"
sys.path.append(str(REPO / "C0_Platform_agent"))
from osenv.venv import ensure  # noqa: E402


def _run(cmd: list[str], cwd: Path) -> int:
    print("$", " ".join(cmd), file=sys.stderr, flush=True)
    return subprocess.run(cmd, cwd=str(cwd)).returncode


def build_frontend() -> int:
    npm = shutil.which("npm")
    if not npm:
        print("npm 을 찾지 못했습니다 — Node 20 이상을 설치하세요 (화면 빌드에 필요)", file=sys.stderr)
        return 1
    if not (FRONTEND / "node_modules").is_dir() and (code := _run([npm, "ci"], FRONTEND)) != 0:
        return code
    return _run([npm, "run", "build"], FRONTEND)


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        print(f"주의: Python {sys.version.split()[0]} — 3.12 로 빌드하는 것을 권장합니다 (검증된 버전)", file=sys.stderr)
    if "--skip-frontend" not in sys.argv[1:] and (code := build_frontend()) != 0:
        return code
    py = ensure(HERE / ".venv", HERE / "requirements.txt", log=sys.stderr)
    return _run([str(py), "-m", "PyInstaller", "--noconfirm", "--clean",
                 "--distpath", str(HERE / "dist"), "--workpath", str(HERE / "build"), str(HERE / "univus-backend.spec")], HERE)


if __name__ == "__main__":
    sys.exit(main())
