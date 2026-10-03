"""내 프로필 읽기 (C2). 프로필은 ../C2_Profile_agent 가 관리한다 (data/profile.db, 대시보드 /api/profile).

대시보드 화면은 백엔드가 프로필을 직접 넘겨주므로 이 파일을 쓰지 않는다. 수집(③·④ 내 소속 원천 — 소속으로 홈페이지를 찾는다)과
CLI(`python -m bachelor list`)가 쓴다.
C2 쪽 store·service 는 표준 라이브러리만 써서 이 .venv 에서도 import 된다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

from . import config as C

C2_DIR = Path(os.environ.get("C2_AGENT_DIR") or C.ROOT.parent / "C2_Profile_agent")


def load_local_profile() -> Optional[dict]:
    if not (C2_DIR / "student" / "service.py").exists():
        return None
    if str(C2_DIR) not in sys.path:
        sys.path.insert(0, str(C2_DIR))
    try:
        from student import service, store        # type: ignore[import-not-found]
        with store.connect() as con:
            return service.matching_view(con)
    except Exception:                               # noqa: BLE001
        return None
