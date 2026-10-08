"""세션 확보 — 로그인 창(대화형) / 무인 자동 로그인 / 조용한 쿠키 복구.

  python -m login           로그인 창: 브라우저 창을 띄워 본인이 직접 SSO 로그인 (+2차 인증).
                       이때 만들어지는 신뢰 기기 쿠키(~1년) 덕에 이후 2차 인증이 생략된다.
                       저장된 자격증명이 있으면 아이디·비밀번호는 자동으로 채워 준다(사람은 휴대폰 인증만).
  python -m login --auto    무인: 앱의 '자동 로그인 정보'(또는 login creds)로 저장한 자격증명으로 headless 자동 로그인.
                       신뢰 기기 쿠키가 있어야 2차 인증 없이 끝까지 진행된다.

빌려 쓰는 기능(F6 수집 · C2·F2 학사정보시스템 · notice_agent)은 reauthenticate(p) 를 부른다:
조용한 쿠키 복구 → (자격증명 있으면) 무인 로그인 순. 성공하면 state/storage_state.json 이 갱신된다.

비밀번호는 DPAPI(auth.py)에서만 읽어 폼에 채운다. 코드·로그에 남기지 않는다.
SSO 로그인 폼(sso.jnu.ac.kr)에는 키보드 보안이 없어 일반 입력으로 채워진다.
"""
from __future__ import annotations

import threading
import time

from playwright.sync_api import sync_playwright

from . import auth
from . import config as C

C.use_browsers()


def session_ok(ctx) -> bool:
    """/my/ 가 로그인/SSO 로 튕기지 않으면 로그인됨. ctx 는 BrowserContext 또는 APIRequestContext."""
    req = getattr(ctx, "request", ctx)
    try:
        r = req.get(C.SESSION_CHECK_URL, max_redirects=0, timeout=15_000)
    except Exception:
        return False
    if r.status == 200:
        return True
    if 300 <= r.status < 400:
        loc = r.headers.get("location", "")
        return not any(k in loc for k in ("/login/", *C.SSO_HOSTS))
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
            if "sel.jnu.ac.kr/login" in page.url:
                return False                 # e클래스 첫 화면으로 튕겼다 = SSO 쿠키가 끝난 세션 (fresh_state 참고)
            time.sleep(2)
        return False
    except Exception:
        return False
    finally:
        browser.close()


def fresh_state() -> dict | None:
    """로그인을 **새로 할 때** 실을 세션 — 저장된 쿠키에서 SSO 쪽 세션 쿠키(만료 없는 .jnu.ac.kr·sso.jnu.ac.kr 쿠키)를 뺀다.
    신뢰 기기 쿠키(idpm RathonSSO_TrustDevice_*, 약 1년)·WMONID 처럼 만료가 있는 쿠키와 e클래스 쿠키는 남긴다.

    storage_state 는 브라우저라면 닫을 때 버렸을 세션 쿠키까지 계속 저장한다. 그 SSO 세션이 서버에서 끝나면(다른 곳에서 같은
    계정으로 로그인 등) SSO 는 쿠키를 보고 '이미 로그인됨'이라 e클래스로 돌려보내고, e클래스는 거부해 첫 화면으로 — 'SSO 로그인'을
    눌러도 넘어가지 않는 고리였다(2026-10-09, 로그인 창·무인 로그인 둘 다). 이 쿠키를 빼면 SSO 로그인 폼이 정상으로 뜬다."""
    import json
    try:
        st = json.loads(C.STATE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    st["cookies"] = [c for c in st.get("cookies", [])
                     if (c.get("expires") or -1) > 0 or c.get("domain", "").lstrip(".") == "sel.jnu.ac.kr"]
    return st


def auto_login(p, uid: str, pw: str, timeout_s: int = C.AUTO_TIMEOUT) -> bool:
    """headless 에서 저장된 자격증명으로 자동 로그인. 신뢰 기기 쿠키가 있으면 2차 인증 생략."""
    browser = p.chromium.launch()
    try:
        # 신뢰 기기 쿠키 등 오래 가는 쿠키는 그대로 싣고, 끝났을 수 있는 SSO 세션 쿠키만 뺀다(fresh_state) — 무인 로그인은
        # 쿠키 복구(refresh_via_sso)가 실패한 뒤에만 오므로 그 세션 쿠키는 쓸모가 없고, 남겨 두면 로그인 폼까지 못 간다.
        # SSO_START → (선택 페이지면) 'SSO 로그인' 클릭 → idpm 경유(신뢰 기기 확인) → 폼 채움.
        kw = {"user_agent": C.USER_AGENT}
        st = fresh_state()
        if st is not None:
            kw["storage_state"] = st
        context = browser.new_context(**kw)
        page = context.new_page()
        page.goto(C.SSO_START_URL, wait_until="load", timeout=timeout_s * 1000)
        deadline = time.time() + timeout_s
        submitted = False
        went_sso = False
        while time.time() < deadline:
            if session_ok(context):
                C.STATE_DIR.mkdir(parents=True, exist_ok=True)
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
            print("  → 화면의 '로그인 창 열기'로 한 번 휴대폰 인증을 통과하면 다시 무인 가능합니다.")
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
        C.STATE_DIR.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(C.DEBUG_SHOT))
        print(f"  (디버그 스크린샷: {C.DEBUG_SHOT})")
    except Exception:
        pass


