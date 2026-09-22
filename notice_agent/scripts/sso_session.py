"""전남대 SSO 세션 — 학사정보시스템(hakstd.jnu.ac.kr) 조회용.

eclass_agent(C.ECLASS_AGENT_DIR)가 이미 관리하는 것을 빌려 쓴다.
  - state/storage_state.json  : SSO 쿠키 + 신뢰기기 쿠키(RathonSSO_TrustDevice, ~1년 → 2차 인증 면제)
  - login.reauthenticate(p)   : 세션이 죽었을 때 조용한 쿠키 복구 → (저장돼 있으면) DPAPI 자격증명으로 무인 로그인
비밀번호는 eclass_agent 쪽 코드가 폼에 직접 채운다. 이 모듈은 자격증명 값을 다루지 않는다.

eclass_agent 가 없거나 실패하면 창을 띄워 본인이 직접 로그인하는 길(interactive)만 남긴다.
세션은 이 폴더의 state/ 에 따로 저장한다 (eclass_agent 의 파일을 덮어쓰지 않는다).

브라우저 바이너리: PLAYWRIGHT_BROWSERS_PATH 가 비어 있으면 eclass_agent/.venv/pw-browsers 를 가리킨다
(이 PC 의 %LOCALAPPDATA% 는 샌드박스에서 가상화되어 쓸 수 없었기 때문 — 프로젝트 폴더에 두는 것이 원칙).
"""
from __future__ import annotations

import contextlib
import importlib
import os
import sys
import time
from typing import Iterator, Optional

from . import config as C


def _prepare_browser_path() -> None:
    if os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
        return
    for cand in (C.ROOT / ".venv" / "pw-browsers", C.ECLASS_AGENT_DIR / ".venv" / "pw-browsers"):
        if cand.exists():
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(cand)
            return


_prepare_browser_path()


def eclass_login_module():
    """eclass_agent 의 login 모듈 (없으면 None). 그쪽 config 가 자기 폴더 기준 경로를 쓰므로 sys.path 에 얹기만 하면 된다."""
    if not (C.ECLASS_AGENT_DIR / "login.py").exists():
        return None
    if str(C.ECLASS_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.ECLASS_AGENT_DIR))
    try:
        return importlib.import_module("login")
    except Exception:
        return None


def state_candidates() -> list[str]:
    out = []
    if C.STATE_FILE.exists():
        out.append(str(C.STATE_FILE))
    ec = C.ECLASS_AGENT_DIR / "state" / "storage_state.json"
    if ec.exists():
        out.append(str(ec))
    return out


def on_sso(url: str) -> bool:
    return any(h in url for h in C.SSO_HOSTS)


def _settle(page, timeout_s: int = 25) -> bool:
    """SSO 리다이렉트 체인이 끝나 학사시스템 페이지에 도착하면 True."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if not on_sso(page.url) and "hakstd.jnu.ac.kr" in page.url:
            try:
                page.wait_for_load_state("networkidle", timeout=8_000)
            except Exception:
                pass
            return True
        # 로그인 폼이 실제로 떴으면 더 기다릴 이유가 없다
        try:
            if page.query_selector("#userPwd"):
                return False
        except Exception:
            pass
        time.sleep(1)
    return not on_sso(page.url)


class SsoError(RuntimeError):
    pass


@contextlib.contextmanager
def hakstd_page(interactive: bool = False, headless: bool = True) -> Iterator["Page"]:  # type: ignore[name-defined]
    """학사정보시스템에 로그인된 Playwright page 를 준다.

    순서: 저장된 세션으로 접속 → 안 되면 eclass_agent reauthenticate → 그래도 안 되면 (interactive 일 때만) 직접 로그인.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = ctx = page = None

        def try_state(state: Optional[str], headed: bool = False):
            nonlocal browser, ctx, page
            browser = p.chromium.launch(headless=not headed)
            kw = {"user_agent": C.USER_AGENT}
            if state:
                kw["storage_state"] = state
            ctx = browser.new_context(**kw)
            page = ctx.new_page()
            page.goto(C.HAKSTD_DASHBOARD, wait_until="load", timeout=60_000)
            return _settle(page)

        def close():
            nonlocal browser
            if browser:
                with contextlib.suppress(Exception):
                    browser.close()
            browser = None

        ok = False
        for st in state_candidates():
            if try_state(st):
                ok = True
                break
            close()

        if not ok:
            lm = eclass_login_module()
            if lm is not None:
                print("  SSO 세션 만료 → eclass_agent 로 재인증 시도...")
                if lm.reauthenticate(p):
                    ec = str(C.ECLASS_AGENT_DIR / "state" / "storage_state.json")
                    ok = try_state(ec)
                    if not ok:
                        close()

        if not ok and interactive:
            print("  브라우저 창을 엽니다. 직접 로그인하세요 (학사정보시스템 화면이 뜨면 자동으로 이어집니다).")
            close()
            browser = p.chromium.launch(headless=False)
            ctx = browser.new_context(user_agent=C.USER_AGENT)
            page = ctx.new_page()
            page.goto(C.HAKSTD_DASHBOARD, wait_until="load", timeout=60_000)
            deadline = time.time() + 600
            while time.time() < deadline:
                if not browser.is_connected():
                    break
                if not on_sso(page.url) and "hakstd.jnu.ac.kr" in page.url:
                    ok = True
                    break
                time.sleep(1)

        if not ok:
            close()
            raise SsoError(
                "학사정보시스템 로그인 실패. eclass_agent 의 `login.cmd`(수동) 또는 `setup-creds.cmd`(무인 저장)를 실행하거나, "
                "`python -m scripts.collect --source hakstd_catalog --interactive` 로 직접 로그인하세요.")

        C.STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            yield page
        finally:
            with contextlib.suppress(Exception):
                ctx.storage_state(path=str(C.STATE_FILE))     # 갱신된 쿠키를 우리 state/ 에 저장
            close()


def goto(page, url: str, settle_s: int = 20) -> bool:
    """세션이 살아있는 상태에서 페이지 이동. 도중에 SSO 로 튕기면 False."""
    page.goto(url, wait_until="load", timeout=60_000)
    return _settle(page, settle_s)
