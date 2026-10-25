"""F12 대외활동 — 설정 (경로 · F11 크롤러 빌려 쓰기 · 수집 정책 · 관심사 등급 · 알림 · LLM 슬롯).

요구사항: 요구사항정의서.md F12·F13 절(구현 메모 2026-10-10) / 화면: Frontend-Route.md 17절(/opportunities).

F11 과의 관계 (2026-10-10 사용자 결정)
  - 수집 원천은 **F11 과 같다** — F11_Scholarship_agent/directory/sources.json (프로필 소속으로 켜지는 사업단·학과 게시판까지).
    이 기능의 directory/sources.json 은 그 위에 대외활동에 맞게 **덮어쓰는 것만** 둔다 (장학 전용 원천 빼기 · 이름·이유 · 거르는 말).
  - 게시판 수집기(aspx·k2web·coss·coursemos)·첨부 읽기·날짜 규칙은 F11 의 것을 **그대로 import** 한다 (scholarship 패키지).
  - F11 은 장학만, F12 는 **장학이 아닌 나머지 전부**(교내 프로그램·공모전·대외활동·취업·해외·창업·봉사·기자재 대여 …).
    장학 어휘가 걸린 글은 F11 몫이라 여기서는 저장하지 않는다 (요구사항정의서 F12 8절 '장학 탭 우선').
  - F11 은 조건으로 '내 해당'을, F12 는 관심사로 '내 관심사'를 가른다. 신청서 초안은 둘 다 만든다.

지키는 선
  - 요청 간격 1.5초·동시성 1 (F11 Http 그대로). F11 수집이 돌고 있으면 끝날 때까지 기다린다 — 두 기능이 같은 학교 서버를 동시에 읽지 않게.
  - 공개 게시판만 읽는다. 어떤 신청 버튼도 누르지 않는다. data/·state/ 는 .gitignore — 공유 금지.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # F12_Activity_agent/
PROJECT_ROOT = ROOT.parent

# C0 OS 공통 계층 (osenv) — 자식 프로세스 명령·프로세스 확인이 OS 마다 다르다
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import module_cmd, pid_alive  # noqa: E402,F401 — runner 가 쓴다

# F11 장학 — 원천 목록·게시판 수집기·첨부 읽기·날짜 규칙을 빌려 쓴다 (scholarship 패키지, 표준 라이브러리 부분만 여기서 import)
F11_AGENT_DIR = Path(os.environ.get("F11_AGENT_DIR") or PROJECT_ROOT / "F11_Scholarship_agent")
if str(F11_AGENT_DIR) not in sys.path:
    sys.path.append(str(F11_AGENT_DIR))


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

DATA_DIR = Path(os.environ.get("F12_DATA_DIR") or ROOT / "data")
STATE_DIR = Path(os.environ.get("F12_STATE_DIR") or ROOT / "state")
DB_PATH = DATA_DIR / "activity.db"
LOCK_FILE = STATE_DIR / "sync.lock"              # 수집이 도는 동안 {pid, started_at}
LAST_RUN_FILE = STATE_DIR / "sync.last.json"     # 마지막 수집 결과
LOG_FILE = STATE_DIR / "sync.log"
# F11 수집 잠금 — 이게 살아 있으면 끝날 때까지 기다린다 (두 기능이 같은 게시판을 동시에 읽지 않게, 동시성 1)
F11_LOCK_FILE = Path(os.environ.get("F11_STATE_DIR") or F11_AGENT_DIR / "state") / "sync.lock"

OVERLAY_FILE = ROOT / "directory" / "sources.json"      # F11 원천 위에 덮어쓰는 것
INTERESTS_FILE = ROOT / "directory" / "interests.json"  # 관심사 태그 ↔ 어휘 · 분류 규칙

# ── 수집 정책 (요청 간격·재시도·첨부 크기는 F11 config 그대로) ─────────────
LIST_PAGES = 2                  # 게시판마다 목록 페이지 수 — 원천이 pages 로 더 깊게 정할 수 있다(학교 전체 공지는 하루 10건 넘게 올라온다)
FIRST_LIST_PAGES = 3            # 처음 수집하는 게시판
MAX_DETAIL_PER_SOURCE = 25      # 한 번에 상세를 받을 새 글 최대 수 (게시판마다)
FIRST_MAX_DETAIL = 35
FIRST_MAX_AGE_DAYS = 45         # 처음 수집할 때 이보다 오래된 글은 상세를 받지 않는다(대개 끝난 모집 — 요청을 아낀다)
RECHECK_DAYS = 10               # 게시 후 이 기간 안의 글은 몇 건씩 다시 받아 수정 여부(내용 해시)를 본다
RECHECK_MAX = 4
ATTACH_BODY_SHORT = 300         # 본문이 이보다 짧을 때만 첨부(PDF·HWPX·DOCX) 글자를 읽는다 — 모집 요강이 첨부에만 있는 경우
MAX_ATTACH_PER_NOTICE = 2
DISCOVERY_MAX_AGE_DAYS = 7      # 찾아 둔 학과 공지 게시판을 이 기간이 지나면 다시 확인한다
SYNC_SLOTS = ("06:00", "18:00")  # 앱이 떠 있으면 이 시각마다 (F13-R06 — 장학과 같은 시각, 장학 수집이 끝난 뒤)
SYNC_TIMEOUT_MIN = 45
PEER_WAIT_MIN = 30              # F11 수집이 이보다 오래 돌면 기다리지 않고 시작한다(멈춘 잠금 대비)


def autosync_enabled() -> bool:
    """앱이 떠 있는 동안의 자동 수집 — 테스트·개발 모드(desktop.py --dev)는 F12_AUTOSYNC=off (F11 과 같은 규칙)."""
    return os.environ.get("F12_AUTOSYNC", "").lower() not in ("off", "0", "false", "no")


# 추출 규칙 판(版). 규칙을 고치면 올린다 → 저장된 공지를 다음 읽기 때 새 규칙으로 다시 뽑는다.
EXTRACT_VERSION = 5

# ── 관심사 등급 (요구사항정의서 F12 5절) ───────────────────────
STALE_DAYS = 45                 # 신청 기간을 못 읽은 공지가 이보다 오래됐으면 '지난 공지'로 접는다
MAX_KEYWORDS = 20               # 자유 키워드·제외 키워드 각각 (F12-R11)
WIDE_KEYWORD_SHARE = 0.3        # 열린 공지의 30% 넘게 걸리는 키워드는 '너무 넓음' 안내 (F12 8절)
WIDE_KEYWORD_MIN = 15

# ── 알림 (F12-R30~R33) ─────────────────────────────────────
DAILY_ALERT_MAX = 5             # 즉시 알림 하루 상한 — 넘으면 '관심 기회 N건이 더 있습니다' 한 줄로 묶는다 (F12-R31, Q4)
ALERT_TIME = "09:00"            # 마감 알림을 울리는 시각
SAVED_DEADLINE_DAYS = (3,)      # 담아 둔 것 — D-3 (F12-R32)
DRAFT_DEADLINE_DAYS = (3, 1)    # 초안·제출 예정 — D-3·D-1 (F11 과 같게)

# ── LLM (선택) — F1·F11 과 같은 슬롯 이름. 비어 있으면 관련도는 키워드·소속으로만, 초안 문단은 골격+빈칸 ──
LLM_BASE_URL = os.environ.get("LLM_MAIN_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_MAIN_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MAIN_MODEL", "")
LLM_TIMEOUT = 90
LLM_DAILY_MAX = 100             # 관련도 판단 하루 호출 상한 — 넘으면 키워드 판정만 (F12 9절 비용, Q3)
LLM_BATCH = 15                  # 한 번에 판단할 공지 수 (1분마다 /api/status 가 이어서 부른다)


def llm_configured() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
