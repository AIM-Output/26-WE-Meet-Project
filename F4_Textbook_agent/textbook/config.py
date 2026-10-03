"""F4 강의자료 요약·예상 문제 — 설정 (경로 · 자료 원천 · 허용 확장자 · 용량).

요구사항: 요구사항정의서.md F4 절 / 화면: Frontend-Route.md 9절.

1차 범위 = **자료를 모아 두고 열어 보는 것까지** (F4-R01·R02·R04·R06~R08 · S01·S02·S05).
파싱·인덱싱·요약·문제·질문(F4-R03, R10~R34)은 AI팀 모델이 정해진 뒤에 붙인다 — 그 자리는
`index_state` 한 칸으로 비워 두었다(전부 `pending`).

설치할 것이 없다
  - **표준 라이브러리 + fastapi** 만 쓴다(쪽수도 zipfile·zlib 로 직접 읽는다). 대시보드 백엔드가 그대로 import 한다.
  - 파일을 새로 내려받지 않는다. e클래스 수집은 **F6_Eclass_agent** 가 하고(로그인은 C3), 여기서는 그 결과를 가져와 보관한다.

보관 (2026-09-30 변경 — 사용자 요청: "강의자료 데이터를 F4 폴더에 저장")
  - 수집된 파일을 `data/materials/<과목>/<활동>/<파일>` 로 들여놓고, **그 뒤로는 F4 가 자료의 주인**이다.
    화면이 여는 파일도, 나중에 인덱싱할 파일도 전부 여기 것이다.
  - 들여놓는 방법은 **하드링크 우선, 안 되면 복사**(`catalog.place`). 같은 드라이브면 하드링크라 디스크를 더 쓰지 않고,
    F6 가 같은 파일을 다시 내려받아도(같은 자리에 덮어쓴다) 내용이 그대로 따라온다.
  - F6 의 `data/` 는 **수집 캐시**로 남는다 — 지워도 F4 보관본은 살아 있고, F6 는 다음 수집 때 다시 받아 올 뿐이다.

다른 폴더에서 읽는 것 (읽기만 한다)
  - F6_Eclass_agent/data/manifest.json   내려받은 파일·글 목록 (F4-R01)
  - F6_Eclass_agent/data/courses.json    과목·활동 목록 — 활동 번호(cmid)로 자료의 종류를 가른다
  - F6_Eclass_agent/data/<과목>/…         실제 파일 (원본은 그 자리에 두고 경로만 가리킨다)

지키는 선 (학교 공지 「저작권 유의사항 안내」 · F4-R40~R42)
  - 원본 파일은 이 PC 를 떠나지 않는다. 밖으로 내보내는 기능(공유·업로드)을 만들지 않는다.
  - 파일을 넘겨주는 상대는 127.0.0.1 의 내 대시보드 하나뿐이다 (백엔드가 Host·Origin 을 막는다).
  - 1차에는 외부 API 호출이 아예 없다 — 동의(F4-R40)가 필요한 일은 인덱싱부터다.
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # F4_Textbook_agent/
PROJECT_ROOT = ROOT.parent

DATA_DIR = Path(os.environ.get("F4_DATA_DIR") or ROOT / "data")
LIBRARY_DIR = DATA_DIR / "materials"                     # 강의자료 보관함 — 여기가 자료의 주인이다 (아래 '보관' 참고)
UPLOAD_DIR = DATA_DIR / "uploads"                        # 직접 추가한 파일 (과목 폴더별, F4-R02)
DB_PATH = DATA_DIR / "textbook.db"                       # 자료 목록 (쪽수·해시·상태)

# ── F6 e클래스 수집 결과 (읽기 전용) ──
F6_AGENT_DIR = Path(os.environ.get("F6_AGENT_DIR") or PROJECT_ROOT / "F6_Eclass_agent")
ECLASS_DATA_DIR = Path(os.environ.get("F6_DATA_DIR") or F6_AGENT_DIR / "data")
ECLASS_ROOT = ECLASS_DATA_DIR.parent                     # manifest 의 'data\<과목>\…' 이 이 폴더 기준
ECLASS_MANIFEST = ECLASS_DATA_DIR / "manifest.json"
ECLASS_COURSES = ECLASS_DATA_DIR / "courses.json"

# ── 자료로 받아들이는 확장자 ──
# F6 가 내려받는 것과 같은 목록(F6 config.ALLOWED_EXT) + 직접 추가도 같은 기준으로 받는다.
ALLOWED_EXT = {
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".hwp", ".hwpx",
    ".xlsx", ".xls", ".csv", ".txt", ".md", ".zip",
    ".c", ".cpp", ".h", ".py", ".java", ".ipynb",
}
# 나중에 파싱·인덱싱 대상이 될 확장자. 나머지는 목록에 두되 인덱싱에서 뺀다 (F4 8절).
INDEXABLE_EXT = {".pdf", ".pptx", ".ppt", ".docx", ".doc", ".hwp", ".hwpx", ".txt", ".md"}
# 쪽수를 셀 수 있는 확장자 (docmeta.py). 나머지는 '—' 로 둔다.
PAGED_EXT = {".pdf", ".pptx", ".docx"}

MAX_FILE_MB = 100                                        # 업로드 상한 — 수집기(F6)와 같은 기준 (F4 8절)
MAX_SCAN_MB = 100                                        # 이보다 큰 파일은 쪽수·해시를 읽지 않는다 (시간)

# 활동 모듈 → 자료 종류. courses.json 의 활동 번호(cmid)로 찾는다.
RESOURCE_MODULES = {"resource", "folder", "ubfile"}      # 강의자료
BOARD_MODULES = {"ubboard"}                              # 게시판(공지·자료실) 첨부
ASSIGN_MODULES = {"assign", "ubassign"}                  # 과제 첨부

KIND_LABEL = {
    "lecture": "강의자료",
    "board": "게시판 첨부",
    "assignment": "과제 첨부",
    "upload": "직접 추가",
}

# 인덱싱 상태 → 화면 문구 (F4-R04 · S02 · 7절 '상태별 화면')
STATE_LABEL = {
    "pending": "분석 대기",
    "running": "분석 중",
    "done": "준비됨",
    "failed": "분석 실패",
    "ocr_needed": "텍스트 없는 PDF",
    "locked": "열 수 없음 (암호)",
    "unsupported": "분석 제외",
    "duplicate": "중복 파일",
}


# 과목 색 — 대시보드가 과목 목록을 넘겨주면 그 색을 쓴다. 명령줄에서 직접 읽을 때만 이 표를 쓴다 (순서는 F6 와 같다).
COURSE_PALETTE = [
    "#4f46e5", "#0891b2", "#d97706", "#059669", "#db2777",
    "#7c3aed", "#ea580c", "#2563eb", "#65a30d", "#9333ea",
]


def ensure_dirs() -> None:
    for d in (DATA_DIR, LIBRARY_DIR, UPLOAD_DIR):
        d.mkdir(parents=True, exist_ok=True)
