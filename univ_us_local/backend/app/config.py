"""univ_us_local 백엔드 설정 — 개인 로컬 서버(127.0.0.1)용.

원칙
  - 127.0.0.1 에만 바인딩한다. LAN 에 열려면 인증·HTTPS 를 먼저 붙인다.
  - e클래스 자료는 eclass_agent 가 내려받은 JSON 을 읽기만 한다 (수집 코드는 그쪽에 있다).
  - 사용자 일정은 이 폴더의 SQLite 에 저장한다 (data/univus.db).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent          # univ_us_local/
PROJECT_ROOT = ROOT.parent                                    # 26 WE-Meet Project/

ECLASS_AGENT_DIR = Path(os.environ.get("ECLASS_AGENT_DIR", PROJECT_ROOT / "eclass_agent"))
ECLASS_DATA_DIR = ECLASS_AGENT_DIR / "data"
ECLASS_STATE_DIR = ECLASS_AGENT_DIR / "state"
ECLASS_SYNC_CMD = ECLASS_AGENT_DIR / "run-sync.cmd"           # 로그를 state/sync.log 에 남기는 런처
ECLASS_LOCK_FILE = ECLASS_STATE_DIR / "sync.lock"           # sync.py 가 도는 동안 잡는 잠금 {pid, started_at}
ECLASS_LAST_RUN_FILE = ECLASS_STATE_DIR / "sync.last.json"  # sync.py 가 끝날 때 남기는 결과 {…, finished_at, exit_code}

DATA_DIR = Path(os.environ.get("UNIVUS_DATA_DIR", ROOT / "data"))
DB_PATH = Path(os.environ.get("UNIVUS_DB", DATA_DIR / "univus.db"))

FRONTEND_OUT = ROOT / "frontend" / "out"                     # `npm run build` 결과 (정적 export)

HOST = os.environ.get("UNIVUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("UNIVUS_PORT", "8000"))

# 브라우저에서 오는 변경 요청(POST/PATCH/DELETE)은 이 Origin 에서만 받는다 (DNS 리바인딩·CSRF 대비).
ALLOWED_ORIGINS = {
    f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}",
    "http://localhost:3000", "http://127.0.0.1:3000",          # next dev
}
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# 과목 색 — courses.json 순서대로 배정 (7과목 + 여유)
COURSE_PALETTE = [
    "#4f46e5",  # indigo
    "#0891b2",  # cyan
    "#d97706",  # amber
    "#059669",  # emerald
    "#db2777",  # pink
    "#7c3aed",  # violet
    "#ea580c",  # orange
    "#2563eb",  # blue
    "#65a30d",  # lime
    "#9333ea",  # purple
]

# 사용자 일정 분류
CATEGORIES = {
    "personal": {"label": "개인", "color": "#4f46e5"},
    "study": {"label": "학업", "color": "#059669"},
    "team": {"label": "팀플", "color": "#d97706"},
    "etc": {"label": "기타", "color": "#64748b"},
}
