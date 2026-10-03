"""학사정보시스템에서 가져오기 (C2-R04) — 학년·학적·소속·평점·이수학점.

**C3_Login_agent 의 .venv 로 실행한다** (playwright·bs4 와 SSO 로그인 세션이 거기 있다):
    ..\\C3_Login_agent\\.venv\\Scripts\\python -m student.hakstd --out state\\import.json [--interactive]
대시보드의 '학사정보시스템에서 가져오기' 버튼은 jobs.py 가 이렇게 띄우고, 결과 파일을 읽어 프로필에 '자동'으로 넣는다.

로그인: 저장된 세션(C3_Login_agent/state/storage_state.json) → 안 되면 C3_Login_agent 의 reauthenticate(쿠키 복구 →
저장된 자격증명으로 무인 로그인) → 그래도 안 되고 --interactive 면 창을 띄워 직접 로그인. 비밀번호는 C3_Login_agent 코드만 다룬다.

읽는 곳 (notice_agent/references/site-structure.md §4, 2026-09-13 실측)
    /Home/DashBoard   div.infotext  "이름 | 학번 | N 학년 | 재학 | 성별 | 주전공 : <단과대> / <학부>"   #Score "3.xx / 4.5"
    /web/Sung/Sung010 [조회] → table#…gvData (년도·학기·성적·학점·교과목상태) → 취득학점·이수 학기·직전 학기 학점
이름·학번 칸은 **읽지 않는다** — 정규식으로 학년·학적·주전공만 꺼낸다 (C2-D5).
종료 코드: 0 성공 · 1 읽은 항목 없음(형식 변경 의심) · 2 로그인 필요
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse

from . import config as C

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(C.C3_BROWSERS))

FAIL_GRADES = {"F", "NP", "U", "W"}          # 취득학점에 넣지 않는 성적


class LoginRequired(RuntimeError):
    pass


def _soup(html: str):
    from bs4 import BeautifulSoup
    return BeautifulSoup(html, "html.parser")


def parse_dashboard(html: str) -> dict:
    soup = _soup(html)
    out: dict = {}
    info = soup.select_one("div.infotext")
    if info is not None:
        txt = info.get_text(" | ", strip=True)
        m = re.search(r"(\d)\s*학년", txt)
        if m:
            out["grade"] = int(m.group(1))
        m = re.search(r"\|\s*(재학|휴학|졸업유예|졸업|수료|제적)\s*\|", txt)
        if m:
            out["enrollment_status"] = m.group(1)
        m = re.search(r"주전공\s*[:：]\s*([^/|]+?)\s*/\s*([^|]+)", txt)
        if m:
            out["college"] = m.group(1).strip()
            out["department"] = m.group(2).strip()
    score = soup.select_one("#Score")
    if score is not None:
        m = re.search(r"(\d\.\d{1,2})\s*\|?\s*/\s*(4\.5|4\.3|4\.0)", score.get_text(" ", strip=True))
        if m:
            out["gpa"] = {"value": float(m.group(1)), "scale": float(m.group(2)), "basis": "전체"}
    return out


def parse_grades(html: str) -> dict:
    table = _soup(html).select_one("table[id$=gvData]")
    if table is None:
        return {}
    heads = [th.get_text(" ", strip=True) for th in table.select("th")]
    idx = {h: i for i, h in enumerate(heads)}
    if not all(k in idx for k in ("년도", "학기", "성적", "학점")):
        return {}
    per_term: dict[tuple[str, str], int] = defaultdict(int)
    total = 0
    for tr in table.select("tr"):
        tds = [td.get_text(" ", strip=True) for td in tr.select("td")]
        if len(tds) < len(heads):
            continue
        year, term = tds[idx["년도"]].strip(), tds[idx["학기"]].strip()
        if not re.fullmatch(r"\d{4}", year):        # '학기 평점' 합계 행 (이 행 때문에 학점이 2배로 잡힌 적이 있다)
            continue
        grade, credit = tds[idx["성적"]].strip().upper(), tds[idx["학점"]].strip()
        status = tds[idx["교과목상태"]] if "교과목상태" in idx else ""
        if not re.fullmatch(r"\d+(\.\d+)?", credit):
            continue
        if grade in FAIL_GRADES or "포기" in status or "취소" in status:
            continue
        c = int(float(credit))
        per_term[(year, term)] += c
        total += c
    if not per_term:
        return {}
    terms = sorted(per_term)
    regular = [t for t in terms if re.fullmatch(r"[12]\s*(?:학기)?", t[1])]     # 계절학기('하계 계절')는 이수 학기에 넣지 않는다
    last = regular[-1] if regular else terms[-1]
    return {"earned_credits": total, "semesters_completed": len(regular) or len(terms),
            "last_semester_credits": per_term[last]}


# ── SSO ────────────────────────────────────────────────────

def _on_sso(url: str) -> bool:
    return any(h in url for h in C.SSO_HOSTS)


def _on_hakstd_login(url: str) -> bool:
    """학사정보시스템 자체 로그인 화면(/Main/Login.aspx, '내 학사행정 로그인' 버튼 하나) — 2026-09-28 실측.
    예전에는 곧장 SSO 로 보냈지만 지금은 이 화면에 먼저 머문다 → 여기에 있으면 아직 로그인 안 된 것."""
    return "hakstd.jnu.ac.kr" in url and "login.aspx" in url.lower()


def _settle(page, timeout_s: int = 25) -> bool:
    """SSO 리다이렉트가 끝나 학사정보시스템 안쪽(로그인 화면이 아닌 곳)에 도착하면 True."""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        url = page.url
        if "hakstd.jnu.ac.kr" in url and not _on_sso(url) and not _on_hakstd_login(url):
            with contextlib.suppress(Exception):
                page.wait_for_load_state("networkidle", timeout=8_000)
            return True
        if _on_hakstd_login(url):
            return False
        with contextlib.suppress(Exception):
            if page.query_selector("#userPwd"):
                return False
        time.sleep(1)
    return False


def _enter(page, timeout_s: int = 30) -> bool:
    """대시보드로 가서 로그인 화면이면 '내 학사행정 로그인'을 눌러 SSO 세션으로 들어간다."""
    page.goto(C.HAKSTD_DASHBOARD, wait_until="load", timeout=60_000)
    if _settle(page):
        return True
    if _on_hakstd_login(page.url):
        with contextlib.suppress(Exception):
            page.click("#btnLogin", timeout=10_000)
            page.wait_for_load_state("load", timeout=30_000)
        if _settle(page, timeout_s):
            return True
    return False


def _c3_login():
    if not (C.C3_AGENT_DIR / "login" / "__init__.py").exists():
        return None
    if str(C.C3_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C3_AGENT_DIR))
    try:
        import login          # C3_Login_agent/login (포털 자동 로그인 — 그쪽 config 가 자기 폴더 기준 경로를 쓴다)
        return login
    except Exception:
        return None


@contextlib.contextmanager
def hakstd_page(interactive: bool = False):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        state = {"browser": None, "ctx": None, "page": None}

        def open_(storage: str | None, headed: bool = False) -> bool:
            state["browser"] = p.chromium.launch(headless=not headed)
            kw = {"user_agent": C.USER_AGENT}
            if storage:
                kw["storage_state"] = storage
            state["ctx"] = state["browser"].new_context(**kw)
            state["page"] = state["ctx"].new_page()
            return _enter(state["page"])

        def close() -> None:
            if state["browser"]:
                with contextlib.suppress(Exception):
                    state["browser"].close()
            state["browser"] = None

        ok = False
        for st in (C.HAKSTD_STATE, C.C3_STATE):
            if st.exists():
                if open_(str(st)):
                    ok = True
                    break
                close()
        if not ok:
            lm = _c3_login()
            if lm is not None and hasattr(lm, "reauthenticate"):
                print("  SSO 세션 만료 → C3_Login_agent 로 재인증 시도")
                if lm.reauthenticate(p) and C.C3_STATE.exists():
                    ok = open_(str(C.C3_STATE))
                    if not ok:
                        close()
        if not ok and interactive:
            print("  로그인 창을 엽니다 — 직접 로그인하세요 (학사정보시스템 화면이 뜨면 자동으로 이어집니다)")
            close()
            ok = open_(None, headed=True)
            deadline = time.time() + 600
            while not ok and time.time() < deadline and state["browser"].is_connected():
                url = state["page"].url
                if "hakstd.jnu.ac.kr" in url and not _on_sso(url) and not _on_hakstd_login(url):
                    ok = True
                    break
                time.sleep(1)
        if not ok:
            close()
            raise LoginRequired("학사정보시스템 로그인이 필요합니다 — C3_Login_agent 의 login.cmd 를 실행하거나 '로그인 창 열기'로 가져오세요")
        C.STATE_DIR.mkdir(parents=True, exist_ok=True)
        try:
            yield state["page"]
        finally:
            with contextlib.suppress(Exception):
                state["ctx"].storage_state(path=str(C.HAKSTD_STATE))
            close()


def fetch(interactive: bool = False) -> dict:
    data: dict = {}
    with hakstd_page(interactive) as page:
        if not urlparse(page.url).path.lower().startswith("/home/dashboard"):     # 로그인 뒤 첫 화면이 대시보드가 아닐 수 있다
            page.goto(C.HAKSTD_DASHBOARD, wait_until="load", timeout=60_000)
            _settle(page, 20)
        data.update(parse_dashboard(page.content()))
        page.goto(C.HAKSTD_GRADES, wait_until="load", timeout=60_000)
        if _settle(page, 20):
            with contextlib.suppress(Exception):
                page.click("input[id$=ibtnSearch]", timeout=10_000)
                page.wait_for_load_state("networkidle", timeout=20_000)
            data.update(parse_grades(page.content()))
    return data


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(C.IMPORT_OUT))
    ap.add_argument("--interactive", action="store_true")
    a = ap.parse_args(argv)
    print(f"======== {datetime.now():%Y-%m-%d %H:%M:%S} 학사정보시스템 가져오기 ========")
    try:
        data = fetch(a.interactive)
    except LoginRequired as e:
        print(f"  {e}")
        return 2
    print(f"  읽은 항목: {', '.join(sorted(data)) or '없음'}")          # 값은 로그에 남기지 않는다
    if not data:
        return 1
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump({"fetchedAt": datetime.now().isoformat(timespec="seconds"), "data": data}, f, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
