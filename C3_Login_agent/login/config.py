"""C3 포털 자동 로그인 — 설정 (경로 · SSO 주소 · 브라우저).

전남대 SSO(sso.jnu.ac.kr) 한 번의 로그인으로 e클래스(sel.jnu.ac.kr)·학사정보시스템(hakstd.jnu.ac.kr)이 같이 열린다.
그 로그인을 여러 기능이 같이 쓰므로 한 폴더에 모았다.

    F6 e클래스 수집 · C2 프로필 가져오기 · F2 기이수성적 · F11 장학 카탈로그(notice_agent) …

이 폴더가 가진 것 (다른 기능은 **빌려 쓰기만** 한다)
  - .venv                  playwright · beautifulsoup4 + Chromium(.venv/pw-browsers). 브라우저가 필요한 기능은 이 python 으로 돈다
  - state/storage_state.json  SSO 쿠키 + 신뢰 기기 쿠키(RathonSSO_TrustDevice_*, 약 1년 → 2차 인증 면제)
  - state/cred.bin         DPAPI(이 Windows 계정 전용)로 암호화한 아이디·비밀번호 — 완전 무인 재로그인용(선택)
  - login.reauthenticate(p)  세션이 죽었을 때: 조용한 쿠키 복구 → (저장돼 있으면) 무인 로그인
비밀번호는 이 폴더 코드만 다룬다. 빌려 쓰는 쪽은 세션 파일 경로와 reauthenticate() 만 안다.

지키는 선 (e클래스 공지 「저작권 유의사항 안내」 — 계정정보 공유 금지)
  - state/ 는 곧 '내 계정으로 로그인된 상태' 다. 복사·공유·업로드 금지(.gitignore).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent            # C3_Login_agent/
PROJECT_ROOT = ROOT.parent

STATE_DIR = Path(os.environ.get("C3_STATE_DIR") or ROOT / "state")
STATE_FILE = STATE_DIR / "storage_state.json"   # 세션 (쿠키 전부 — 신뢰 기기 쿠키를 골라내면 신뢰 인식이 깨진다)
CRED_FILE = STATE_DIR / "cred.bin"              # DPAPI 로 암호화된 자격증명 (완전 무인용, 없으면 반자동)
DEBUG_SHOT = STATE_DIR / "login_debug.png"      # 무인 로그인이 실패했을 때의 화면

# 브라우저가 필요한 기능이 쓰는 python 과 Chromium (setup.cmd 가 만든다)
VENV_DIR = ROOT / ".venv"
PYTHON = VENV_DIR / "Scripts" / "python.exe"
BROWSERS = VENV_DIR / "pw-browsers"

# ── 전남대 SSO ──
ECLASS_BASE = "https://sel.jnu.ac.kr"
# SP 주도 SSO 시작점. 이미 SSO 세션이 있으면 로그인 화면 없이 곧장 Moodle 세션이 만들어지고,
# 없으면 IdP(idpm.jnu.ac.kr) → sso.jnu.ac.kr 로그인 화면으로 보낸다.
SSO_START_URL = f"{ECLASS_BASE}/Rathon/Php/lms_sso.php"
# SSO 로그인 폼 (sso.jnu.ac.kr/Idp/Login.aspx) — 키보드보안 없음, 신뢰기기 쿠키로 2차 인증 생략
SSO_LOGIN_URL = "https://sso.jnu.ac.kr/Idp/Login.aspx?RelayState=" + SSO_START_URL
SESSION_CHECK_URL = f"{ECLASS_BASE}/my/"        # 여기가 로그인·SSO 로 튕기지 않으면 로그인된 것
SSO_HOSTS = ("sso.jnu.ac.kr", "idpm.jnu.ac.kr")

WAIT_SECONDS = 600          # 로그인 창(대화형) 최대 대기
AUTO_TIMEOUT = 120          # 무인 로그인 한 번의 제한시간

# 로그인에 쓴 Chromium 과 같은 계열의 UA (호환성 목적)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)


def browser_env(env: dict | None = None) -> dict:
    """이 폴더의 Chromium 을 쓰도록 PLAYWRIGHT_BROWSERS_PATH 를 채운 환경변수 (자식 프로세스용)."""
    out = dict(os.environ if env is None else env)
    out.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(BROWSERS))
    out["PYTHONUTF8"] = "1"
    return out


def use_browsers() -> None:
    """지금 프로세스가 이 폴더의 Chromium 을 쓰게 한다 (이미 지정돼 있으면 그대로)."""
    if not os.environ.get("PLAYWRIGHT_BROWSERS_PATH") and BROWSERS.exists():
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(BROWSERS)
