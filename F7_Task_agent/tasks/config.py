"""F7 과제 우선순위 확인·배치 — 설정 (경로 · 유형별 기본 소요시간 · 그룹 경계 · 설정값 범위).

요구사항: 요구사항정의서.md F7 절 / 화면: Frontend-Route.md 12절.

설치할 것이 없다
  - 전부 **표준 라이브러리**다. 계산은 규칙 기반 코드로만 한다(F7-R16 — LLM 을 부르지 않는다).
    대시보드 백엔드가 그대로 import 하고, 명령줄(run.cmd)은 아무 파이썬 3.10+ 로 돈다.

판단 신호는 두 가지뿐이다 (F7 D1)
  - **마감 일시**(F6 과제 원장) + **예상 소요시간**(유형별 기본값, 사용자가 고친 값은 F6 원장의 estimate_hours).
  - 계획서의 '성적 반영 비중'은 쓰지 않는다 (2026-09-25 결정 — 배점표를 얻을 경로가 없다).

저장하는 것 / 안 하는 것
  - **순위는 저장하지 않는다.** 시간이 흐르면 바뀌므로 조회할 때마다 계산한다 (F7 6절).
  - 과제별 소요시간은 **F6 원장**에 있다 — 재수집이 덮어쓰지 않는다(F7-R03 = F6-R34). 이 폴더는 고치지 않고 읽기만 한다.
  - 이 폴더가 쓰는 것은 설정 하나뿐이다: data/settings.json (안전계수 · 유형별 기본 시간 · 취침 시각, F7-R05·S08).

다른 폴더에서 읽는 것 (읽기만 한다 — 대시보드에서는 백엔드가 넘겨주고, 명령줄에서는 sources.py 가 직접 읽는다)
  - F6_Eclass_agent/data/eclass.db       과제·퀴즈·동영상 마감 · 제출 · 내가 체크함 · 사용자 소요시간
  - F3_Attendance_agent (수업 회차)       오늘 남은 시간에서 뺄 수업 (F7-R21)
  - C1_Calendar_agent/data/univus.db     오늘 남은 시간에서 뺄 내 일정
  - F5_Test_agent/data/exams.db          오늘 남은 시간에서 뺄 학습 분량(날짜 단위라 시각 없이 분만)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent             # F7_Task_agent/
PROJECT_ROOT = ROOT.parent                               # 26 WE-Meet Project/

DATA_DIR = Path(os.environ.get("F7_DATA_DIR") or ROOT / "data")
SETTINGS_FILE = DATA_DIR / "settings.json"               # 사용자가 바꾼 설정만 (기본값과 같은 값은 넣지 않는다)

# ── 다른 기능 폴더 (명령줄에서만 직접 읽는다 — sources.py) ──
F6_AGENT_DIR = Path(os.environ.get("F6_AGENT_DIR") or PROJECT_ROOT / "F6_Eclass_agent")
C1_AGENT_DIR = Path(os.environ.get("C1_AGENT_DIR") or PROJECT_ROOT / "C1_Calendar_agent")
F3_AGENT_DIR = Path(os.environ.get("F3_AGENT_DIR") or PROJECT_ROOT / "F3_Attendance_agent")
F5_AGENT_DIR = Path(os.environ.get("F5_AGENT_DIR") or PROJECT_ROOT / "F5_Test_agent")

# ── 과제 유형 (F7-R01) ──
#   F6 원장의 type 은 과제 · 퀴즈 · 동영상 · 일정(캘린더에서만 보인 것) 넷이다. '발표/프로젝트'는 e클래스에 따로 없으므로
#   제목으로 가른다 (kind_of). 순서가 우선순위다 — e클래스가 퀴즈·동영상이라고 한 것은 제목보다 앞선다.
#   기본 시간: 2026-10-06 사용자 요청으로 과제 2시간 · 퀴즈 30분 · 동영상 50분 · 프로젝트 4시간
#   (요구사항 F7-R01 처음 값은 3시간 · 30분 · 1시간 · 5시간). 동영상 50분은 시간으로 50/60 — 화면 칸에는 0.83 으로 보이고,
#   그 값을 저장해도 기본값으로 본다(settings.same).
KINDS = {
    "assignment": {"label": "과제", "hours": 2.0},
    "quiz":       {"label": "퀴즈", "hours": 0.5},
    "video":      {"label": "동영상", "hours": 50 / 60},
    "project":    {"label": "프로젝트", "hours": 4.0},
}
KIND_ORDER = ("assignment", "quiz", "video", "project")

# ── 계산 규칙 (F7 5절) ──
#   h = 마감 − 지금 (시간) · w = 예상 소요 × 안전계수 · s = h − w
SAFETY_FACTOR = 1.0                    # 2026-10-06 사용자 요청: 1.0 (예상 그대로, 요구사항 처음 값 1.5). 사람마다 설정에서 올린다
NOW_WITHIN_HOURS = 24.0                # h ≤ 24 이면 여유가 있어도 '지금 해야 함' (내일까지)
WEEK_SLACK_HOURS = 24.0 * 7            # s ≤ 7일 이면 '이번 주' (Q4 — 주말 기준으로 바꿀지 미결)
STALE_OVERDUE_DAYS = 14                # 2주 넘게 지난 놓친 마감은 접어 두고 건수만 (8절)
TOP_N = 3                              # 대시보드·브리핑 상위 N건 (F7-R32·R33)

# 그룹 — 순서가 곧 화면 순서다. nodue(마감 없음)는 순위 계산에서 빠지고 맨 아래에 따로 모은다 (8절).
GROUPS = {
    "overdue": {"label": "놓친 마감", "tone": "danger"},
    "now":     {"label": "지금 해야 함", "tone": "accent"},
    "week":    {"label": "이번 주", "tone": "neutral"},
    "later":   {"label": "나중에", "tone": "neutral"},
    "nodue":   {"label": "마감 없음", "tone": "neutral"},
}
GROUP_ORDER = ("overdue", "now", "week", "later", "nodue")

# ── 소요시간 범위 ──
#   0 이나 음수는 최소값으로 보정한다 (8절). 상한은 F6 원장이 받는 값과 같다 (F6 service.patch).
MIN_HOURS = 0.25
MAX_HOURS = 200.0

# ── 설정 (F7-R05 · S08) — 사용자가 바꿀 수 있는 값과 그 범위 ──
DEFAULT_BED_TIME = "24:00"
SAFETY_RANGE = (1.0, 3.0)              # 1.0 = 예상 그대로 · 3.0 = 세 배 (그 밖은 오타로 본다)
DEFAULT_HOURS_RANGE = (MIN_HOURS, 50.0)
#   취침 시각은 '오늘 밤' 기준이다. 12:00 이전 값(예: 01:30)은 자정을 넘긴 다음 날 새벽으로 본다 — 늦게 자는 학생.
#   24:00 = 자정. 18:00 보다 이른 취침은 받지 않는다(오타 방어).
BED_EARLIEST = "18:00"
BED_LATEST_AFTER_MIDNIGHT = "05:00"


def default_settings() -> dict:
    return {
        "safetyFactor": SAFETY_FACTOR,
        "defaultHours": {k: KINDS[k]["hours"] for k in KIND_ORDER},
        "bedTime": DEFAULT_BED_TIME,
    }
