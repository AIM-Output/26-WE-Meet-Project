"""세션 확보 — 대화형 로그인 / 무인 자동 로그인 / 조용한 쿠키 복구.

모드:
  login.cmd            대화형: 브라우저 창을 띄워 본인이 직접 SSO 로그인 (+2차 인증).
                       이때 만들어지는 신뢰 기기 쿠키(~1년) 덕에 이후 2차 인증이 생략된다.
  login.cmd --auto     무인: setup_creds 로 저장한 자격증명으로 headless 자동 로그인.
                       신뢰 기기 쿠키가 있어야 2차 인증 없이 끝까지 진행된다.

sync.py 는 reauthenticate() 를 호출한다: 조용한 쿠키 복구 → (자격증명 있으면) 무인 로그인 순.

비밀번호는 DPAPI(auth.py)에서만 읽어 폼에 채운다. 코드·로그에 남기지 않는다.
SSO 로그인 폼(sso.jnu.ac.kr)에는 키보드 보안이 없어 일반 입력으로 채워진다.
"""
import sys
import threading
import time

from playwright.sync_api import sync_playwright

import auth
import config as C

WAIT_SECONDS = 600          # 대화형 최대 대기
AUTO_TIMEOUT = 120          # 무인 로그인 한 번의 제한시간


def session_ok(ctx) -> bool:
    """/my/ 가 로그인/SSO 로 튕기지 않으면 로그인됨. ctx 는 BrowserContext 또는 APIRequestContext."""
    req = getattr(ctx, "request", ctx)
    try:
        r = req.get(f"{C.BASE_URL}/my/", max_redirects=0, timeout=15_000)
    except Exception:
        return False
    if r.status == 200:
        return True
    if 300 <= r.status < 400:
        loc = r.headers.get("location", "")
        return not any(k in loc for k in ("/login/", "sso.jnu.ac.kr", "idpm.jnu.ac.kr"))
    return False


SSO_LINK_SEL = "a[href*='sso.jnu.ac.kr/Idp/Login']"


def _has_sso_form(page) -> bool:
    """SSO IdP 아이디/비번 폼(sso.jnu.ac.kr/Idp/Login.aspx)이 있는가."""
    for fr in page.frames:
        try:
            if fr.query_selector("#userId") and fr.query_selector("#userPwd"):
                return True
        except Exception:
            pass
    return False


def _fill_sso_form(page, uid: str, pw: str) -> bool:
    """SSO IdP 폼을 채우고 아이디/비번 로그인 버튼(#btnLoginButton)을 누른다.

    이 페이지는 '모바일 앱' 탭으로 열려서 아이디/비번 입력 pane(#login-tab-1)이 숨어 있다.
    숨어 있으면 해당 pane 을 활성화해 #userId 를 보이게 한 뒤 채운다.
    """
    for fr in page.frames:
        try:
            if not (fr.query_selector("#userId") and fr.query_selector("#userPwd")):
                continue
            if not fr.eval_on_selector("#userId", "e => e.offsetParent !== null"):
                fr.eval_on_selector(
                    "#login-tab-1",
                    "e => { e.classList.add('active', 'show'); e.style.display = 'block'; }",
                )
            fr.wait_for_selector("#userId", state="visible", timeout=8_000)
            fr.fill("#userId", uid)
            fr.fill("#userPwd", pw)
            btn = fr.query_selector("#btnLoginButton")
            if btn and btn.is_visible():
                btn.click()
            else:
                fr.press("#userPwd", "Enter")
            return True
        except Exception:
            continue
    return False


def _mfa_blocking(page) -> bool:
    """전화가 필요한 2차 인증 패널이 실제로 보이면 True (신뢰 기기 쿠키가 없을 때)."""
    for fr in page.frames:
        for sel in ("#btnMfaFidoPush", "#btnQrAuthSubmit", "#btnOtpAuthSubmit"):
            try:
                el = fr.query_selector(sel)
                if el and el.is_visible():
                    return True
            except Exception:
                pass
    return False


