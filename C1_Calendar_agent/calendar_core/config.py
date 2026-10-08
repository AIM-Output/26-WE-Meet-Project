"""C1 서비스 캘린더 (공통 기반) — 설정 (경로 · 분류 색).

요구사항: 요구사항정의서.md C1 절 / 화면: Frontend-Route.md 3절.

설치할 것이 없다
  - 표준 라이브러리 + fastapi 만 쓴다. 대시보드 백엔드(univ_us_local)가 그대로 import 한다.
    명령줄(run.cmd)은 fastapi 없이도 도는 부분(store·service)만 쓴다.

다른 기능이 캘린더에 얹는 일정 (C1 3절)
  - 이 폴더는 **내 일정·할 일**(kind=user)만 저장한다. 학사(F1)·마감(F6)·수업(F3)·학습 블록(F5)은
    각 기능 폴더가 갖고 있고, 백엔드가 build_router(sources=[...]) 로 넘겨주면 /api/events 에서 합쳐진다.

지키는 선
  - 내 일정·할 일은 이 PC 의 data/univus.db 에만 있다. 밖으로 나가지 않는다 (C1 7절 · 전역 결정 G1).
  - 날짜는 tz 없는 로컬 문자열. 종일 일정의 end 는 exclusive (C1-R14).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # C1_Calendar_agent/
PROJECT_ROOT = ROOT.parent                               # 26 WE-Meet Project/

# UNIVUS_* 는 이 코드가 univ_us_local/backend 에 있던 시절의 이름 — 쓰던 사람을 위해 계속 받는다.
DATA_DIR = Path(os.environ.get("C1_DATA_DIR") or os.environ.get("UNIVUS_DATA_DIR") or ROOT / "data")
DB_PATH = Path(os.environ.get("C1_DB") or os.environ.get("UNIVUS_DB") or DATA_DIR / "univus.db")

# 2026-09-30 이전 위치. 남아 있으면 store.init() 이 **한 번만** 위 자리로 옮긴다.
LEGACY_DB = Path(os.environ.get("C1_LEGACY_DB") or PROJECT_ROOT / "univ_us_local" / "data" / "univus.db")

# 내 일정 분류 (C1 3절 '내 일정' — 색은 분류별. 소스 구분은 색만으로 하지 않는다, C1-R12)
CATEGORIES = {
    "personal": {"label": "개인", "color": "#33644d"},
    "study": {"label": "학업", "color": "#3d6b8c"},
    "team": {"label": "팀플", "color": "#9a6a14"},
    "etc": {"label": "기타", "color": "#6b6560"},
}
