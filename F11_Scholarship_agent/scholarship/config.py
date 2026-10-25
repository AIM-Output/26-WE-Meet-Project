"""F11 장학 — 설정 (경로 · 수집 정책 · 판정 문턱 · 알림 · LLM 슬롯).

요구사항: 요구사항정의서.md F11 절 / 화면: Frontend-Route.md 16절(/scholarships).
원천 목록(학교 전체·부서·사업단·내 학과)은 directory/sources.json — 2026-10-09 실측, 근거는 README.

지키는 선
  - 요청 간격 REQUEST_INTERVAL 은 줄이지 않는다 (학교 서버 부담 금지, 계획서 4.1). 동시성은 항상 1.
  - 공개 게시판·공개 안내 페이지만 읽는다 → 로그인 정보가 필요 없다. 어떤 신청 버튼도 누르지 않는다.
  - data/ (수집 공지·초안·진행 상태) 와 state/ (잠금·로그) 는 .gitignore — 공유 금지.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # F11_Scholarship_agent/
PROJECT_ROOT = ROOT.parent

# C0 OS 공통 계층 (osenv) — 자식 프로세스 명령·프로세스 확인이 OS 마다 다르다
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import module_cmd, pid_alive  # noqa: E402,F401 — runner 가 쓴다


def _load_env(path: Path) -> None:
    """.env 의 KEY=VALUE 를 환경변수로 (이미 있는 값은 건드리지 않는다). python-dotenv 없이."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env(ROOT / ".env")

DATA_DIR = Path(os.environ.get("F11_DATA_DIR") or ROOT / "data")
STATE_DIR = Path(os.environ.get("F11_STATE_DIR") or ROOT / "state")
DB_PATH = DATA_DIR / "scholarship.db"
LOCK_FILE = STATE_DIR / "sync.lock"              # 수집이 도는 동안 {pid, started_at}
LAST_RUN_FILE = STATE_DIR / "sync.last.json"     # 마지막 수집 결과
LOG_FILE = STATE_DIR / "sync.log"
# F12 대외활동 수집 잠금 — 같은 게시판을 읽으므로 F12 가 돌고 있으면 끝날 때까지 기다린다(동시성 1, 최대 PEER_WAIT_MIN 분).
# F12 는 자기 잠금을 잡기 전에 F11 을 기다리고, F11 은 잠금을 잡은 뒤 F12 를 기다린다 — 서로 막히지 않는다.
PEER_LOCK_FILE = Path(os.environ.get("F12_STATE_DIR") or PROJECT_ROOT / "F12_Activity_agent" / "state") / "sync.lock"
PEER_WAIT_MIN = 45

# 원천 목록 — 저장소 스냅숏 (directory/sources.json). 학과·단과대학 홈페이지 목록은 F1 이 모아 둔 것을 같이 쓴다.
SOURCES_FILE = ROOT / "directory" / "sources.json"
F1_AGENT_DIR = Path(os.environ.get("F1_AGENT_DIR") or PROJECT_ROOT / "F1_Bachelor_agent")
F1_DATA_DIR = Path(os.environ.get("F1_DATA_DIR") or F1_AGENT_DIR / "data")
HOMEPAGES_FILES = (F1_DATA_DIR / "directory" / "homepages.json", F1_AGENT_DIR / "directory" / "homepages.json")