def _click_if_visible(page, selector: str) -> bool:
    """로그인 뒤 나타나는 확인 인터스티셜(예: '확인했습니다. 로그인 진행') 처리."""
    for fr in page.frames:
        try:
            el = fr.query_selector(selector)
            if el and el.is_visible():
                el.click()
                return True
        except Exception:
            pass
    return False


def refresh_via_sso(p, timeout_s: int = 40) -> bool:
    """저장된 SSO 쿠키만으로 headless 재접속 (비밀번호 미사용). SSO 서버 세션이 살아있을 때만 성공."""
    if not C.STATE_FILE.exists():
        return False
    browser = p.chromium.launch()
    try:
        context = browser.new_context(storage_state=str(C.STATE_FILE), user_agent=C.USER_AGENT)
        page = context.new_page()
        page.goto(C.SSO_START_URL, wait_until="load", timeout=timeout_s * 1000)
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            if session_ok(context):
                context.storage_state(path=str(C.STATE_FILE))
                return True
            if "sso.jnu.ac.kr" in page.url or page.query_selector("#userPwd"):
                return False                 # 로그인 폼이 떴다 = 쿠키만으론 불가
            time.sleep(2)
        return False
    except Exception:
        return False
    finally:
        browser.close()


def auto_login(p, uid: str, pw: str, timeout_s: int = AUTO_TIMEOUT) -> bool:
    """headless 에서 저장된 자격증명으로 자동 로그인. 신뢰 기기 쿠키가 있으면 2차 인증 생략."""
    browser = p.chromium.launch()
    try:
        # 전체 세션(신뢰 기기 쿠키 포함)을 그대로 로드해 실제 사용자와 같은 흐름으로 진행한다.
        # SSO_START → (선택 페이지면) 'SSO 로그인' 클릭 → idpm 경유(신뢰 기기 확인) → 폼 채움.
        kw = {"user_agent": C.USER_AGENT}
        if C.STATE_FILE.exists():
            kw["storage_state"] = str(C.STATE_FILE)
        context = browser.new_context(**kw)
        page = context.new_page()
        page.goto(C.SSO_START_URL, wait_until="load", timeout=timeout_s * 1000)
        deadline = time.time() + timeout_s
        submitted = False
        went_sso = False
        while time.time() < deadline:
            if session_ok(context):
                context.storage_state(path=str(C.STATE_FILE))
                return True
            _click_if_visible(page, "#btnFirstAuthEndConfirm")   # 로그인 뒤 확인 인터스티셜
            if _has_sso_form(page):
                # SSO 아이디/비번 폼 — 채워서 제출 (신뢰 기기면 2차 인증 없이 통과)
                if not submitted:
                    submitted = _fill_sso_form(page, uid, pw)
                    if submitted:
                        try:
                            page.wait_for_load_state("networkidle", timeout=20_000)
                        except Exception:
                            pass
                        continue
            elif not went_sso:
                # 로그인 선택/랜딩 페이지 → 'SSO 로그인' 클릭(없으면 URL 직행)해 IdP 폼으로.
                # Moodle 로컬 폼(#input-password)은 SSO 계정에서 안 되므로 쓰지 않는다.
                went_sso = True
                if not _click_if_visible(page, SSO_LINK_SEL):
                    try:
                        page.goto(C.SSO_LOGIN_URL, wait_until="load", timeout=timeout_s * 1000)
                    except Exception:
                        pass
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except Exception:
                    pass
                continue
            time.sleep(1.5)
        # 여기까지 왔으면 실패. 화면을 남긴다.
        if submitted and _mfa_blocking(page):
            print("  로그인 후 2차 인증(휴대폰) 대기 상태입니다. 신뢰 기기가 만료된 듯합니다.")
            print("  → login.cmd 를 한 번 수동 실행해 휴대폰 인증을 통과하면 다시 무인 가능합니다.")
        else:
            print("  자동 로그인 시간 초과. 아이디/비밀번호 또는 로그인 흐름을 확인하세요.")
        _debug_shot(page)
        return False
    except Exception as e:
        print(f"  자동 로그인 오류: {str(e)[:150]}")
        return False
    finally:
        browser.close()


