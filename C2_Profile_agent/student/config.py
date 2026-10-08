"""C2 사용자 프로필·학과 마스터 — 설정 (경로 · 원천 · 요청 간격).

요구사항: 요구사항정의서.md C2 절 / 화면: Frontend-Route.md 5절.
프로필 하나를 F1(학사일정 대상 판정) · F2(졸업요건 룰셋) · F11(장학 매칭)이 같이 쓴다 (전역 결정 G3).

설치할 것이 없다
  - 프로필 저장·API·학과 마스터 수집은 **표준 라이브러리만** 쓴다 → 대시보드 백엔드가 그대로 import 한다.
  - 학사정보시스템 가져오기(SSO·브라우저)만 C3_Login_agent 의 .venv(playwright·bs4)와 로그인 세션을 빌려 쓴다.

지키는 선
  - 이름·학번은 받지도 읽지도 저장하지도 않는다 (C2-D5).
  - 프로필은 이 PC 의 data/profile.db 에만 있다. 밖으로 보내지 않는다 (C2-R11).
  - 교육과정검색 요청 간격 1.5초, 동시성 1 (C2 8절).
"""
from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # C2_Profile_agent/
PROJECT_ROOT = ROOT.parent

# C0 OS 공통 계층 (osenv) — venv python 자리·프로세스 확인이 OS 마다 다르다
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import FROZEN, IS_WINDOWS, browsers_dir, chromium_state, module_cmd  # noqa: E402,F401

DATA_DIR = Path(os.environ.get("C2_DATA_DIR") or ROOT / "data")
STATE_DIR = Path(os.environ.get("C2_STATE_DIR") or ROOT / "state")
DB_PATH = DATA_DIR / "profile.db"

# 학과 마스터 — 저장소에 넣어 두는 스냅숏(처음 실행에도 네트워크 없이 뜬다) + 사용자가 '갱신'하면 data/ 쪽이 이긴다
BUNDLED_MASTER = ROOT / "master" / "departments.json"
LOCAL_MASTER = DATA_DIR / "master" / "departments.json"

# ── 교육과정검색 (공개, 로그인 불필요 — C2 2절, 2026-09-28 실측) ──
CURRICULUM_URL = "https://www.jnu.ac.kr/WebApp/web/DBM/ENG/CurriCulumn/CurriCulumnSM.aspx"
REQUEST_INTERVAL = 1.5          # 초. 줄이지 말 것.
RETRY_WAITS = (3, 10, 30)
HTTP_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
# 학부 과정만 받는다(C2-Q4 1차 답). 단과대 코드 3000xxxx = 학부, 2000xxxx = 대학원. 타대학 협약은 뺀다.
UNDERGRAD_PREFIX = "3"
SKIP_COLLEGES = {"30890001"}    # 협약대학(타대)

# ── 학사정보시스템 (SSO) — C3_Login_agent 의 세션·재인증·브라우저를 빌린다 ──
C3_AGENT_DIR = Path(os.environ.get("C3_AGENT_DIR") or PROJECT_ROOT / "C3_Login_agent")
C3_BROWSERS = browsers_dir()                     # Chromium (앱 데이터 폴더 / 개발 모드 venv) — 가져오기는 osenv.module_cmd 로 띄운다
# C3 의 state 자리 — C3 config 와 같은 규칙(C3_STATE_DIR). 자격증명 표시는 OS 마다 이름이 다르다 (C3 auth.py)
C3_STATE_DIR = Path(os.environ.get("C3_STATE_DIR") or C3_AGENT_DIR / "state")
C3_STATE = C3_STATE_DIR / "storage_state.json"
C3_CRED = C3_STATE_DIR / ("cred.bin" if IS_WINDOWS else "cred.keychain.json")
HAKSTD_BASE = "https://hakstd.jnu.ac.kr"
HAKSTD_DASHBOARD = f"{HAKSTD_BASE}/Home/DashBoard"
HAKSTD_GRADES = f"{HAKSTD_BASE}/web/Sung/Sung010"          # 기이수성적
SSO_HOSTS = ("sso.jnu.ac.kr", "idpm.jnu.ac.kr")
HAKSTD_STATE = STATE_DIR / "hakstd_state.json"              # 갱신된 쿠키는 여기에 (C3_Login_agent 파일은 덮어쓰지 않는다)
IMPORT_OUT = STATE_DIR / "import.json"
IMPORT_LOG = STATE_DIR / "import.log"
IMPORT_TIMEOUT = 8 * 60          # 세션 두 개 시도 + 쿠키 복구 + 무인 로그인이 다 돌면 5분을 넘길 수 있다
INTERACTIVE_TIMEOUT = 12 * 60                               # 직접 로그인 창을 띄운 경우


def current_year() -> int:
    """교육과정 학년도 — 3월에 바뀐다(1·2월은 전 학년도)."""
    t = date.today()
    return t.year if t.month >= 3 else t.year - 1


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR, LOCAL_MASTER.parent):
        d.mkdir(parents=True, exist_ok=True)
