"""F2 졸업요건·학점 트래커 — 설정 (경로 · 원천 · 성적 규칙).

요구사항: 요구사항정의서.md F2 절 / 화면: Frontend-Route.md 7절.
프로필(학과·전공·입학년도·이수유형·평점)은 C2_Profile_agent 의 것을 읽는다 (전역 결정 G3, C2 6절 자동 매칭).

설치할 것이 없다
  - 계산·저장·API·교육과정 수집은 **표준 라이브러리만** 쓴다 → 대시보드 백엔드가 그대로 import 한다.
  - 학사정보시스템 기이수성적 수집(SSO·브라우저)만 C3_Login_agent 의 .venv(playwright·bs4)와 로그인 세션을 빌린다.
    로그인 절차는 C2 의 student.hakstd 를 그대로 쓴다(같은 학사정보시스템, 같은 함정 — /Main/Login.aspx).

지키는 선
  - 계산은 규칙 기반 코드로만. LLM 호출이 없다 (F2-R29).
  - 이수 내역·평점은 이 PC 의 data/graduation.db 에만 있다. 밖으로 보내지 않는다 (F2 9절).
  - 이름·학번은 읽지도 저장하지도 않는다 (F2-R03).
  - 교육과정검색 요청 간격 1.5초, 동시성 1 (C2 8절).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # F2_Graduation_agent/
PROJECT_ROOT = ROOT.parent

# C0 OS 공통 계층 (osenv) — venv python 자리·프로세스 확인이 OS 마다 다르다
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import FROZEN, IS_WINDOWS, browsers_dir, chromium_state, module_cmd  # noqa: E402,F401

DATA_DIR = Path(os.environ.get("F2_DATA_DIR") or ROOT / "data")
STATE_DIR = Path(os.environ.get("F2_STATE_DIR") or ROOT / "state")
DB_PATH = DATA_DIR / "graduation.db"

# 룰셋·교육과정 — 저장소에 넣어 두는 것(검수한 기본값) + 사용자가 받은 것(data/)
BUNDLED_RULESETS = ROOT / "rulesets"
BUNDLED_CURRICULUM = ROOT / "curriculum"
LOCAL_CURRICULUM = DATA_DIR / "curriculum"

# ── 교육과정검색 (공개, 로그인 불필요 — C2 2절, 2026-09-28 실측) ──
CURRICULUM_URL = "https://www.jnu.ac.kr/WebApp/web/DBM/ENG/CurriCulumn/CurriCulumnSM.aspx"
REQUEST_INTERVAL = 1.5          # 초. 줄이지 말 것.
RETRY_WAITS = (3, 10, 30)
HTTP_TIMEOUT = 30
MAX_PAGES = 30                  # 한 학과·연도의 교과목 페이지 상한 (10행/페이지)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# ── 학사정보시스템 (SSO) — C3_Login_agent 의 세션·브라우저 + C2 의 로그인 절차를 빌린다 ──
C2_AGENT_DIR = Path(os.environ.get("C2_AGENT_DIR") or PROJECT_ROOT / "C2_Profile_agent")
C3_AGENT_DIR = Path(os.environ.get("C3_AGENT_DIR") or PROJECT_ROOT / "C3_Login_agent")
C3_BROWSERS = browsers_dir()                     # Chromium (앱 데이터 폴더 / 개발 모드 venv) — 가져오기는 osenv.module_cmd 로 띄운다
# C3 의 state 자리 — C3 config 와 같은 규칙(C3_STATE_DIR). 자격증명 표시는 OS 마다 이름이 다르다 (C3 auth.py)
C3_STATE_DIR = Path(os.environ.get("C3_STATE_DIR") or C3_AGENT_DIR / "state")
C3_STATE = C3_STATE_DIR / "storage_state.json"
C3_CRED = C3_STATE_DIR / ("cred.bin" if IS_WINDOWS else "cred.keychain.json")
C2_HAKSTD_STATE = Path(os.environ.get("C2_STATE_DIR") or C2_AGENT_DIR / "state") / "hakstd_state.json"
HAKSTD_BASE = "https://hakstd.jnu.ac.kr"
HAKSTD_DASHBOARD = f"{HAKSTD_BASE}/Home/DashBoard"
HAKSTD_GRADES = f"{HAKSTD_BASE}/web/Sung/Sung010"          # 기이수성적
IMPORT_OUT = STATE_DIR / "import.json"
IMPORT_LOG = STATE_DIR / "import.log"
IMPORT_TIMEOUT = 5 * 60
INTERACTIVE_TIMEOUT = 12 * 60                               # 직접 로그인 창을 띄운 경우

# ── 성적 규칙 (5절 ①) ──
FAIL_GRADES = {"F", "NP", "U", "W", "FA", "N"}              # 취득학점에 넣지 않는 성적 (F2-R20)
DROP_WORDS = ("포기", "취소", "철회", "삭제")                 # 교과목상태에 이 말이 있으면 계산 제외
# 재수강 정리 때 '가장 높은 성적 1건'을 고르는 순서 (5절 ②). P 는 등급 없는 통과라 D- 와 같은 자리.
GRADE_RANK = {"A+": 13, "A0": 12, "A": 12, "A-": 11, "B+": 10, "B0": 9, "B": 9, "B-": 8, "C+": 7, "C0": 6, "C": 6,
              "C-": 5, "D+": 4, "D0": 3, "D": 3, "D-": 2, "P": 2, "S": 2}


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR, LOCAL_CURRICULUM):
        d.mkdir(parents=True, exist_ok=True)
