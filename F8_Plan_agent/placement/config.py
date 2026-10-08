"""F8 공강 기반 학습 플랜 자동 배치 — 설정 (경로 · 낮 시간대 기본값 · 블록 길이 · 공강 공부 규칙 · 설정값 범위).

요구사항: 요구사항정의서.md F8 절 / 화면: Frontend-Route.md 13절.

설치할 것이 없다
  - 전부 **표준 라이브러리**다. 계산은 규칙 기반 코드로만 한다(F8-R18 — LLM 을 부르지 않는다).
    대시보드 백엔드가 그대로 import 하고, 명령줄(desktop/cli.py)은 표준 라이브러리만으로 돈다.

역할 경계 (2026-10-07 사용자 요청으로 다시 정함)
  - **F8 = 낮 공강(기본 09:00~18:00)**: 과제(F7 순서) · 할 일(C1) 을 먼저 넣고, **남는 공강은 공부 블록**으로 채운다.
    공부 과목은 남은 진도율 ÷ 시험까지 남은 날수로 고른다(rules.fill_study).
  - **F5 = 저녁(기본 19:00~24:00)**: 시험 공부 계획의 날짜별 분량은 F5 가 저녁 시간대에 이어 놓는다(공부 캘린더).
    F8 은 저녁을 쓰지 않고, F5 하루치 분량을 옮기지도 않는다.
  - F7 = 무엇부터 — F8 은 F7 의 순서를 다시 계산하지 않는다(F7-R34).

저장하는 것 / 안 하는 것
  - **미리보기는 저장하지 않는다.** 계산은 부수효과가 없고, 캘린더를 바꾸는 것은 `배치하기` 뿐이다 (Frontend-Route 13-6).
  - data/placement.db   등록된 블록 — 자동 배치(auto)·내가 옮긴 것(user, 고정)·완료 체크
  - data/settings.json  공강 배치 설정 — **기본값과 다른 값만** (F7 설정과 같은 방식)

다른 폴더에서 읽는 것 (읽기만 한다 — 대시보드에서는 백엔드가 넘겨주고, 명령줄에서는 sources.py 가 직접 읽는다)
  - F3_Attendance_agent (수업 회차)      수업 · 휴강(F8-R08)
  - C1_Calendar_agent/data/univus.db      내 일정 · 할 일 (학사 일정에서 '내 일정에 넣기'로 만든 것 포함)
  학사 일정(F1)은 읽지 않는다 — 학교 전체 일정이라 내 시간을 차지하지 않는다 (2026-10-07 사용자 요청)
  - F5_Test_agent/data/exams.db           다가오는 시험 · 공부 진도율 (공강 공부 대상)
  - F6_Eclass_agent/data/eclass.db        과제 — F7 순위 계산을 거쳐 순서·필요 시간 (F8-R11 · R12)
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent             # F8_Plan_agent/
PROJECT_ROOT = ROOT.parent                               # 26 WE-Meet Project/

DATA_DIR = Path(os.environ.get("F8_DATA_DIR") or ROOT / "data")
DB_PATH = DATA_DIR / "placement.db"                      # 등록된 블록
SETTINGS_FILE = DATA_DIR / "settings.json"               # 사용자가 바꾼 설정만

# ── 다른 기능 폴더 (명령줄에서만 직접 읽는다 — sources.py) ──
F3_AGENT_DIR = Path(os.environ.get("F3_AGENT_DIR") or PROJECT_ROOT / "F3_Attendance_agent")
F5_AGENT_DIR = Path(os.environ.get("F5_AGENT_DIR") or PROJECT_ROOT / "F5_Test_agent")
F6_AGENT_DIR = Path(os.environ.get("F6_AGENT_DIR") or PROJECT_ROOT / "F6_Eclass_agent")
F7_AGENT_DIR = Path(os.environ.get("F7_AGENT_DIR") or PROJECT_ROOT / "F7_Task_agent")
C1_AGENT_DIR = Path(os.environ.get("C1_AGENT_DIR") or PROJECT_ROOT / "C1_Calendar_agent")

# ── 공강 배치 설정 기본값 (F8 6절 AvailabilitySettings — 2026-10-07 개정) ──
#   배치 범위는 **낮 09:00~18:00** (사용자 요청 — '공강 시간에 배치하기'). 저녁 19:00~24:00 은 F5 시험 공부 계획 전용이다.
#   그 범위 안의 빈 시간이 전부 공강이다 — 수업 사이뿐 아니라 첫 수업 전·마지막 수업 뒤, 수업 없는 날(공강 날)도.
#   주말은 기본으로 끈다 — 낮 9시간을 통째로 공부 블록으로 채우게 되기 때문이다(켜면 토·일도 같은 규칙).
#   하루 상한은 없다 (2026-10-06 사용자 요청 — F8-R15 삭제).
DEFAULTS = {
    "dayStart": "09:00",
    "dayEnd": "18:00",
    "lunchBreak": True,            # 점심 제외 (F8-R05)
    "lunchStart": "12:00",
    "lunchEnd": "13:00",
    "bufferMinutes": 10,           # 수업 앞뒤 이동·준비 여유 (F8-R04)
    "minSlotMinutes": 30,          # 이보다 짧은 빈 시간은 버린다 · 블록 최소 길이 (F8-R06 · R14)
    "maxBlockMinutes": 120,        # 블록 최대 길이 (F8-R14)
    "useWeekend": False,           # 주말 사용 (F8-R07)
    "rangeDays": 7,                # 배치 대상 기간 — 오늘부터 N일 (6절 range · Q1)
    "fillStudy": True,             # 과제·할 일을 넣고 남는 공강을 공부 블록으로 채운다 (2026-10-07)
}
KEYS = tuple(DEFAULTS)

# ── 설정값 범위 (그 밖은 오타로 본다) ──
BUFFER_CHOICES = (0, 5, 10, 15, 20, 30)
MIN_SLOT_RANGE = (15, 60)
MAX_BLOCK_RANGE = (30, 240)
RANGE_DAYS_CHOICES = (7, 14)
DAY_EARLIEST = "07:00"         # 낮 시작은 이보다 이를 수 없다
DAY_LATEST = "19:00"           # 낮 끝은 이보다 늦을 수 없다 — 그 뒤는 F5 저녁(시험 공부 계획) 몫
DAY_END = 24 * 60

# ── 배치 규칙 (F8 5절) ──
MAX_BLOCKS_PER_TASK_PER_DAY = 2    # 같은 작업은 하루 최대 2블록 (F8-R16 · Q5) — 공부 블록은 같은 시험(과목)끼리
NOW_ROUND_MINUTES = 10             # 오늘 슬롯은 '지금'을 10분 단위로 올림한 시각부터
DAY_STEP_MINUTES = 60              # '낮 시간 늘리기' 조정이 당기는 폭
PREVIEW_MAX_AGE_MINUTES = 30       # 미리보기 시각(at)을 등록에서 다시 쓸 수 있는 시간 — 넘으면 다시 계산하라고 한다
TODO_MINUTES = 30                  # 할 일(C1) 하나에 잡는 시간 — 할 일에는 소요시간 칸이 없다
TODO_LOOKBACK_DAYS = 14            # 날짜가 지난 미완료 할 일은 이 날수 안의 것만 '밀린 할 일'로 가져온다

# ── 공강 공부 (2026-10-07) ──
#   점수 = 남은 진도율(0~1) ÷ 시험까지 남은 날수(그 블록 날짜 기준, 최소 0.5일).
#   같은 날 같은 과목을 또 고를 때는 점수에 STUDY_REPEAT_PENALTY 를 곱한다 — 한 과목만 하루 종일 하지 않게.
#   진도율 100% 인 시험은 대상이 아니다. 대상 시험의 범위(30일)는 F5 study_targets 가 정한다.
STUDY_REPEAT_PENALTY = 0.5
STUDY_SAME_DAY_MIN_DAYS = 0.5      # 시험 당일(시험 시각 전) 블록의 '남은 날수'

# F7 그룹 — 배치 대상. 마감 없음(nodue)은 마감 전 슬롯이 없으므로 대상이 아니다.
#   놓친 마감(overdue)은 2주 안 것만 '이미 마감이 지났습니다'로 보여 준다(stale 은 F7 이 접어 둔 것).
ASSIGNMENT_GROUPS = ("now", "week", "later")

# ── 미배치 이유 (F8 5절 표 — 하루 상한 행은 2026-10-06 삭제) ──
REASONS = {
    "noSlot": "마감까지 빈 공강이 없습니다",
    "short": "30분 이상 연속 공강이 없습니다",
    "overdue": "이미 마감이 지났습니다",
    "sameTask": "같은 작업은 하루 2블록까지라 남았습니다",
    "excluded": "미리보기에서 뺐습니다",
}

TASK_LABEL = {"assignment": "과제", "todo": "할 일", "study": "공부", "exam": "시험 공부"}

# ── 캘린더 (C1 3절 kind=study) ──
STUDY_COLOR = "#5C6B22"            # 학습 블록 색 (F5 와 같다 — Frontend-Route 10-6 · 디자인 v3 올리브)
EVENT_PREFIX = "pb:"               # 등록된 블록의 캘린더 id — pb:<n>

WEEKDAY_KO = "월화수목금토일"


def default_settings() -> dict:
    return dict(DEFAULTS)


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
