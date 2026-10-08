"""C3 포털 자동 로그인 — 전남대 SSO 세션을 여러 기능이 같이 쓴다.

빌려 쓰는 법 (playwright 가 있는 python — 앱 실행 파일 / 개발 venv — 으로 도는 코드에서):

    sys.path.insert(0, r"...\\C3_Login_agent")
    import login
    login.STATE_FILE                 # 세션 파일 (storage_state) — 여기서 시작한다
    login.reauthenticate(p)          # 죽었으면: 쿠키 복구 → 저장된 자격증명으로 무인 로그인. 성공하면 STATE_FILE 갱신
    login.session_ok(ctx)            # e클래스 세션이 살아 있는가
    login.sso_continue(page)         # 내 화면에서 SSO 로그인 폼을 만났으면 저장된 자격증명으로 통과 (학사정보시스템)

playwright 가 없는 곳(대시보드 백엔드)에서도 import 할 수 있다 — status() 는 파일만 보고, 브라우저 함수는 처음 쓸 때 불러온다.
"""
from __future__ import annotations

from typing import Any

from . import config
from .config import BROWSERS, CRED_FILE, ROOT, STATE_DIR, STATE_FILE, USER_AGENT, browser_env

_LAZY = {"session_ok", "refresh_via_sso", "auto_login", "reauthenticate", "interactive_login", "sso_continue"}


def __getattr__(name: str) -> Any:
    if name in _LAZY:                               # playwright 는 여기서 처음 불러온다
        from . import session
        return getattr(session, name)
    raise AttributeError(name)


def status() -> dict:
    """설치·로그인 기록 상태 (파일만 본다 — 요청·브라우저 없음). 화면의 '로그인 필요' 안내와 가져오기 전 점검에 쓴다."""
    import datetime as _dt

    def mtime(p):
        try:
            return _dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except OSError:
            return None

    return {
        "installed": True,                       # 기능별 venv 가 없어진 뒤로 늘 참 (화면 타입 호환)
        "browsers": config.chromium_state(BROWSERS) == "ready",
        "hasSession": STATE_FILE.exists(),
        "sessionSavedAt": mtime(STATE_FILE),
        "hasCreds": CRED_FILE.exists(),
        "dir": str(ROOT),
    }


def problem(need_login_record: bool = True) -> str | None:
    """브라우저가 필요한 기능을 시작할 수 없는 이유 (없으면 None). C2·F2·F6 가 같은 문구를 쓴다."""
    if config.chromium_state(BROWSERS) == "installing":
        return "브라우저 엔진을 내려받는 중입니다 — 몇 분 뒤 다시 시도하세요"
    if not BROWSERS.exists():
        return "브라우저 엔진이 없습니다 — 앱을 다시 실행하면 내려받습니다"
    if need_login_record and not (STATE_FILE.exists() or CRED_FILE.exists()):
        return "학교 로그인 기록이 없습니다 — '로그인 창 열기'로 한 번 로그인하세요"
    return None


__all__ = ["config", "BROWSERS", "CRED_FILE", "ROOT", "STATE_DIR", "STATE_FILE", "USER_AGENT",
           "browser_env", "status", "problem", *sorted(_LAZY)]
