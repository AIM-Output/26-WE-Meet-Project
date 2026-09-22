"""notice_agent 설정 — F11 장학 공지 매칭·신청서 초안 (Univ-Us `notice_ai-agent` 모듈).

수집 대상 게시판(SOURCES), 경로, 요청 간격, LLM 슬롯을 한 곳에 모은다.
게시판 구조(셀렉터·URL 규칙)의 근거는 references/site-structure.md 에 있다.

지키는 선
  - 요청 간격 REQUEST_INTERVAL 은 줄이지 않는다 (학교 서버 부담 금지).
  - data/ (수집 공지·프로필·초안) 와 state/ (세션) 는 .gitignore — 공유 금지.
  - 학사정보시스템(SSO) 소스는 본인 계정으로만, 조회만 한다. 어떤 신청 버튼도 누르지 않는다.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # notice_agent/
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
STATE_DIR = ROOT / "state"
ASSETS_DIR = ROOT / "assets"
PROMPT_DIR = ASSETS_DIR / "prompts"
TEMPLATE_DIR = ASSETS_DIR / "templates"

NOTICE_DIR = DATA_DIR / "notices"          # 수집 원문 (source별 JSON)
ATTACH_DIR = DATA_DIR / "attachments"      # 내려받은 공고문 (PDF 등)
EXTRACT_DIR = DATA_DIR / "extracted"       # 자격요건 JSON
MATCH_DIR = DATA_DIR / "matches"           # 판정 결과
DRAFT_DIR = DATA_DIR / "drafts"            # 신청서 초안 (승인 대기 큐)
ALERT_DIR = DATA_DIR / "alerts"            # 알림 다이제스트
CACHE_DIR = DATA_DIR / "cache"             # LLM 응답 캐시
LOG_DIR = DATA_DIR / "logs"
MANIFEST_FILE = DATA_DIR / "manifest.json"  # 신규 판별용 (id → content_hash)
PROFILE_FILE = DATA_DIR / "profile.json"    # 사용자 프로필 (assets/profile.example.json 을 복사)
STATE_FILE = STATE_DIR / "storage_state.json"  # 자체 SSO 세션 (eclass_agent 것을 못 쓸 때만)

# ── 수집 정책 ──────────────────────────────────────────────
REQUEST_INTERVAL = 1.5      # 초. 동시성은 항상 1. 줄이지 말 것.
LIST_PAGES = 2              # 소스당 목록 페이지 수 (주기 수집이면 1~2면 충분)
MAX_ATTACH_MB = 20          # 첨부 1개 최대 크기
ATTACH_EXT = {".pdf", ".hwp", ".hwpx", ".docx", ".doc", ".xlsx"}
TEXT_EXTRACTABLE_EXT = {".pdf"}   # 본문 텍스트를 뽑아 추출기에 넣는 확장자 (hwp 는 못 읽음 → 확인 필요)

# 장학 관련 글만 남기기 위한 제목 키워드 (카테고리가 없는 게시판에 적용)
SCHOLARSHIP_KEYWORDS = ("장학", "학자금", "근로장학", "등록금 감면", "지원금", "멘토링 장학")
# 제목에 이 단어가 있으면 결과 공지·홍보성 글로 보고 후순위 (수집은 하되 초안은 만들지 않음)
RESULT_KEYWORDS = ("선발 결과", "합격자", "발표", "결과 안내", "명단", "박람회 홍보")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# ── 수집 소스 ──────────────────────────────────────────────
# kind 는 scripts/sources/ 의 수집기 이름. 구조가 같은 게시판은 같은 kind 를 쓴다.
#   jnu_aspx   전남대 대표 홈페이지 계열 ASP.NET 게시판 (www.jnu.ac.kr, international.jnu.ac.kr)
#   k2web      학과·단과대 홈페이지 (K2Web Wizard: aisw.jnu.ac.kr, cvg.jnu.ac.kr, sw.jnu.ac.kr …)
#   aicoss     인공지능혁신융합대학사업단 (aicoss.kr)
#   hakstd     학사정보시스템 장학 카탈로그 (SSO 필요, 교내·법정·교외 장학 지원조건 전문)
# enabled=False 로 두면 건너뛴다. 학과·단과대가 다르면 site/board 만 바꾸면 된다.
SOURCES: list[dict] = [
    {
        "key": "jnu_home_scholarship",
        "name": "전남대 홈페이지 공지사항 › 장학안내",
        "kind": "jnu_aspx",
        "base": "https://www.jnu.ac.kr",
        "list_path": "/WebApp/web/HOM/COM/Board/board.aspx",
        "params": {"boardID": "5", "cate": "8"},        # cate: 5 학사안내 · 8 장학안내 · 15 공모전 · 16 모집공고
        "page_param": "page",
        "id_param": "key",
        "category_label": "장학안내",
        "keyword_filter": False,                          # 카테고리 자체가 장학 → 전부 수집
        "requires_login": False,
        "enabled": True,
    },
    {
        "key": "aisw_dept",
        "name": "인공지능학부 공지 (학부(과) 공지)",
        "kind": "k2web",
        "base": "https://aisw.jnu.ac.kr",
        "site": "aisw",
        "board": "64",
        "category": "237",          # 말머리 '장학' (bbsOpenWrdSeq). None 이면 전체 + 키워드 필터
        "keyword_filter": True,     # 말머리 필터를 걸어도 상단 고정 공지는 섞여 오므로 제목 키워드로 한 번 더 거른다
        "requires_login": False,
        "enabled": True,
    },
    {
        "key": "cvg_college",
        "name": "AI융합대학 공지 (단과대학 공지)",
        "kind": "k2web",
        "base": "https://cvg.jnu.ac.kr",
        "site": "cvg",
        "board": "405",
        "category": None,
        "keyword_filter": True,
        "requires_login": False,
        "enabled": True,
    },
    {
        "key": "aicoss",
        "name": "인공지능혁신융합대학사업단(AICOSS) 공지",
        "kind": "aicoss",
        "base": "https://aicoss.kr",
        "list_path": "/www/notice/",
        "search_option": "",        # ''=All · '학생지원' · '교과' · '비교과' … (references/site-structure.md)
        "keyword_filter": True,
        "requires_login": False,
        "enabled": True,
    },
    {
        "key": "international",
        "name": "국제협력과 공지 (교환학생·해외 장학)",
        "kind": "jnu_aspx",
        "base": "https://international.jnu.ac.kr",
        "list_path": "/Board/Board.aspx",
        "params": {"BoardID": "3", "Mode": "List"},
        "page_param": "PageNum",
        "id_param": "Seq",
        "view_params": {"Mode": "View"},
        "keyword_filter": True,
        "requires_login": False,
        "enabled": True,
    },
    {
        "key": "hakstd_catalog",
        "name": "학사정보시스템 › 장학 › 전체 장학 안내 (교내·법정·교외 카탈로그)",
        "kind": "hakstd",
        "base": "https://hakstd.jnu.ac.kr",
        "requires_login": True,     # SSO. eclass_agent 세션/무인 로그인을 재사용한다 (sso_session.py)
        "enabled": True,
    },
]

# ── SSO (학사정보시스템) ─────────────────────────────────────
# eclass_agent 가 이미 신뢰기기 쿠키(2차 인증 면제 ~1년)와 DPAPI 자격증명을 관리한다.
# 그 폴더를 가리키면 로그인 코드를 다시 만들지 않고 세션만 빌려 쓴다.
ECLASS_AGENT_DIR = Path(os.environ.get("ECLASS_AGENT_DIR") or ROOT.parent / "eclass_agent")
HAKSTD_BASE = "https://hakstd.jnu.ac.kr"
HAKSTD_DASHBOARD = f"{HAKSTD_BASE}/Home/DashBoard"
HAKSTD_CATALOG_ALL = f"{HAKSTD_BASE}/web/Jang/Jang012"      # 전체 장학 안내 (지원대상·성적기준 전문)
HAKSTD_CATALOG_MINE = f"{HAKSTD_BASE}/web/Jang/Jang011"     # 학생 맞춤형 장학 안내 (표: 장학명/지원조건/문의처)
HAKSTD_GRADES = f"{HAKSTD_BASE}/web/Sung/Sung010"           # 기이수성적 (이수학점 합산용)
SSO_HOSTS = ("sso.jnu.ac.kr", "idpm.jnu.ac.kr")

# ── LLM 슬롯 (Univ-Us_AI/.env.example 과 같은 이름) ──────────
# 코드에는 모델명을 쓰지 않는다. 비어 있으면 LLM 단계는 규칙 추출만으로 동작하고 '확인 필요' 비율이 올라간다.
LLM_MAIN_BASE_URL = os.environ.get("LLM_MAIN_BASE_URL", "")
LLM_MAIN_API_KEY = os.environ.get("LLM_MAIN_API_KEY", "")
LLM_MAIN_MODEL = os.environ.get("LLM_MAIN_MODEL", "")
ENABLE_RESPONSE_CACHE = os.environ.get("ENABLE_RESPONSE_CACHE", "true").lower() != "false"
LLM_TIMEOUT = 90

# ── 판정 정책 ──────────────────────────────────────────────
CONFIDENCE_THRESHOLD = 0.6   # 추출 신뢰도가 이보다 낮으면 자동 판정하지 않고 '확인 필요'
DRAFT_FOR_NEEDS_REVIEW = True   # 애매한 건도 초안을 만들어 둔다 (놓치는 것이 더 나쁨). 알림에는 구분 표시.


def ensure_dirs() -> None:
    for d in (DATA_DIR, STATE_DIR, NOTICE_DIR, ATTACH_DIR, EXTRACT_DIR, MATCH_DIR,
              DRAFT_DIR, ALERT_DIR, CACHE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)


def llm_configured() -> bool:
    return bool(LLM_MAIN_API_KEY and LLM_MAIN_MODEL)


def enabled_sources(keys: list[str] | None = None) -> list[dict]:
    srcs = [s for s in SOURCES if s.get("enabled", True)]
    if keys:
        srcs = [s for s in srcs if s["key"] in keys]
    return srcs
