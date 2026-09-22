"""전남대 e클래스(sel.jnu.ac.kr, Moodle/유비온) 개인 자료 수집기 설정.

학교가 공지한 금지선(e클래스 공지 「저작권 유의사항 안내」):
  - 다운로드한 자료를 타인에게 배포·전송         → data/ 폴더는 절대 공유 금지
  - 계정정보 공유                                → state/ 폴더(세션)도 동일
  - 무단복사 방지 조치 무력화                    → 동영상(mod/vod)은 건드리지 않음
  - 수업자료를 인터넷에 게시                     → 깃허브 등 업로드 금지
"""
from pathlib import Path

BASE_URL = "https://sel.jnu.ac.kr"
LOGIN_URL = f"{BASE_URL}/login/index.php"
# SP 주도 SSO 시작점. 이미 SSO 세션이 있으면 로그인 화면 없이 곧장 Moodle 세션이 만들어지고,
# 없으면 IdP(idpm.jnu.ac.kr) → sso.jnu.ac.kr 로그인 화면으로 보낸다.
SSO_START_URL = f"{BASE_URL}/Rathon/Php/lms_sso.php"

ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "state" / "storage_state.json"   # login.py 가 저장하는 세션
CRED_FILE = ROOT / "state" / "cred.bin"               # DPAPI 로 암호화된 자격증명 (완전 무인용)
LOG_FILE = ROOT / "state" / "sync.log"                # 스케줄러 실행 로그
LOCK_FILE = ROOT / "state" / "sync.lock"              # sync.py 가 도는 동안 잡는 잠금 {pid, started_at} — 중복 실행 방지
LAST_RUN_FILE = ROOT / "state" / "sync.last.json"     # sync.py 가 끝날 때 남기는 결과 {…, finished_at, exit_code}
DATA_DIR = ROOT / "data"                              # 내려받은 자료
MANIFEST_FILE = DATA_DIR / "manifest.json"            # 에이전트가 읽을 파일 목록

# SSO 로그인 폼 (sso.jnu.ac.kr/Idp/Login.aspx) — 키보드보안 없음, 신뢰기기 쿠키로 2차 인증 생략
SSO_LOGIN_URL = "https://sso.jnu.ac.kr/Idp/Login.aspx?RelayState=" + BASE_URL + "/Rathon/Php/lms_sso.php"

# 과목 목록 후보 페이지 (앞에서부터 시도, 과목이 잡히는 첫 페이지 사용)
COURSE_LIST_URLS = [
    f"{BASE_URL}/local/ubion/user/index.php",   # 유비온 "나의 강의실"
    f"{BASE_URL}/my/",                          # Moodle 기본 대시보드
]

# 요청 간격(초). 서버 부하 방지 목적이므로 줄이지 말 것. 동시성은 항상 1.
REQUEST_INTERVAL = 1.5

# 내려받을 확장자 — 문서·코드만 (미디어 없음)
ALLOWED_EXT = {
    ".pdf", ".pptx", ".ppt", ".docx", ".doc", ".hwp", ".hwpx",
    ".xlsx", ".xls", ".csv", ".txt", ".md", ".zip",
    ".c", ".cpp", ".h", ".py", ".java", ".ipynb",
}

# 파일 자료로 취급하는 활동 모듈 (/mod/<이름>/view.php)
RESOURCE_MODULES = {"resource", "folder", "ubfile"}

# 게시판(ubboard): 이름에 아래 단어가 들어간 것만 수집 — 교수·조교가 올리는 공지/자료실.
# Q&A·팀빌딩·자유게시판처럼 학생 글이 올라오는 곳은 타인 개인정보가 섞이므로 수집하지 않는다.
BOARD_INCLUDE = ("공지", "자료")
BOARD_MAX_POSTS = 30            # 게시판당 최근 글 수 (목록 첫 페이지)

# 과제(assign): 설명·첨부·마감·제출상태를 기록한다 (본인 것만 보인다).
# 마감 일정: 캘린더 '다가오는 일정' + 과제 페이지를 합친다 (동영상 시청 기한 포함).
CALENDAR_URL = f"{BASE_URL}/calendar/view.php?view=upcoming"

# 그 외 모듈은 전부 스킵된다. 특히:
#   vod / ubcontent / econtent … 동영상 (복사방지 무력화 금지) — 제목·링크만 courses.json 에 기록
#   quiz / attendance          … 퀴즈·출석 (자료 아님)

# 파일 하나당 최대 용량(MB) — 대용량 미디어 차단
MAX_FILE_MB = 100

# 로그인에 쓴 Chromium 과 같은 계열의 UA (호환성 목적)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