# ── 수집 정책 ──────────────────────────────────────────────
REQUEST_INTERVAL = 1.5          # 초. 줄이지 말 것.
RETRY_WAITS = (3, 10, 30)       # 접속 실패 시 재시도 간격(초)
HTTP_TIMEOUT = 30
LIST_PAGES = 2                  # 게시판마다 목록 페이지 수 (주기 수집이면 1~2면 충분)
FIRST_LIST_PAGES = 3            # 처음 수집하는 게시판은 조금 더 깊이 — 아직 신청 중인 공지를 놓치지 않게
MAX_DETAIL_PER_SOURCE = 25      # 한 번에 상세를 받을 새 글 최대 수 (게시판마다)
FIRST_MAX_DETAIL = 45           # 처음 수집하는 게시판 — 장학안내 3쪽(60건) 중 아직 신청 중일 만한 최근 글까지
RECHECK_DAYS = 14               # 게시 후 이 기간 안의 글은 다시 받아 수정 여부(내용 해시)를 본다
RECHECK_MAX = 6                 # 한 번에 다시 볼 글 최대 수
MAX_ATTACH_MB = 10              # 읽는 첨부(PDF) 최대 크기 — 파일은 저장하지 않고 글자만 남긴다
MAX_ATTACH_PER_NOTICE = 3
DISCOVERY_MAX_AGE_DAYS = 7      # 찾아 둔 학과 게시판을 이 기간이 지나면 다시 확인한다 (홈페이지 개편 대비)
CATALOG_MAX_AGE_DAYS = 7        # 상시 장학 안내(교내·교외 장학금 페이지)는 주 1회 (F11-D12)
SYNC_SLOTS = ("06:00", "18:00")  # 앱이 떠 있으면 이 시각마다 수집 (F10 6절 · F13-R06). 놓쳤으면 켜질 때 한 번
SYNC_TIMEOUT_MIN = 30


def autosync_enabled() -> bool:
    """앱이 떠 있는 동안의 자동 수집 — 테스트·개발 모드(desktop.py --dev)는 F11_AUTOSYNC=off (F1·F6 예약 실행과 같은 규칙)."""
    return os.environ.get("F11_AUTOSYNC", "").lower() not in ("off", "0", "false", "no")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# 장학 관련 글만 남기는 제목 어휘 (장학 전용 게시판·말머리가 아닌 곳에 적용).
# '지원금' 처럼 넓은 말은 넣지 않는다 — 사업단 게시판에서는 창업·활동 지원금이 대부분이다.
SCHOLARSHIP_WORDS = ("장학", "학자금", "등록금", "인재육성비", "우수인재육성", "학업장려", "생활비 지원", "생활비지원",
                     "근로장학", "튜터링", "마일리지")
# 장학 어휘가 있어도 신청과 상관없는 글 (총동창회 '장학재단 결산 공시서류' 등) — 장학 전용이 아닌 게시판에서만 뺀다
NOT_APPLY_WORDS = ("결산", "공시", "기부금", "약정 현황", "기부자")
# 이 말이 있으면 선발 결과·홍보 글 — 모으되 신청 대상으로 보지 않는다 (F11-R07)
RESULT_WORDS = ("선발 결과", "선발결과", "합격자", "최종 선발자", "선발자 공고", "선발 대상자 공고", "명단", "수여식",
                "결과 안내", "결과 및", "발표")
# 학부생 대상이 아닌 글 — '대상 아님' (F11 5절)
GRAD_ONLY_WORDS = ("대학원생", "대학원 ", "석사", "박사", "박사후", "교직원", "전임교원", "연구교수")

# 추출 규칙 판(版). 규칙을 고치면 올린다 → 저장된 공지를 다음 읽기 때 새 규칙으로 다시 뽑는다.
EXTRACT_VERSION = 3

# ── 판정 (F11 5절) ─────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.6      # 추출 신뢰도가 이보다 낮으면 자동 판정하지 않고 '확인 필요' (F11-R13)
RECENT_EXPIRY_DAYS = 21         # 저신뢰 추출에서 이 일수 안에 '지난' 마감은 마감 대신 확인 필요
NO_PERIOD_STALE_DAYS = 60       # 신청 기간을 못 읽은 공지가 이보다 오래됐으면 '지난 공지'로 접는다

# ── 알림 (F11-R70~R72) ─────────────────────────────────────
ALERT_TIME = "09:00"            # 마감 D-3 · D-1 알림을 울리는 시각
DEADLINE_DAYS = (3, 1)
BUNDLE_OVER = 3                 # 한 번 수집에서 새 해당·확인 필요가 이보다 많으면 한 줄로 묶는다

# ── LLM (선택) — F1·notice_agent 와 같은 슬롯 이름. 비어 있으면 초안 문단은 골격+안내문만 만든다 (F11-R48) ──
LLM_BASE_URL = os.environ.get("LLM_MAIN_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_MAIN_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MAIN_MODEL", "")
LLM_TIMEOUT = 90


def llm_configured() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
