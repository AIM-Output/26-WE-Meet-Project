"""F5 시험 공부 일정 자동 추천 — 설정 (경로 · 시험 유형 · 난이도 계수 · 계획 기본값).

요구사항: 요구사항정의서.md F5 절 / 화면: Frontend-Route.md 10절.

설치할 것이 없다
  - 전부 **표준 라이브러리**다(공지 추출도 정규식 — LLM 을 부르지 않는다). 대시보드 백엔드가 그대로 import 하고,
    명령줄(run.cmd)은 아무 파이썬 3.10+ 로 돈다.
  - 계산은 규칙 기반 코드로만 한다 (F5-R26). LLM 은 공지 추출에만 쓸 수 있다고 되어 있으나, 1차는 정규식으로
    충분했다 — 2026-09-30 실측 공지 18건에서 시험·발표 3건을 다 찾았다 (notices.py 머리말).

다른 폴더에서 읽는 것 (읽기만 한다)
  - F6_Eclass_agent/data/manifest.json + 게시판 글(.md)   시험 공지 원천 (F5-R01, D1)
  - F6_Eclass_agent/data/courses.json                     과목 이름·색 — 대시보드에서는 백엔드가 같은 목록을 넘겨준다
  - F4_Textbook_agent/data/textbook.db                    범위 안 자료의 쪽수 합계 (F5-R10, D2) — textbook.store 로 읽는다
  - F1_Bachelor_agent/data/academic.db                    개강·종강 (학기 판정에만)

지키는 선
  - 시험·계획·진도는 이 PC 의 data/exams.db 에만 있다. 밖으로 보내지 않는다 (F5 9절 '프라이버시').
  - 전체 캘린더(C1)에 쓰는 것은 **날짜가 확정된 시험(kind=exam)** 뿐이다 (C1 3절).
    학습 블록(공부 계획)은 시험 공부 일정 캘린더(web/study_calendar.html → /study-calendar)에만 나온다 (2026-10-01).
    등록은 사용자가 미리보기를 확인한 뒤에만 한다 (D3) — 계산만으로 캘린더가 바뀌는 길은 없다.
  - 진도 재조정은 **제안만** 한다. 사용자가 누르기 전에는 등록된 블록을 건드리지 않는다 (F5 5절).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent             # F5_Test_agent/
PROJECT_ROOT = ROOT.parent                               # 26 WE-Meet Project/

DATA_DIR = Path(os.environ.get("F5_DATA_DIR") or ROOT / "data")
DB_PATH = DATA_DIR / "exams.db"                          # 시험 · 학습 계획 · 날짜별 분량

# ── 다른 기능 폴더 (읽기 전용) ──
F6_AGENT_DIR = Path(os.environ.get("F6_AGENT_DIR") or PROJECT_ROOT / "F6_Eclass_agent")      # F6 e클래스 수집
ECLASS_DATA_DIR = Path(os.environ.get("F6_DATA_DIR") or F6_AGENT_DIR / "data")
ECLASS_ROOT = ECLASS_DATA_DIR.parent                     # manifest 의 'data\<과목>\…' 이 이 폴더 기준
ECLASS_MANIFEST = ECLASS_DATA_DIR / "manifest.json"      # posts: 게시판 글 (과목 id · 게시판 · 작성일 · .md 경로)
ECLASS_COURSES = ECLASS_DATA_DIR / "courses.json"
F4_AGENT_DIR = Path(os.environ.get("F4_AGENT_DIR") or PROJECT_ROOT / "F4_Textbook_agent")    # F4 강의자료 (쪽수)
F1_AGENT_DIR = Path(os.environ.get("F1_AGENT_DIR") or PROJECT_ROOT / "F1_Bachelor_agent")    # F1 학사일정 (평가·시험 기간)
F1_DB = Path(os.environ.get("F1_DATA_DIR") or F1_AGENT_DIR / "data") / "academic.db"
F3_AGENT_DIR = Path(os.environ.get("F3_AGENT_DIR") or PROJECT_ROOT / "F3_Attendance_agent")  # F3 출결 (과목별 수업 회차)

# ── 과목마다 기본으로 두는 시험 (2026-10-01 사용자 요청) ──
#   모든 과목은 중간·기말 2회를 본다고 둔다. 시험이 없는 과목은 사용자가 과목별로 끈다(course_settings).
#   퀴즈·발표는 여기에 넣지 않는다 — 공지·직접 추가로만 생긴다.
DEFAULT_EXAM_TYPES = ("midterm", "final")
#   일정이 아직 안 나온 시험은 학사일정의 평가 기간 안에서 **그 과목의 수업 회차**로 임의로 잡는다(source='auto').
#   여러 회차 중에서는 공식 시험 주간의 **첫 수업**을 고른다 — 계획은 이른 날짜에 맞춰 두는 쪽이 안전하다
#   (실제 시험이 늦으면 여유가 생기고, 빠르면 준비가 안 된다).
AUTO_EXAM_CONFIDENCE = 0.5

# ── 시험 유형 (F5-R04) ──
#   마무리 복습일 기본값이 유형별로 다르다 (F5-R20: 중간·기말 2일 / 나머지 1일)
TYPES = {
    "midterm":      {"label": "중간고사", "reviewDays": 1},
    "final":        {"label": "기말고사", "reviewDays": 1},
    "quiz":         {"label": "퀴즈", "reviewDays": 1},
    "presentation": {"label": "발표", "reviewDays": 1},
    "etc":          {"label": "기타", "reviewDays": 1},
}
#   2026-10-02 사용자 요청: 마무리 복습 기본값은 모든 유형에서 **시험 전날 하루**(예전: 중간·기말 2일)
# 한 과목에 하나뿐인 유형 — id 를 (과목·유형)으로 만들어 날짜가 바뀌어도 같은 시험으로 본다(연기 감지, F5 8절).
# 나머지(퀴즈·발표)는 여러 번 있을 수 있어 날짜까지 id 에 넣는다.
SINGLETON_TYPES = {"midterm", "final"}
# 준비만 체크하는 유형 (2026-10-06 사용자 요청) — 발표는 공부 계획·자료 체크·진도 그래프 없이 '준비 완료' 하나만 누른다
PREP_ONLY_TYPES = {"presentation"}

# ── 난이도 → 쪽당 소요 시간 (F5-R12, 기본 1.5 / 2.5 / 4분 · 사용자 조정 가능) ──
#   Q2 미결: 이 값이 실제와 맞는지는 시범 사용 후에 본다.
DIFFICULTY = {
    "easy":   {"label": "쉬움", "pageMinutes": 1.0},
    "normal": {"label": "보통", "pageMinutes": 1.5},
    "hard":   {"label": "어려움", "pageMinutes": 2.0},
}
#   2026-10-02 사용자 요청: 기본 1 / 1.5 / 2분(그 전 1 / 2 / 3분, 처음 1.5 / 2.5 / 4분). 사용자가 '난이도 시간 설정'에서 바꾼다 —
#   바꾼 값은 data/exams.db 의 meta.difficulty_minutes 에 있고, 계산할 때 service 가 넣어 준다.
DEFAULT_DIFFICULTY = "normal"
PAGE_MINUTES_MAX = 30.0                 # 사용자가 직접 넣을 수 있는 쪽당 시간의 상한 (오타 방어)

# ── 계획 기본값 (F5 5절) ──
# 하루 학습 시간 기준(처음 4시간, F5-R14·R25)은 없다 — 2026-10-02 옵션 삭제, 2026-10-07 경고까지 삭제(사용자 요청).
#   DB 의 plans.cap_minutes 칸은 옛 계획 호환으로만 남아 있고 읽지 않는다.
MAX_REVIEW_DAYS = 5
MAX_EXCLUDED = 60
# 마무리 복습일의 '전체 훑기' 시간 = 총 소요 시간 × 이 비율 ÷ 복습일 수.
#   정독이 아니라 훑기라 정독 시간의 일부만 잡는다. 요구사항에 숫자가 없어 1차 값으로 둔다(Q2 와 같이 본다).
REVIEW_SKIM_RATIO = 0.3
DEFAULT_STUDY_DAYS = 3                  # 계획 만들기 화면의 학습일 기본값 (2026-10-02 사용자 요청)
QUIZ_MINUTES_PER_ITEM = 2               # 예상 문제 1문항당 (F5-R13). Q4 미결 — F4 문제 생성이 붙은 뒤 정한다
DEFAULT_QUIZ_COUNT = 20                 # 예상 문제 풀이를 켰을 때의 기본 문항 수 (F5 5절 예시의 20문항)

# 저녁 시간대 — **시험 공부 계획 전용** (2026-10-07 사용자 요청). 계획의 하루 분량은 이 시간대에 과목 순서대로 이어 놓인다
#   (공부 캘린더). 낮 09:00~18:00 공강은 F8(공강 배치)이 과제·할 일·공강 공부로 채운다 — 두 시간대가 겹치지 않는다.
#   사용자가 '가용 시간' 설정에서 바꾼다(meta.evening, 기본값과 다르면만 저장).
EVENING_START = "19:00"
EVENING_END = "24:00"
EVENING_EARLIEST = "17:00"              # 저녁 시작은 이보다 이를 수 없다 (낮은 F8 공강 몫)
# 공강 공부(F8) 대상 — 시험일이 오늘부터 이 날수 안인 시험만. 학기 끝 기말에 10월부터 공강을 쓰지 않게
STUDY_TARGET_DAYS = 30

# ── 공지 추출 (F5-R01·R02) ──
REVIEW_BELOW = 0.75                     # 신뢰도가 이보다 낮으면 status='review' — '확인 필요' 로 보낸다
NOTICE_LOOKBACK_DAYS = 200              # 작성일이 이보다 오래된 글은 보지 않는다 (한 학기치)
EXAM_MIN_DAYS_AHEAD = -30               # 작성일보다 이만큼 이전의 날짜는 버린다 (지난 시험 언급 방어)
EXAM_MAX_DAYS_AHEAD = 200               # 작성일보다 이만큼 뒤의 날짜는 버린다 (다음 학기 언급 방어)

# ── 캘린더 (C1 3절) ──
STUDY_COLOR = "#5C6B22"                 # 학습 블록 색 — 올리브 (디자인 v3, 옛 #4D7C0F)
EXAM_COLOR = "#9F2F2D"                  # 시험 자체 — 벽돌색(디자인 v3, 옛 #B91C1C) — 학습 블록과 구분되는 색·아이콘 (F5-R05)

# 과목 색 — 대시보드가 과목 목록을 넘겨주면 그 색을 쓴다. 명령줄에서 직접 읽을 때만 이 표를 쓴다 (F6 와 같은 순서).
COURSE_PALETTE = [  # 흙빛 팔레트 (디자인 v3 "Paper & Pine" — DESIGN.md)
    "#3d6b8c", "#a0522d", "#7a4f8a", "#2f7a73", "#9a6a14",
    "#a63d52", "#4c5fa6", "#8a6a4c", "#55753a", "#b05a7a",
]


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def review_days_for(exam_type: str) -> int:
    return TYPES.get(exam_type, TYPES["etc"])["reviewDays"]


def page_minutes_for(difficulty: str) -> float:
    return DIFFICULTY.get(difficulty, DIFFICULTY[DEFAULT_DIFFICULTY])["pageMinutes"]


def type_label(exam_type: str) -> str:
    return TYPES.get(exam_type, {}).get("label", exam_type)
