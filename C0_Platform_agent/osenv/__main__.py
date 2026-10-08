"""osenv 명령줄 (C0_Platform_agent 폴더에서).

    python -m osenv venv <venv 폴더> [-r requirements.txt]           없으면 만들고 맞춘다 → 마지막 줄에 python 경로
    python -m osenv copy-data --to <폴더> [--from <앱 데이터 폴더>]     앱 데이터(data/·state/)를 다른 폴더로 복사 (덮어쓰지 않음)
                                                                     — 개발 모드 데이터 채우기: --to ../desktop/.dev-data
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .venv import VenvError, ensure


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m osenv", description="C0 OS 공통 계층")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("venv", help="가상환경 만들기·패키지 맞추기")
    p.add_argument("dir")
    p.add_argument("-r", "--requirements")
    p = sub.add_parser("copy-data", help="앱 데이터 폴더의 data/·state/ → 다른 폴더 (덮어쓰지 않음)")
    p.add_argument("--to", required=True, help="복사할 곳 (예: ../desktop/.dev-data)")
    p.add_argument("--from", dest="src", help="원본 (기본: 설치된 앱의 데이터 폴더)")
    a = ap.parse_args(argv)

    if a.cmd == "copy-data":
        from . import appdata
        src = Path(a.src) if a.src else appdata.default_root()
        if not src.is_dir():
            print(f"원본 폴더가 없습니다: {src}", file=sys.stderr)
            return 1
        done = appdata.migrate(src, Path(a.to))
        print(f"완료: {len(done)}개 폴더 {src} → {a.to}")
        return 0

    try:
        py = ensure(a.dir, a.requirements, log=sys.stderr)
        print(py)
    except VenvError as e:
        print(f"\n  {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
