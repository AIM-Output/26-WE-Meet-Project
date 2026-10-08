"""F1 학사 일정 자동 등록·알림 — 설정 (경로 · 수집 원천 · 문턱 · 기본 알림).

요구사항: 요구사항정의서.md F1 절 / 화면: Frontend-Route.md 6절.

지키는 선
  - 요청 간격 REQUEST_INTERVAL 은 줄이지 않는다 (학교 서버 부담 금지, 계획서 4.1). 동시성은 항상 1.
  - 공개 게시판만 수집한다 → 로그인 정보가 필요 없다.
  - data/ (수집 결과 DB) 와 state/ (잠금·로그) 는 .gitignore.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # F1_Bachelor_agent/

# C0 OS 공통 계층 (osenv) — venv python 자리·프로세스 확인이 OS 마다 다르다
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or ROOT.parent / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import FROZEN, module_cmd, pid_alive, venv_python  # noqa: E402,F401 — runner·pipeline 이 쓴다


def _load_env(path: Path) -> None:
    """.env 의 KEY=VALUE 를 환경변수로 (이미 있는 값은 건드리지 않는다). python-dotenv 없이 동작하게 직접 읽는다."""
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

DATA_DIR = Path(os.environ.get("F1_DATA_DIR") or ROOT / "data")
STATE_DIR = Path(os.environ.get("F1_STATE_DIR") or ROOT / "state")
DB_PATH = DATA_DIR / "academic.db"
LOCK_FILE = STATE_DIR / "sync.lock"              # 수집이 도는 동안 {pid, started_at}
LAST_RUN_FILE = STATE_DIR / "sync.last.json"     # 마지막 수집 결과 {…, finished_at, exit_code, sources}
LOG_FILE = STATE_DIR / "sync.log"
RUN_SYNC_CMD = ROOT / "run-sync.cmd"             # 대시보드 버튼이 부르는 런처
RETRY_FILE = STATE_DIR / "retry.json"            # 예약 수집이 네트워크 오류로 재시도를 기다리는 중 {pid, attempt, next_at, slot}

# ── 예약 수집 (e클래스 F6 와 같은 규칙) ─────────────────────────
# 작업 스케줄러가 매일 SCHEDULE_AT + 로그인할 때 + 놓쳤으면 켜지는 대로 `python -m bachelor tick`(run-scheduled.cmd)을 부른다.
# tick 은 가장 최근 SCHEDULE_AT 이후 성공한 수집이 있으면 건너뛴다 → 하루 한 번. 전부 실패(코드 4, 대개 네트워크)면
# 5 → 15 → 45분 뒤 다시(최대 3회). 그 사이 누가 '지금 수집'으로 성공하면 남은 재시도는 그만둔다.
SCHEDULE_AT = os.environ.get("F1_SCHEDULE_AT", "08:00")
RETRY_WAITS_MIN = (5, 15, 45)
CATCHUP_AFTER_MIN = 10           # 예약 시각에서 이만큼 넘게 지나 돌면 '놓친 수집 따라잡기'(catchup)로 기록
TASK_NAME = "UnivUs-F1-Academic-Sync"              # Windows 작업 스케줄러 (register-task.ps1)
LAUNCHD_LABEL = "kr.univus.f1-academic-sync"       # 맥 launchd 사용자 에이전트 (~/Library/LaunchAgents/<이름>.plist)
RUN_SCHEDULED_CMD = ROOT / "run-scheduled.cmd"


def tasks_enabled() -> bool:
    """예약 실행(Windows 작업 스케줄러 · 맥 launchd)을 만질지 — 테스트·격리 서버는 F1_TASKS=off."""
    return sys.platform in ("win32", "darwin") and os.environ.get("F1_TASKS", "").lower() not in ("off", "0", "false", "no")

# 단과대학·학부(과) 홈페이지 목록 — 저장소 스냅숏 + 다시 받은 것(data/ 쪽이 이긴다). homepages.py
BUNDLED_DIRECTORY = ROOT / "directory" / "homepages.json"
LOCAL_DIRECTORY = DATA_DIR / "directory" / "homepages.json"
DISCOVERY_MAX_AGE_DAYS = 7      # 찾아 둔 게시판을 이 기간이 지나면 다시 확인한다 (홈페이지 개편 대비)

# ── 수집 정책 ──────────────────────────────────────────────
REQUEST_INTERVAL = 1.5          # 초. 줄이지 말 것.
RETRY_WAITS = (3, 10, 30)       # 접속 실패 시 재시도 간격(초) — 3회, 간격 증가 (F1 9절)
HTTP_TIMEOUT = 30
LIST_PAGES = 2                  # 공지 게시판 목록 페이지 수
RECHECK_DAYS = 30               # 게시 후 이 기간 안의 글은 다시 받아 수정 여부(내용 해시)를 본다
RECHECK_MAX = 8                 # 한 번에 다시 볼 글 최대 수
MAX_ATTACH_MB = 10              # 본문에 날짜가 없을 때 읽는 PDF 첨부 최대 크기
TABLE_KEEP_MONTHS = 14          # 학사일정 표(2013년부터 전부 들어 있음)에서 오늘 기준 이만큼 지난 것부터 가져온다

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# 추출 규칙 판(版). 규칙을 고치면 올린다 → 다음 수집 때 목록 범위 안의 공지를 다시 읽어 새 규칙으로 뽑는다.
EXTRACT_VERSION = 3

# ── 판정 문턱 (요구사항정의서 F1 7절) ────────────────────────
AUTO_THRESHOLD = 0.80           # 이상이면 자동 등록(status=auto)
WEAK_THRESHOLD = 0.50           # 미만이면 확인 필요 + '근거 약함'

# ── 알림 (F1 5절) ──────────────────────────────────────────
ALERT_TIME = "09:00"            # 기준 시각 (설정에서 바꿀 수 있다 → meta.alert_time)
MISSED_AFTER_MIN = 60           # 예정 시각보다 이만큼 늦게 배달되면 '놓친 알림'
BUNDLE_OVER = 3                 # 같은 시각 알림이 이보다 많으면 화면에서 한 줄로 묶는다

# 알림 코드 — 모두 '하루 기준 시각(ALERT_TIME)' 에 울린다. m30 만 예외(시작 30분 전).
#   d7/d3/d1 : 시작 7·3·1일 전      end1 : 기간형의 종료 전날 '내일 마감'      m30 : 시각이 있는 일정의 30분 전
REMINDER_CODES = ("d7", "d3", "d1", "end1", "m30")

# 유형별 기본 알림. 요구사항 기본값은 D-7/3/1 이지만, 개강·휴업일·수업일수 같은 '알림이 필요 없는' 유형까지
# 3번씩 울리면 정작 등록금·수강신청 알림이 묻힌다 → 유형마다 다르게 둔다(구현 결정, README 참고).
DEFAULT_REMINDERS: dict[str, tuple[str, ...]] = {
    "tuition": ("d7", "d3", "d1", "end1", "m30"),
    "course_reg": ("d7", "d3", "d1", "end1", "m30"),
    "registration": ("d7", "d3", "d1", "end1", "m30"),
    "grade": ("d3", "d1", "end1", "m30"),
    "exam": ("d7", "d1"),
    "vacation": ("d1",),
    "event": ("d3",),
    "holiday": (),
    "etc": (),                  # 수업일수 1/4·보강일·수업평가 — 필요하면 항목별로 켠다
}

# ── 수집 원천 4곳 (D1: ① 학사일정 표 ② 학사 공지 ③·④ 내 소속 홈페이지) ──
# 사용자는 /settings/sources · /academic 에서 원천마다 켜고 끈다. 끄면 새로 받지 않고, 그 원천에서 온 일정도 목록·캘린더에서 빠진다
# (지우지 않으므로 다시 켜면 돌아온다).
# priority 는 병합 시 대표값을 고르는 순서(작을수록 우선, F1 7절 '중복 판정') — 학교 전체 > 내 학부 > 내 단과대학.
# kind 는 bachelor/sources/ 의 수집기 이름. profile_board 는 프로필(C2) 소속으로 홈페이지를 찾아(homepages.py)
# 그 사이트의 학사 공지 게시판을 찾은 뒤(k2web_discover) K2Web 수집기로 읽는다.
BUILTIN_SOURCES: list[dict] = [
    {
        "key": "jnu_calendar",
        "name": "학교 학사일정",
        "kind": "calendar_table",
        "url": "https://www.jnu.ac.kr/WebApp/web/HOM/TOP/Schedule300.aspx?type=1",
        "priority": 1,
        "interval": "06·18시",
        "enabled": True,
    },
    {
        "key": "jnu_notice",
        "name": "학교 공지 › 학사안내",
        "kind": "jnu_board",
        "base": "https://www.jnu.ac.kr",
        "list_path": "/WebApp/web/HOM/COM/Board/board.aspx",
        "params": {"boardID": "5", "cate": "5"},     # cate=5 학사안내
        "url": "https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx?boardID=5&cate=5",
        "priority": 2,
        "interval": "06·18시",
        "enabled": True,
    },
    {
        "key": "my_dept",
        "name": "내 학부 공지",
        "kind": "profile_board",
        "scope": "dept",                 # 프로필의 학과(학부) → 그 홈페이지
        "priority": 3,
        "interval": "06·18시",
        "enabled": True,
    },
    {
        "key": "my_college",
        "name": "내 단과대학 공지",
        "kind": "profile_board",
        "scope": "college",              # 프로필의 단과대학 → 그 홈페이지
        "priority": 4,
        "interval": "06·18시",
        "enabled": True,
    },
]
# 목록에 없는 원천(예전 기본값 aisw_haksa · 사용자가 추가했던 게시판)은 seed 때 지운다 — my_dept 가 대신한다

# ── LLM (선택) — notice_agent·Univ-Us_AI 와 같은 슬롯 이름. 비어 있으면 규칙 추출만 한다 ──
LLM_BASE_URL = os.environ.get("LLM_MAIN_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_MAIN_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MAIN_MODEL", "")
LLM_TIMEOUT = 90


def llm_configured() -> bool:
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
