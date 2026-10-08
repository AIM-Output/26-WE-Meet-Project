"""사이드카 빌드 — univ_us_local/backend/desktop.py 를 PyInstaller onedir 로 묶는다.

    py -3.12 desktop/sidecar/build.py          (맥: python3.12 desktop/sidecar/build.py)

결과: desktop/sidecar/dist/univus-backend/univus-backend(.exe) + _internal/  — Tauri 가 resources 로 넣는다 (tauri.conf.json).
빌드용 .venv 는 desktop/sidecar/.venv (C0 osenv.venv.ensure — requirements.txt 가 바뀌었을 때만 다시 설치).
프론트(univ_us_local/frontend/out)는 저장소에 커밋된 빌드 결과를 그대로 쓴다 — 화면을 고쳤으면 npm run build 먼저.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.append(str(REPO / "C0_Platform_agent"))
from osenv.venv import ensure  # noqa: E402


def main() -> int:
    if sys.version_info[:2] != (3, 12):
        print(f"주의: Python {sys.version.split()[0]} — 3.12 로 빌드하는 것을 권장합니다 (검증된 버전)", file=sys.stderr)
    py = ensure(HERE / ".venv", HERE / "requirements.txt", log=sys.stderr)
    cmd = [str(py), "-m", "PyInstaller", "--noconfirm", "--clean",
           "--distpath", str(HERE / "dist"), "--workpath", str(HERE / "build"), str(HERE / "univus-backend.spec")]
    print("$", " ".join(cmd), file=sys.stderr, flush=True)
    return subprocess.run(cmd, cwd=str(HERE)).returncode


if __name__ == "__main__":
    sys.exit(main())
