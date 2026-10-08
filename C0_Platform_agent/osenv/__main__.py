"""osenv 명령줄 — 맥 런처(*.command)가 부른다 (C0_Platform_agent/univus.sh 참고).

    python3 -m osenv venv <venv 폴더> [-r requirements.txt] [--chromium]    없으면 만들고 맞춘다 → 마지막 줄에 python 경로
    python3 -m osenv python <venv 폴더>                                    그 venv 의 python 경로만
    python3 -m osenv migrate-data [--to 앱데이터폴더]                         저장소 data/·state/ 를 데스크톱 앱 데이터 폴더로 복사
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import venv_python
from .venv import VenvError, ensure


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m osenv", description="C0 OS 공통 계층")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("venv", help="가상환경 만들기·패키지 맞추기")
    p.add_argument("dir")
    p.add_argument("-r", "--requirements")
    p.add_argument("--chromium", action="store_true", help="Playwright Chromium 을 <dir>/pw-browsers 에")
    p = sub.add_parser("python", help="venv 의 python 경로")
    p.add_argument("dir")
    p = sub.add_parser("migrate-data", help="저장소 data/·state/ → 데스크톱 앱 데이터 폴더 (덮어쓰지 않음)")
    p.add_argument("--to", help="앱 데이터 폴더 (기본: OS 별 위치)")
    a = ap.parse_args(argv)

    if a.cmd == "migrate-data":
        from . import appdata
        src = Path(__file__).resolve().parent.parent.parent          # 저장소 루트 (C0_Platform_agent 의 부모)
        root = Path(a.to) if a.to else appdata.default_root()
        done = appdata.migrate(src, root)
        print(f"완료: {len(done)}개 폴더 → {root}")
        return 0

    if a.cmd == "python":
        print(venv_python(a.dir))
        return 0
    try:
        py = ensure(a.dir, a.requirements, chromium=a.chromium, log=sys.stderr)
        print(py)
    except VenvError as e:
        print(f"\n  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