def _debug_shot(page):
    try:
        C.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(C.STATE_FILE.parent / "login_debug.png"))
        print(f"  (디버그 스크린샷: {C.STATE_FILE.parent / 'login_debug.png'})")
    except Exception:
        pass


def reauthenticate(p) -> bool:
    """sync.py 용 오케스트레이터: 조용한 쿠키 복구 → (자격증명 있으면) 무인 로그인."""
    if refresh_via_sso(p):
        print("  SSO 쿠키로 재접속 성공.")
        return True
    creds = auth.load()
    if not creds:
        return False
    print("  저장된 자격증명으로 무인 로그인 시도...")
    return auto_login(p, creds["username"], creds["password"])


# ---------------------------------------------------------------- 대화형 / CLI

def interactive_login() -> int:
    C.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    force = threading.Event()

    def wait_enter():
        try:
            input()
            force.set()
        except Exception:
            pass

    threading.Thread(target=wait_enter, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        kw = {"user_agent": C.USER_AGENT}
        if C.STATE_FILE.exists():
            kw["storage_state"] = str(C.STATE_FILE)
            print("이전 세션 쿠키를 이어서 사용합니다 (SSO 세션이 살아있으면 로그인 화면 없이 끝납니다).")
        context = browser.new_context(**kw)
        page = context.new_page()
        page.goto(C.SSO_START_URL)
        creds = auth.load()   # 있으면 아이디/비번은 자동으로 채워주고, 사람은 휴대폰 2차 인증만 하면 된다
        if creds:
            print("저장된 자격증명으로 아이디/비밀번호는 자동 입력됩니다. 휴대폰 2차 인증만 진행하세요.")
        print("로그인/2차 인증 화면이 뜨면 진행하세요. e클래스로 돌아오면 자동으로 닫힙니다.")
        print("  (e클래스 화면까지 왔는데도 안 닫히면 → 이 터미널에서 Enter)")
        deadline = time.time() + WAIT_SECONDS
        last_report = time.time()
        detected = False
        filled = False
        while time.time() < deadline and not force.is_set():
            if not browser.is_connected() or not context.pages:
                print("브라우저가 닫혔습니다. 다시 실행하세요.")
                return 1
            if session_ok(context):
                detected = True
                break
            if creds and not filled and _has_sso_form(page):
                filled = _fill_sso_form(page, creds["username"], creds["password"])
                if filled:
                    print("  아이디/비밀번호 자동 입력 완료 → 휴대폰으로 2차 인증을 마치세요.")
            elif creds and filled and not _has_sso_form(page):
                filled = False   # 다음 화면(재로그인 등)에서 다시 채울 수 있도록
            if time.time() - last_report >= 15:
                last_report = time.time()
                print("  대기 중... 현재 탭:", [pg.url[:90] for pg in context.pages])
            time.sleep(1)
        context.storage_state(path=str(C.STATE_FILE))
        ok = detected or session_ok(context)
        browser.close()
    print(f"세션 저장 완료 -> {C.STATE_FILE}")
    print("서버가 로그인 상태로 확인했습니다." if ok else "경고: 서버가 아직 로그인 상태로 보지 않습니다.")
    return 0 if ok else 0


def auto_login_cli() -> int:
    creds = auth.load()
    if not creds:
        print("저장된 자격증명이 없습니다. 먼저 `setup-creds.cmd` 를 실행하세요.")
        return 1
    print("무인 로그인 시도 중...")
    with sync_playwright() as p:
        ok = auto_login(p, creds["username"], creds["password"])
    print("성공. 세션 저장됨." if ok else "실패. 위 안내를 확인하세요.")
    return 0 if ok else 2


def main() -> int:
    return auto_login_cli() if "--auto" in sys.argv else interactive_login()


if __name__ == "__main__":
    sys.exit(main())
