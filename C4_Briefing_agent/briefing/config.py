"""C4 브리핑 — 설정 (경로 · 기본값 · 섹션 · 한 줄 요약 규칙).

요구사항: 요구사항정의서.md F10 절(아침 브리핑) — 2026-10-25 부터 **공통 기능 C4** 로 구현한다 (모든 기능의 알림·임박 항목을 모은다).
화면: Frontend-Route.md 15절.

설치할 것이 없다
  - 전부 **표준 라이브러리**다(라우터만 fastapi). 숫자·목록은 각 기능이 계산한 값을 그대로 옮겨 적고(F10-R17),
    LLM 은 맨 위 한 줄만 맡는다(F10 D1). LLM 이 없거나 실패해도 브리핑은 그대로 나온다.

저장하는 것
  - data/briefing.db 하나 — 날짜별 브리핑 **스냅샷**(만든 뒤 데이터가 바뀌어도 그대로, F10 7절) · 설정 · 기다림 기록.
  - 다른 기능의 데이터는 쓰지 않는다. 재료는 백엔드가 함수로 넘겨주고(api.Sources), 알림 센터(F1 표)에 한 줄 넣는 것도
    백엔드가 넘겨준 함수로 한다.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent             # C4_Briefing_agent/
PROJECT_ROOT = ROOT.parent                               # 26 WE-Meet Project/


def _load_env(path: Path) -> None:
    """.env 의 KEY=VALUE 를 환경변수로 (이미 있는 값은 건드리지 않는다). python-dotenv 없이 — F11·F12 와 같다."""
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

DATA_DIR = Path(os.environ.get("C4_DATA_DIR") or ROOT / "data")
DB_PATH = DATA_DIR / "briefing.db"

# 명령줄 make 가 재료를 빌리는 대시보드 백엔드 (univ_us_local/backend — 기능 어댑터가 거기 있다)
BACKEND_DIR = Path(os.environ.get("UNIVUS_BACKEND_DIR") or PROJECT_ROOT / "univ_us_local" / "backend")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# ── 생성·배달 (F10 4절 가) ──
DEFAULT_TIME = "08:00"                 # F10-R01 기본 08:00 (Q1 — 시범 사용 후)
DEFAULT_KEEP_DAYS = 30                 # F10-R22 보관 기간 기본 30일
KEEP_DAYS_CHOICES = (7, 14, 30, 60)
MISSED_AFTER_MIN = 60                  # 예정 시각보다 이만큼 늦게 만들면 '놓친 브리핑'(catchup) — F1 놓친 알림과 같은 값
WAIT_COLLECT_MIN = 5                   # 수집이 돌고 있으면 최대 이만큼 기다렸다가 만든다 (F10 9절)
ALERT_LOOKBACK_HOURS = 24              # '새 알림' — 지난 브리핑 이후, 그래도 최대 하루치만

# source — 정시 / 놓쳐서 켤 때 / 다시 만들기 (F10 7절)
SOURCES = ("scheduled", "catchup", "manual")

# ── 섹션 (F10 5절 + 각 기능이 브리핑에 싣기로 한 것) ──
#   순서가 곧 화면 순서다. empty = 비었을 때 보일 한 줄(None 이면 섹션을 숨긴다 — 5절 '섹션 규칙').
#   attention: F3-R35 '위험·초과 과목은 브리핑 상단' · F7 놓친 마감
#   deadlines: F6 마감(D-3) + F1-R35 학사 D-3 + F11-R74 장학 마감 임박 + F12-R34 담아 둔 것의 마감 + F5 시험 D-3
#   alerts   : 알림 센터에서 지난 브리핑 이후 안 읽은 것 (마감·학사 D-n 알림은 위 섹션과 겹치므로 뺀다)
SECTIONS = {
    "attention": {"label": "주의",       "icon": "alert",    "empty": None, "link": "/attendance"},
    "classes":   {"label": "오늘 수업",   "icon": "class",    "empty": None, "link": "/?view=week"},
    "events":    {"label": "오늘 일정",   "icon": "calendar", "empty": None, "link": "/?view=list"},
    "deadlines": {"label": "마감 임박",   "icon": "clock",    "empty": "사흘 안에 마감이 없습니다", "link": "/assignments?sort=priority"},
    "priority":  {"label": "먼저 할 것",  "icon": "flame",    "empty": None, "link": "/assignments?sort=priority"},
    "alerts":    {"label": "새 알림",     "icon": "bell",     "empty": None, "link": None},
}
SECTION_ORDER = ("attention", "classes", "events", "deadlines", "priority", "alerts")
ALL_EMPTY_TEXT = "오늘은 일정이 없습니다"   # F10-R16
SHOW_LINES = 5                         # 섹션당 최대 5줄 — 넘으면 화면이 '+N건 더' (10절 분량)
KEEP_LINES = 30                        # 스냅샷에 남기는 최대 줄 수 (그 이상은 건수만)
SOON_DAYS = 3                          # 마감 임박 = D-3 이내 (F10-R12)
TOP_N = 3                              # 먼저 할 것 = F7 상위 3건 (F10-R13)

# 재료 이름 → 화면에 보일 기능 이름 (못 읽은 재료는 gaps 로 남긴다 — '있는 섹션만 보여 준다', 9절)
SOURCE_NAMES = {
    "classes": "F3 출결(수업)", "events": "C1 캘린더", "deadlines": "F6 과제 마감", "priority": "F7 우선순위",
    "academic": "F1 학사일정", "study": "F5 시험 공부", "blocks": "F8 학습 블록", "scholarships": "F11 장학",
    "activities": "F12 대외활동", "alerts": "알림 센터",
}

# 새 알림에서 뺄 것 — 같은 내용이 다른 섹션에 이미 있다
#   F1 학사 D-n 알림(id rem:…) · F6 과제별 마감 알림(kind=deadline, refId 있음) · 브리핑 도착 알림 자신
ALERT_SKIP_KINDS = ("briefing",)
ALERT_SKIP_ID_PREFIX = ("rem:",)

# ── 한 줄 요약 (LLM, F10 5절 '한 줄 요약 규칙') — 슬롯 이름은 F1·F11·F12 와 같다(LLM_MAIN_*) ──
LLM_BASE_URL = os.environ.get("LLM_MAIN_BASE_URL", "").rstrip("/")
LLM_API_KEY = os.environ.get("LLM_MAIN_API_KEY", "")
LLM_MODEL = os.environ.get("LLM_MAIN_MODEL", "")
LLM_TIMEOUT = 3                        # 3초 넘으면 포기 (10절 속도)
HEADLINE_MAX = 60                      # 한 문장 60자 이내
PROMPT_VERSION = "c4-headline-1"
BANNED = ("화이팅", "파이팅", "힘내", "응원", "!")   # 격려 남발 금지


def llm_configured() -> bool:
    if os.environ.get("C4_LLM", "").lower() in ("off", "0", "false", "no"):
        return False
    return bool(LLM_BASE_URL and LLM_API_KEY and LLM_MODEL)


def default_settings() -> dict:
    return {"enabled": True, "time": DEFAULT_TIME, "keepDays": DEFAULT_KEEP_DAYS}