def sso_continue(page, timeout_s: int = 60) -> bool:
    """빌려 쓰는 기능이 **자기 화면에서** SSO 로그인 폼을 만났을 때(학사정보시스템 '내 학사행정 로그인' → sso.jnu.ac.kr):
    저장된 자격증명으로 채워 SSO 를 통과시킨다. 통과해 SSO 밖(원래 사이트)으로 돌아오면 True.

    reauthenticate() 는 e클래스(/my/)만 보고 판단해서, e클래스 세션은 살아 있는데 SSO 세션만 끝난 경우 '성공'이라 답하고도
    학사정보시스템은 여전히 로그인 화면이다(팀원 PC 에서 F2 가져오기가 실패한 경로, 2026-10-08). 그때 이 함수가 그 화면에서 직접 넘긴다.
    자격증명이 없거나 폼이 없거나 2차 인증(휴대폰)이 막으면 False. 비밀번호는 여기서만 다룬다."""
    creds = auth.load()
    if not creds or not _has_sso_form(page):
        return False
    if not _fill_sso_form(page, creds["username"], creds["password"]):
        return False
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        _click_if_visible(page, "#btnFirstAuthEndConfirm")
        if not any(h in page.url for h in C.SSO_HOSTS) and not _has_sso_form(page):
            return True
        if _mfa_blocking(page):
            print("  SSO 2차 인증(휴대폰) 대기 — 신뢰 기기가 만료된 듯합니다. '로그인 창 열기'로 한 번 인증하세요.")
            return False
        time.sleep(1)
    return False


def reauthenticate(p) -> bool:
    """빌려 쓰는 기능용 오케스트레이터: 조용한 쿠키 복구 → (자격증명 있으면) 무인 로그인."""
    if refresh_via_sso(p):
        print("  SSO 쿠키로 재접속 성공.")
        return True
    creds = auth.load()
    if not creds:
        return False
    print("  저장된 자격증명으로 무인 로그인 시도...")
    return auto_login(p, creds["username"], creds["password"])


# ---------------------------------------------------------------- 로그인 창 (대화형)

def interactive_login(wait_s: int = C.WAIT_SECONDS) -> int:
    """브라우저 창을 띄워 본인이 로그인한다. 로그인이 확인되면 세션을 저장하고 창을 닫는다.
    0 = 로그인됨 · 1 = 창을 닫음 · 2 = 시간 안에 로그인되지 않음. 대시보드의 '로그인 창 열기'도 이것을 띄운다(입력 없음)."""
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    force = threading.Event()

    def wait_enter():
        try:
            input()
            force.set()
        except Exception:                    # 대시보드가 띄우면 stdin 이 없다 — Enter 없이 자동 감지만
            pass

    threading.Thread(target=wait_enter, daemon=True).start()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        kw = {"user_agent": C.USER_AGENT}
        st = fresh_state()                   # 끝났을 수 있는 SSO 세션 쿠키는 뺀다 — 남기면 'SSO 로그인'이 첫 화면으로 되돌아온다
        if st is not None:
            kw["storage_state"] = st
            print("이전 세션(e클래스·신뢰 기기 쿠키)을 이어서 사용합니다 (e클래스 세션이 살아있으면 로그인 화면 없이 끝납니다).")
        context = browser.new_context(**kw)
        page = context.new_page()
        page.goto(C.SSO_START_URL)
        creds = auth.load()   # 있으면 아이디/비번은 자동으로 채워주고, 사람은 휴대폰 2차 인증만 하면 된다
        if creds:
            print("저장된 자격증명으로 아이디/비밀번호는 자동 입력됩니다. 휴대폰 2차 인증만 진행하세요.")
        print("로그인/2차 인증 화면이 뜨면 진행하세요. e클래스로 돌아오면 자동으로 닫힙니다.")
        print("  (e클래스 화면까지 왔는데도 안 닫히면 → 이 터미널에서 Enter)")
        deadline = time.time() + wait_s
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
    return 0 if ok else 2


def auto_login_cli() -> int:
    creds = auth.load()
    if not creds:
        print("저장된 자격증명이 없습니다. 먼저 앱 설정(연결 소스)의 '자동 로그인 정보'에서 저장하세요.")
        return 1
    print("무인 로그인 시도 중...")
    with sync_playwright() as p:
        ok = auto_login(p, creds["username"], creds["password"])
    print("성공. 세션 저장됨." if ok else "실패. 위 안내를 확인하세요.")
    return 0 if ok else 2


def check_cli() -> int:
    """저장된 세션이 지금 살아 있는지 (브라우저 창 없이 요청 한 번). 0 = 로그인됨 · 2 = 아님."""
    if not C.STATE_FILE.exists():
        print("세션 파일이 없습니다.")
        return 2
    with sync_playwright() as p:
        req = p.request.new_context(storage_state=str(C.STATE_FILE), user_agent=C.USER_AGENT)
        ok = session_ok(req)
        req.dispose()
    print("로그인됨" if ok else "세션 만료 (다음 수집 때 자동 재인증을 시도합니다)")
    return 0 if ok else 2
