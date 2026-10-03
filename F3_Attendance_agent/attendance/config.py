"""F3 출결·학사경고 예방 — 설정 (경로 · 원천 · 교시 시각 · 계산 기본값).

요구사항: 요구사항정의서.md F3 절 / 화면: Frontend-Route.md 8절.

설치할 것이 없다
  - 전부 **표준 라이브러리**다(시간표 조회도 urllib — 로그인이 필요 없는 공개 화면이라 브라우저가 필요 없다).
    대시보드 백엔드가 그대로 import 하고, 명령줄은 아무 파이썬 3.10+ 로 돈다.

다른 폴더에서 읽는 것 (읽기만 한다)
  - F6_Eclass_agent/data/courses.json     과목 목록 (F3-R01) — 대시보드에서는 백엔드가 같은 목록을 넘겨준다
  - F1_Bachelor_agent/data/academic.db    개강·종강·휴업일·학교 지정 보강일 (F3-R11·R12, F1-R01a)
  - F6_Eclass_agent/data/manifest.json + 게시판 글(.md)   과목 공지의 '휴강' → 그 회차를 자동으로 휴강 (2026-09-29 수정 ③)
  - C2 프로필(백엔드가 넘겨줌)             직전 학기 평점 → 학사경고 안내 (F3-R40)

지키는 선
  - 계산은 규칙 기반 코드로만. LLM 호출이 없다 (F3-R37).
  - 출결 기록은 이 PC 의 data/attendance.db 에만 있다. 밖으로 보내지 않는다 (F3 10절).
  - 시간표 조회 요청 간격 1.5초, 동시성 1 (F3 2절).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # F3_Attendance_agent/
PROJECT_ROOT = ROOT.parent

DATA_DIR = Path(os.environ.get("F3_DATA_DIR") or ROOT / "data")
STATE_DIR = Path(os.environ.get("F3_STATE_DIR") or ROOT / "state")
DB_PATH = DATA_DIR / "attendance.db"

# ── 다른 기능 폴더 (읽기 전용) ──
F6_AGENT_DIR = Path(os.environ.get("F6_AGENT_DIR") or PROJECT_ROOT / "F6_Eclass_agent")      # F6 e클래스 수집
ECLASS_DATA_DIR = Path(os.environ.get("F6_DATA_DIR") or F6_AGENT_DIR / "data")
ECLASS_ROOT = ECLASS_DATA_DIR.parent                          # manifest 의 'data\<과목>\…' 경로가 이 폴더 기준
ECLASS_COURSES = ECLASS_DATA_DIR / "courses.json"
ECLASS_MANIFEST = ECLASS_DATA_DIR / "manifest.json"   # posts: 게시판 글 (과목 id · 게시판 · 작성일 · .md 경로)
F1_AGENT_DIR = Path(os.environ.get("F1_AGENT_DIR") or PROJECT_ROOT / "F1_Bachelor_agent")
F1_DB = Path(os.environ.get("F1_DATA_DIR") or F1_AGENT_DIR / "data") / "academic.db"

# ── 학사정보시스템 시간표 조회 (공개, 로그인 불필요 — F3 2절, 2026-09-28 실측) ──
#   교과목명으로 검색해야 한다(학수번호로는 0건). 학년은 필수지만 결과를 거르지 않는다(학년 3 으로 2학년 과목이 나옴)
#   → 과목당 1회 요청. 결과가 0건이면 괄호 앞 이름으로 한 번 더.
TIMETABLE_URL = "https://hakstd.jnu.ac.kr/web/Suup/TimeTable/Suup053C.aspx"
FORM_PREFIX = "ctl00$ctl00$ContentPlaceHolder$ContentPlaceHolderSub$"
TERM_CODES = {"1": "1", "2": "2", "S": "6", "W": "7"}   # 학기 → ddlTerm (6 하계 · 7 동계)
REQUEST_INTERVAL = 1.5          # 초. 줄이지 말 것.
RETRY_WAITS = (3, 10)
HTTP_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# ── 교시 ↔ 시각 (C1-R05a · F3-R03). 전남대학교 「시간표 모듈」 그대로 (C-Q6 의 1차 값) ──
#   https://cloudweb.jnu.ac.kr/bbs/ds/3457/912224/artclView.do
#   월·수·금 50분 수업(1~15교시, 09:00 부터 매시 정각) / 화·목 75분 수업(1~10교시, 15분 쉬고 다음 교시)
#   → 같은 '5교시'라도 월요일은 13:00~13:50, 화요일은 15:00~16:15 다. 3학점 과목이 '화5목5'(2교시)인 이유.
#   교시 시각은 캘린더에 그리는 데만 쓴다 — 출결 계산은 시수가 아니라 **날짜(회)** 단위다(아래 계산 기본값).
PERIOD_SOURCE = "전남대학교 시간표 모듈 (월·수·금 50분 · 화·목 75분)"
PERIOD_SOURCE_URL = "https://cloudweb.jnu.ac.kr/bbs/ds/3457/912224/artclView.do"
MODULE_MWF = {p: (f"{8 + p:02d}:00", f"{8 + p:02d}:50") for p in range(1, 16)}
MODULE_TT = {p: (f"{(540 + (p - 1) * 90) // 60:02d}:{(540 + (p - 1) * 90) % 60:02d}",
                 f"{(615 + (p - 1) * 90) // 60:02d}:{(615 + (p - 1) * 90) % 60:02d}") for p in range(1, 11)}
WEEKDAY_MODULE = {0: "mwf", 1: "tt", 2: "mwf", 3: "tt", 4: "mwf", 5: "mwf", 6: "mwf"}   # 토·일은 월수금 표를 쓴다

WEEKDAYS = "월화수목금토일"

# ── 계산 기본값 (F3 3절 · 6절) ──
#   2026-09-29 수정 ①: 전남대는 출석을 **하루 단위**로 부른다(월 5·6교시든 수 5교시든 그날 한 번) → 계산은 시수가 아니라
#   **회(날짜)** 단위. 같은 과목이 하루에 두 번 나뉘어 있어도 그날은 1회다.
DEFAULT_LIMIT_RATIO = 0.25      # 결석 한도 = 총 횟수의 1/4. '1/4 초과'여야 초과다(정확히 1/4 은 아직 아님, Q2)
DEFAULT_LATE_TO_ABSENCE = 3     # 지각 3회 = 결석 1회 (D4). 0 이면 환산하지 않는다
CAUTION_RATIO = 0.5             # 허용의 절반을 쓰면 '주의'
LIMIT_CHOICES = (0.25, 1 / 3, 0.2)

# 양력 고정 공휴일 — 학사일정(F1)이 없거나 빠뜨렸을 때의 최소 보강. 음력·대체공휴일은 F1 에서만 온다.
FIXED_HOLIDAYS = {"01-01": "신정", "03-01": "삼일절", "05-05": "어린이날", "06-06": "현충일",
                  "08-15": "광복절", "10-03": "개천절", "10-09": "한글날", "12-25": "성탄절"}

# ── 학사경고 (F3-R40, Q3) ──
#   전남대 생활과학대학 '학사경고/유급' 안내: 학기 성적 평균평점 1.75 미만 → 학사경고, 3회면 제적.
WARNING_GPA = 1.75
WARNING_SCALE = 4.5
WARNING_SOURCE_URL = "https://engc.jnu.ac.kr/engc/2185/subview.do"

# ── e클래스 공지의 휴강 (2026-09-29 수정 ③) ──
NOTICE_RANGE_MAX_DAYS = 14      # '9월 16일~18일 휴강' 같은 기간은 이 길이까지만 펼친다

# ── 알림 (F3-R33) ──
ALERT_DEDUP_MIN = 10            # 같은 과목·같은 단계 알림을 이 시간 안에 다시 만들지 않는다 (눌렀다 되돌리기 반복 대비)


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR):
        d.mkdir(parents=True, exist_ok=True)
