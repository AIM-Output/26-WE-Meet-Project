"""univ_us_local 백엔드 설정 — 개인 로컬 서버(127.0.0.1)용.

원칙
  - 127.0.0.1 에만 바인딩한다. LAN 에 열려면 인증·HTTPS 를 먼저 붙인다.
  - 기능마다 폴더가 따로 있다(C1 · F6_Eclass_agent · F1 · C2 · F2 · F3 · F4 · F5). 이 서버는 그 API 를 붙이기만 한다.
    학교 로그인·브라우저는 C3_Login_agent 몫이다 — 이 서버의 .venv 에는 playwright 가 없다.
  - 내 일정·할 일도 C1_Calendar_agent 로 나갔다 (그 폴더의 data/univus.db). 여기에는 DB 가 없다.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent          # univ_us_local/
PROJECT_ROOT = ROOT.parent                                    # 26 WE-Meet Project/

# 기능 폴더 — 코드·DB 는 그 폴더에 있고, 여기서는 그 API 를 붙이기만 한다.
C1_AGENT_DIR = Path(os.environ.get("C1_AGENT_DIR") or PROJECT_ROOT / "C1_Calendar_agent")   # C1 서비스 캘린더 (calendar_core.api)
F6_AGENT_DIR = Path(os.environ.get("F6_AGENT_DIR") or PROJECT_ROOT / "F6_Eclass_agent")      # F6 e클래스 과제·마감 (eclass.api)
C3_AGENT_DIR = Path(os.environ.get("C3_AGENT_DIR") or PROJECT_ROOT / "C3_Login_agent")       # C3 포털 자동 로그인 (F6·C2·F2 가 빌려 쓴다)
F1_AGENT_DIR = Path(os.environ.get("F1_AGENT_DIR") or PROJECT_ROOT / "F1_Bachelor_agent")   # F1 학사 일정 (bachelor.api)
C2_AGENT_DIR = Path(os.environ.get("C2_AGENT_DIR") or PROJECT_ROOT / "C2_Profile_agent")    # C2 프로필·학과 마스터 (student.api)
F2_AGENT_DIR = Path(os.environ.get("F2_AGENT_DIR") or PROJECT_ROOT / "F2_Graduation_agent")  # F2 졸업요건 (graduation.api)
F3_AGENT_DIR = Path(os.environ.get("F3_AGENT_DIR") or PROJECT_ROOT / "F3_Attendance_agent")  # F3 출결 (attendance.api)
F4_AGENT_DIR = Path(os.environ.get("F4_AGENT_DIR") or PROJECT_ROOT / "F4_Textbook_agent")   # F4 강의자료 (textbook.api)
F5_AGENT_DIR = Path(os.environ.get("F5_AGENT_DIR") or PROJECT_ROOT / "F5_Test_agent")       # F5 시험 공부 일정 (exams.api)

FRONTEND_OUT = ROOT / "frontend" / "out"                     # `npm run build` 결과 (정적 export)

HOST = os.environ.get("UNIVUS_HOST", "127.0.0.1")
PORT = int(os.environ.get("UNIVUS_PORT", "8000"))

# 브라우저에서 오는 변경 요청(POST/PATCH/DELETE)은 이 Origin 에서만 받는다 (DNS 리바인딩·CSRF 대비).
ALLOWED_ORIGINS = {
    f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}",
    "http://localhost:3000", "http://127.0.0.1:3000",          # next dev
}
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# 과목 색 — courses.json 순서대로 배정 (7과목 + 여유)
COURSE_PALETTE = [
    "#4f46e5",  # indigo
    "#0891b2",  # cyan
    "#d97706",  # amber
    "#059669",  # emerald
    "#db2777",  # pink
    "#7c3aed",  # violet
    "#ea580c",  # orange
    "#2563eb",  # blue
    "#65a30d",  # lime
    "#9333ea",  # purple
]
