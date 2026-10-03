"""e클래스 수집기 — 저장된 SSO 세션으로 본인 수강 과목의 자료·공지·과제·마감 일정을 모은다. (F6-R01~R07)

**C3_Login_agent/.venv 의 python 으로 돈다** (playwright · bs4). 직접 부르지 말고 runner(`python -m eclass sync`)를 거친다
— 잠금·실행 이력·재시도·원장 반영(reconcile)이 거기 있다.

- 브라우저를 띄우지 않고 HTTP 요청만 사용 (서버 부하 최소화)
- 요청 간격 config.REQUEST_INTERVAL, 동시성 1
- 다운로드 전에 확장자를 검사해 동영상 등은 요청 자체를 하지 않음
- 동영상(vod)은 재생 화면을 열지 않는다 — 과목 화면의 출석인정 마감 + 진도 현황의 진도율(시청 완료)만, 학생 글이 올라오는 게시판은 건드리지 않음
- 퀴즈는 마감 일시만 (문제·응시 여부는 저장하지 않는다, F6-R07)
- 세션이 만료되면 C3 의 reauthenticate(쿠키 복구 → 저장된 자격증명 무인 로그인)를 1회, 그래도 안 되면 EXIT_LOGIN

결과물 (data/ 아래):
  <과목>/<활동>/<파일>              강의자료 파일
  <과목>/게시판/<게시판>/<날짜>_<제목>.md   공지·자료실 글 (+첨부)
  <과목>/과제/<과제>.md              과제 설명·첨부·마감·제출상태
  deadlines.md / deadlines.json     마감 일정 (캘린더 + 과제 + 퀴즈, 날짜순)
  assignments.json                  과제 전체
  courses.json                      과목·활동 목록 (동영상 제목 포함)
  manifest.json                     내려받은 파일·글 목록
"""
from __future__ import annotations

import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from . import config as C

MOD_RE = re.compile(r"/mod/([a-z0-9_]+)/view\.php\?id=(\d+)")
UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
KDATE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\s*\([^)]*\))?\s*,?\s*(?:(오전|오후)\s*)?(\d{1,2}):(\d{2})")
ISODATE = re.compile(r"(\d{4})-(\d{1,2})-(\d{1,2})[ T](\d{1,2}):(\d{2})")     # 과제 화면은 '2026-10-5 00:00' 처럼 0 을 안 붙인다
RELDATE = re.compile(r"(오늘|내일|모레|어제)\s*,?\s*(\d{1,2}):(\d{2})")
REL_DAYS = {"오늘": 0, "내일": 1, "모레": 2, "어제": -1}
ALL_PARTS = ("files", "boards", "assign", "deadlines")
QUIZ_CLOSE_WORDS = ("종료", "마감", "닫", "close")

# 네트워크 문제로 볼 오류 문구 (Playwright/Node 소켓 오류 · Chromium net:: 오류)
NETWORK_HINTS = ("ENOTFOUND", "EAI_AGAIN", "ECONNREFUSED", "ECONNRESET", "ETIMEDOUT", "ENETUNREACH", "EHOSTUNREACH",
                 "ERR_INTERNET_DISCONNECTED", "ERR_NAME_NOT_RESOLVED", "ERR_CONNECTION", "ERR_NETWORK", "ERR_TIMED_OUT",
                 "ERR_ADDRESS_UNREACHABLE", "socket hang up", "Timeout", "timed out", "getaddrinfo")


class SessionExpired(Exception):
    pass


class NetworkError(Exception):
    pass


def is_network_error(e: BaseException) -> bool:
    msg = f"{type(e).__name__}: {e}"
    return isinstance(e, (NetworkError, ConnectionError, TimeoutError)) or any(h.lower() in msg.lower() for h in NETWORK_HINTS)


# ---------------------------------------------------------------- 유틸

def sanitize(name: str, limit: int = 80) -> str:
    name = UNSAFE_CHARS.sub("_", name).strip(" ._")
    return (name or "unnamed")[:limit]


def text_of(el, sep: str = " ") -> str:
    return el.get_text(sep, strip=True) if el else ""


def file_key(url: str) -> str:
    """파일을 식별하는 경로. Moodle 은 /pluginfile.php/ctx/.../이름.ext 형식과
    /pluginfile.php?file=/ctx/.../이름.ext 형식(유비온)을 둘 다 쓴다."""
    p = urlparse(url)
    q = parse_qs(p.query)
    if q.get("file"):
        return unquote(q["file"][0])
    return unquote(p.path)


def ext_of(url: str) -> str:
    return Path(file_key(url)).suffix.lower()


def filename_of(url: str) -> str:
    return sanitize(Path(file_key(url)).name)


def rel_path(p: Path) -> str:
    """manifest·assignments 에 적는 경로 — data 폴더의 부모 기준 ('data\\<과목>\\…')."""
    return str(p.relative_to(C.DATA_DIR.parent))


def abs_path(rel: str) -> Path:
    return C.DATA_DIR.parent / str(rel).replace("\\", "/")


def cmid_of(url: str) -> str:
    """활동 링크(/mod/<mod>/view.php?id=N) → N. 아니면 ''."""
    m = MOD_RE.search(url or "")
    return m.group(2) if m else ""


def mod_of(url: str) -> str:
    m = MOD_RE.search(url or "")
    return m.group(1) if m else ""


def parse_kdate(text: str, today: date) -> str:
    """'2026년 9월 15일(화요일), 23:59' / '2026년 9월 15일 오후 11:59' / '내일, 23:59' → 'YYYY-MM-DD HH:MM'. 못 읽으면 원문."""
    m = KDATE.search(text)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h, mi = int(m.group(5)), int(m.group(6))
        if m.group(4) == "오후" and h < 12:
            h += 12
        elif m.group(4) == "오전" and h == 12:
            h = 0
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    m = ISODATE.search(text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    m = RELDATE.search(text)
    if m:
        d = today + timedelta(days=REL_DAYS[m.group(1)])
        return f"{d.isoformat()} {int(m.group(2)):02d}:{m.group(3)}"
    return text.strip()


def quiz_close(soup: BeautifulSoup, today: date) -> str:
    """퀴즈 첫 화면에서 종료(마감) 일시만 읽는다 — 'YYYY-MM-DD HH:MM' 또는 ''. 문제·응시 기록은 보지 않는다(F6-R07).
    Moodle 은 '.quizinfo' 에 '이 퀴즈는 2026년 9월 28일(월요일), 23:59에 종료됩니다' / '종료 일시: …' 식으로 적는다."""
    box = soup.select_one(".quizinfo") or soup.select_one("#region-main") or soup
    for line in box.get_text("\n", strip=True).splitlines():
        if any(w in line.lower() for w in QUIZ_CLOSE_WORDS):
            v = parse_kdate(line, today)
            if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", v):
                return v
    return ""


def parse_assignment_status(soup: BeautifulSoup) -> dict[str, str]:
    """과제 화면의 제출 상태 표 → {제출 여부, 채점 상황, 종료 일시, …}."""
    status: dict[str, str] = {}
    for tr in soup.select("table.generaltable tr"):
        cells = tr.select("th, td")
        if len(cells) >= 2:
            k, v = text_of(cells[0]), text_of(cells[1])
            if k and "___" not in v:          # 템플릿 잔여물 제외
                status[k] = v
    return status


def parse_calendar(soup: BeautifulSoup, today: date) -> list[dict]:
    """캘린더 '다가오는 일정' → [{name, url, type, course, start, end, cmid, mod}]."""
    events: list[dict] = []
    for div in soup.select("div.event"):
        a = div.select_one("h3.referer a") or div.select_one("h3 a")
        if a is None:
            continue
        icon = div.select_one("img.icon")
        parts = [x.strip() for x in text_of(div.select_one(".date")).split("»")]
        url = urljoin(C.BASE_URL, a.get("href", ""))
        ev = {
            "name": text_of(a), "url": url,
            "type": (icon.get("title") or icon.get("alt") or "") if icon is not None else "",
            "course": text_of(div.select_one(".course a")),
            "start": parse_kdate(parts[0], today) if len(parts) > 1 else "",
            "end": parse_kdate(parts[-1], today),
            "cmid": cmid_of(url), "mod": mod_of(url),
        }
        if ev not in events:
            events.append(ev)
    return events


class Client:
    """레이트리밋 + 세션 만료 감지가 붙은 얇은 HTTP 클라이언트."""

    def __init__(self, req):
        self.req = req
        self._last = 0.0
        self.requests = 0

    def _throttle(self):
        wait = C.REQUEST_INTERVAL - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        self.requests += 1

    @staticmethod
    def _check_session(url: str):
        if "sso.jnu.ac.kr" in url or "idpm.jnu.ac.kr" in url or "/login/" in url:
            raise SessionExpired(url)

    def get(self, url: str):
        self._throttle()
        r = self.req.get(url)
        self._check_session(r.url)
        return r

    def head(self, url: str) -> dict:
        """본문 없이 응답 머리만 (파일 올린 시각용)."""
        self._throttle()
        r = self.req.fetch(url, method="HEAD")
        self._check_session(r.url)
        return dict(r.headers)

    def resolve(self, url: str, hops: int = 5):
        """리다이렉트를 한 단계씩 따라가되, 목적지가 파일(pluginfile.php)이면
        내려받지 않고 ("file", url, None) 을 돌려준다. 확장자 검사를 다운로드
        전에 하기 위함. 일반 페이지면 ("page", url, response)."""
        for _ in range(hops):
            self._throttle()
            r = self.req.get(url, max_redirects=0)
            if 300 <= r.status < 400:
                loc = urljoin(url, r.headers.get("location", ""))
                self._check_session(loc)
                if "pluginfile.php" in loc:
                    return "file", loc, None
                url = loc
                continue
            self._check_session(r.url)
            return "page", url, r
        raise RuntimeError(f"리다이렉트 과다: {url}")

    def page(self, url: str) -> BeautifulSoup | None:
        kind, _, r = self.resolve(url)
        return BeautifulSoup(r.text(), "html.parser") if kind == "page" else None


# ---------------------------------------------------------------- 탐색

def find_courses(c: Client) -> list[dict]:
    for list_url in C.COURSE_LIST_URLS:
        soup = c.page(list_url)
        if soup is None:
            continue
        courses: dict[str, dict] = {}
        for a in soup.select('a[href*="course/view.php?id="]'):
            href = urljoin(C.BASE_URL, a.get("href", ""))
            cid = parse_qs(urlparse(href).query).get("id", [""])[0]
            if not cid.isdigit() or cid == "1":  # id=1 은 사이트 홈
                continue
            name = text_of(a)
            cur = courses.get(cid)
            if cur is None or len(name) > len(cur["name"]):
                courses[cid] = {"id": cid, "name": name, "url": f"{C.BASE_URL}/course/view.php?id={cid}"}
        if courses:
            for v in courses.values():
                v["name"] = v["name"] or f"course_{v['id']}"
            print(f"[과목 목록] {list_url} -> {len(courses)}개")
            return list(courses.values())
    return []


def find_activities(c: Client, course: dict) -> dict[str, dict]:
    """과목 페이지의 모든 활동 (cmid → {mod, cmid, name, url}). 사이트 공용 게시판은 제외."""
    soup = c.page(course["url"])
    if soup is None:
        return {}
    acts: dict[str, dict] = {}
    for a in soup.select('a[href*="/mod/"]'):
        href = urljoin(C.BASE_URL, a.get("href", ""))
        m = MOD_RE.search(href)
        if not m:
            continue
        mod, cmid = m.groups()
        if mod == "ubboard" and int(cmid) < 100:   # 이용안내/Q&A/FAQ (사이트 공용)
            continue
        name = " ".join(text_of(a).split())
        cur = acts.get(cmid)
        if cur is None or len(name) > len(cur["name"]):
            acts[cmid] = {"mod": mod, "cmid": cmid, "name": name or f"{mod}_{cmid}",
                          "url": f"{C.BASE_URL}/mod/{mod}/view.php?id={cmid}"}
            if mod in C.VIDEO_MODULES:
                li = a.find_parent("li")
                acts[cmid].update(vod_period(text_of(li.select_one(".displayoptions")) if li else ""))
    return acts


PERIOD_RE = re.compile(r"(\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{2})(?::\d{2})?\s*~\s*(\d{4}-\d{1,2}-\d{1,2} \d{1,2}:\d{2})(?::\d{2})?")
CLOCK_RE = re.compile(r"\b(\d{1,3}:\d{2}(?::\d{2})?)\b\s*$")


def vod_period(text: str) -> dict:
    """과목 화면 동영상 옆 표시 '2026-09-01 00:00:00 ~ 2026-09-15 23:59:00, 13:40' → 출석인정 기간·길이.
    처음 나오는 기간이 출석인정 기간이다(진도 현황의 data-sterm/eterm 과 같다, 2026-10-02 실측). 뒤에 지각 기간이 붙어도 쓰지 않는다."""
    out = {"vodStart": "", "vodEnd": "", "length": ""}
    m = PERIOD_RE.search(text or "")
    if m:
        out["vodStart"] = parse_kdate(m.group(1), date.today())
        out["vodEnd"] = parse_kdate(m.group(2), date.today())
    lm = CLOCK_RE.search((text or "").replace(",", " "))
    if lm and (not m or lm.start() > m.end() - 1):
        out["length"] = lm.group(1)
    return out


def _clock_seconds(s: str) -> int:
    parts = [int(x) for x in (s or "").split(":") if x.isdigit()]
    if not parts:
        return 0
    while len(parts) < 3:
        parts.insert(0, 0)
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def parse_vod_progress(soup: BeautifulSoup) -> dict[str, dict]:
    """진도 현황(report/ubcompletion/user_progress.php)의 동영상 표 → {이름: {length, required, progress, watched}}.
    이 화면 위쪽의 학번·이름·전화 표는 읽지 않는다 — 'user_progress' 표만 본다.
    출석 인정 = 학습 인정 시간 ≥ 출석인정 요구시간(콘텐츠 길이의 90% 안팎) → 진도율이 요구시간/길이 이상이면 시청 완료로 본다."""
    out: dict[str, dict] = {}
    table = soup.select_one("table.user_progress")
    if table is None:
        return out
    for tr in table.find_all("tr"):
        cells = tr.find_all("td", recursive=False)
        name_td = next((td for td in cells if "text-left" in (td.get("class") or [])), None)
        if name_td is None:
            continue
        i = cells.index(name_td)
        rest = cells[i + 1:]
        if len(rest) < 4:
            continue
        name = " ".join(name_td.get_text(" ", strip=True).split())
        length, required = text_of(rest[0]), text_of(rest[1])
        pm = re.search(r"(\d+(?:\.\d+)?)\s*%", text_of(rest[3]))
        progress = float(pm.group(1)) if pm else 0.0
        total = _clock_seconds(length)
        need = 100.0 * _clock_seconds(required) / total if total and _clock_seconds(required) else C.VOD_DONE_PERCENT
        out.setdefault(name, {"length": length, "required": required, "progress": progress,
                              "watched": progress >= int(need)})       # 화면의 진도율은 반올림돼 있다 → 요구 비율은 내림
    return out


def extract_pluginfiles(root) -> list[str]:
    seen: dict[str, str] = {}
    for tag, attr in (("a", "href"), ("iframe", "src"), ("object", "data"), ("embed", "src"), ("source", "src")):
        for el in root.select(f'{tag}[{attr}*="pluginfile.php"]'):
            u = urljoin(C.BASE_URL, el.get(attr, ""))
            seen.setdefault(file_key(u), u)
    return list(seen.values())


def file_urls_for(c: Client, act: dict) -> list[str]:
    """자료 활동 → 내려받을 pluginfile URL 목록 (아직 아무것도 내려받지 않은 상태)."""
    url = act["url"]
    if act["mod"] == "resource":
        url += "&redirect=1"          # Moodle: 표시 방식과 무관하게 파일로 리다이렉트
    kind, target, r = c.resolve(url)
    if kind == "file":
        return [target]
    return extract_pluginfiles(BeautifulSoup(r.text(), "html.parser"))


# ---------------------------------------------------------------- 저장

def load_manifest() -> dict:
    m = {"files": {}, "posts": {}}
    if C.MANIFEST_FILE.exists():
        m.update(json.loads(C.MANIFEST_FILE.read_text(encoding="utf-8")))
    m.setdefault("files", {})
    m.setdefault("posts", {})
    return m


def save_json(path: Path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)               # 대시보드가 읽는 도중에 반쯤 쓴 파일을 보지 않게


def uploaded_at(headers: dict) -> str | None:
    """파일 응답의 Last-Modified → e클래스에 올린(고친) 시각, 로컬 'YYYY-MM-DDTHH:MM:SS'. 없으면 None.
    Moodle 은 pluginfile 응답에 파일의 timemodified 를 Last-Modified 로 준다(2026-10-03 실측: week 5.ppt 10/1 13:15 KST,
    받은 시각은 16:31). 과목 화면·자료 목록에는 올린 시각이 없다."""
    raw = {k.lower(): v for k, v in (headers or {}).items()}.get("last-modified")
    if not raw:
        return None
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(raw).astimezone().replace(tzinfo=None).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def download(c: Client, url: str, dest: Path) -> tuple[int, str | None]:
    """파일을 받는다 → (크기, 올린 시각)."""
    r = c.get(url)
    ct = r.headers.get("content-type", "")
    if ct.startswith("text/html"):
        raise RuntimeError("HTML 응답 (파일 아님)")
    if ct.startswith(("video/", "audio/")):
        raise RuntimeError(f"미디어 응답 스킵: {ct}")
    limit = C.MAX_FILE_MB * 1024 * 1024
    cl = r.headers.get("content-length")
    if cl and int(cl) > limit:
        raise RuntimeError(f"용량 초과 {int(cl) // 1024 // 1024}MB")
    body = r.body()
    if len(body) > limit:
        raise RuntimeError(f"용량 초과 {len(body) // 1024 // 1024}MB")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return len(body), uploaded_at(r.headers)


class Sync:
    def __init__(self, c: Client, manifest: dict, dry: bool):
        self.c = c
        self.manifest = manifest
        self.dry = dry
        self.stats: Counter = Counter()
        self.assignments: list[dict] = []
        self.quizzes: list[dict] = []
        self.videos: list[dict] = []
        self.courses_index: list[dict] = []

    def save_manifest(self):
        save_json(C.MANIFEST_FILE, self.manifest)

    def _soft(self, what: str, e: Exception):
        """활동 하나가 실패해도 나머지는 계속 — 단 세션 만료·네트워크 오류는 위로 올린다."""
        if isinstance(e, SessionExpired) or is_network_error(e):
            raise e
        print(f"   ! {what}: {e}")
        self.stats["error"] += 1

    # -- 파일 하나 ------------------------------------------------------
    def fetch_file(self, url: str, dest: Path, meta: dict) -> str | None:
        """허용 확장자면 내려받고 data 부모 기준 상대경로를 돌려준다. 이미 있으면 그 경로."""
        if ext_of(url) not in C.ALLOWED_EXT:
            self.stats["skip_ext"] += 1
            return None
        key = file_key(url)
        entry = self.manifest["files"].get(key)
        if entry and abs_path(entry["path"]).exists():
            self.stats["exists"] += 1
            if "uploaded_at" not in entry and not self.dry:
                self._backfill_uploaded(entry)
            return entry["path"]
        rel = dest.relative_to(C.DATA_DIR)
        if self.dry:
            print(f"   + {rel}")
            self.stats["planned"] += 1
            return None
        try:
            size, uploaded = download(self.c, url, dest)
        except Exception as e:
            self._soft(dest.name, e)
            return None
        self.manifest["files"][key] = {
            "url": url, "path": rel_path(dest), "size": size,
            "downloaded_at": datetime.now().isoformat(timespec="seconds"), "uploaded_at": uploaded, **meta,
        }
        self.save_manifest()
        self.stats["downloaded"] += 1
        print(f"   v {rel} ({size // 1024} KB)")
        return self.manifest["files"][key]["path"]

    def _backfill_uploaded(self, entry: dict) -> None:
        """올린 시각을 모르는 예전에 받은 파일 — 본문 없이 머리(HEAD)만 한 번 물어 Last-Modified 를 적는다(파일마다 한 번)."""
        try:
            entry["uploaded_at"] = uploaded_at(self.c.head(entry["url"]))
        except Exception as e:
            self._soft(f"{Path(entry['path']).name} 올린 시각", e)
            return
        self.save_manifest()
        self.stats["uploaded_backfill"] += 1

    # -- 자료 활동 -------------------------------------------------------
    def collect_files(self, course: dict, act: dict):
        try:
            urls = file_urls_for(self.c, act)
        except Exception as e:
            self._soft(act["name"], e)
            return
        cdir = C.DATA_DIR / sanitize(course["name"]) / sanitize(act["name"])
        meta = {"course_id": course["id"], "course": course["name"], "cmid": act["cmid"], "activity": act["name"]}
        for u in urls:
            self.fetch_file(u, cdir / filename_of(u), meta)

    # -- 게시판 ---------------------------------------------------------
    def collect_board(self, course: dict, act: dict):
        soup = self.c.page(act["url"])
        if soup is None:
            return
        rows = [tr for tr in soup.select("table tr") if tr.select_one('a[href*="article.php"]')]
        bdir = C.DATA_DIR / sanitize(course["name"]) / "게시판" / sanitize(act["name"])
        for tr in rows[: C.BOARD_MAX_POSTS]:
            a = tr.select_one('a[href*="article.php"]')
            href = urljoin(C.BASE_URL, a["href"])
            bwid = parse_qs(urlparse(href).query).get("bwid", [""])[0]
            cells = [text_of(td) for td in tr.select("td")]
            title = text_of(a) or f"post_{bwid}"
            posted = next((x for x in cells if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x)), "")
            key = f"{act['cmid']}:{bwid}"
            entry = self.manifest["posts"].get(key)
            if entry and abs_path(entry["path"]).exists():
                self.stats["post_exists"] += 1
                continue
            if self.dry:
                print(f"   + [글] {act['name']} / {posted} {title}")
                self.stats["post_planned"] += 1
                continue
            asoup = self.c.page(href)
            if asoup is None:
                continue
            post = self.parse_article(asoup)
            md_path = bdir / f"{posted or 'nodate'}_{sanitize(title, 60)}.md"
            meta = {"course_id": course["id"], "course": course["name"], "cmid": act["cmid"],
                    "activity": act["name"], "post": title}
            attached = [p for u in post["attachments"] if (p := self.fetch_file(u, bdir / filename_of(u), meta))]
            lines = [f"# {post['title'] or title}", "",
                     f"- 과목: {course['name']}", f"- 게시판: {act['name']}",
                     f"- 작성자: {post['writer']}", f"- 작성일: {post['date'] or posted}", f"- 링크: {href}", ""]
            if attached:
                lines += ["## 첨부", *[f"- {Path(p).name}  (`{p}`)" for p in attached], ""]
            lines += ["## 본문", "", post["body"], ""]
            md_path.parent.mkdir(parents=True, exist_ok=True)
            md_path.write_text("\n".join(lines), encoding="utf-8")
            self.manifest["posts"][key] = {
                "url": href, "path": rel_path(md_path), "title": title, "date": post["date"] or posted,
                "attachments": attached, "fetched_at": datetime.now().isoformat(timespec="seconds"), **meta,
            }
            self.save_manifest()
            self.stats["post_saved"] += 1
            print(f"   v [글] {md_path.relative_to(C.DATA_DIR)}")

    @staticmethod
    def parse_article(soup) -> dict:
        view = soup.select_one(".ubboard_view") or soup

        def info(cls: str) -> str:
            el = view.select_one(f".info .{cls}")
            if el is None:
                return ""
            label = el.select_one("span.title")
            if label is not None:
                label.extract()
            return text_of(el)

        content = view.select_one(".content")
        return {
            "title": text_of(view.select_one(".subject h3") or view.select_one(".subject")),
            "writer": info("writer"),
            "date": info("date"),
            "body": content.get_text("\n", strip=True) if content else "",
            "attachments": extract_pluginfiles(view),
        }

    # -- 과제 -----------------------------------------------------------
    def collect_assignment(self, course: dict, act: dict):
        soup = self.c.page(act["url"])
        if soup is None:
            return
        intro = soup.select_one("#intro")
        status = parse_assignment_status(soup)
        adir = C.DATA_DIR / sanitize(course["name"]) / "과제"
        meta = {"course_id": course["id"], "course": course["name"], "cmid": act["cmid"], "activity": act["name"]}
        attached = []
        if intro is not None:
            attached = [p for u in extract_pluginfiles(intro) if (p := self.fetch_file(u, adir / filename_of(u), meta))]
        info = {
            "course_id": course["id"], "course": course["name"], "cmid": act["cmid"],
            "name": act["name"], "url": act["url"],
            "due": parse_kdate(status.get("종료 일시", ""), date.today()) if status.get("종료 일시") else "",
            "remaining": status.get("마감까지 남은 기한", ""),
            "submitted": status.get("제출 여부", ""), "graded": status.get("채점 상황", ""),
            "status": status, "description": intro.get_text("\n", strip=True) if intro else "",
            "attachments": attached, "fetched_at": datetime.now().isoformat(timespec="seconds"),
        }
        self.assignments.append(info)
        self.stats["assign"] += 1
        print(f"   * [과제] {act['name']} — 마감 {info['due'] or '?'} / {info['submitted'] or '?'}")
        if self.dry:
            return
        lines = [f"# {act['name']}", "", f"- 과목: {course['name']}",
                 f"- 마감: {info['due'] or '?'}  (남은 기한: {info['remaining'] or '?'})",
                 f"- 제출 여부: {info['submitted'] or '?'} / 채점: {info['graded'] or '?'}",
                 f"- 링크: {act['url']}", f"- 확인 시각: {info['fetched_at']}", ""]
        if attached:
            lines += ["## 첨부", *[f"- {Path(p).name}  (`{p}`)" for p in attached], ""]
        lines += ["## 설명", "", info["description"] or "(없음)", ""]
        adir.mkdir(parents=True, exist_ok=True)
        (adir / f"{sanitize(act['name'])}.md").write_text("\n".join(lines), encoding="utf-8")

    # -- 퀴즈 (마감 일시만, F6-R07 · 미결 Q1) ------------------------------
    def collect_quiz(self, course: dict, act: dict):
        """퀴즈 첫 화면에서 종료 일시만 읽는다. 캘린더 '다가오는 일정'이 빠뜨리는 퀴즈(기간이 먼 것·캘린더 비공개)도 잡는다."""
        try:
            soup = self.c.page(act["url"])
        except Exception as e:
            self._soft(act["name"], e)
            return
        if soup is None:
            return
        due = quiz_close(soup, date.today())
        self.quizzes.append({"course_id": course["id"], "course": course["name"], "cmid": act["cmid"],
                             "name": act["name"], "url": act["url"], "due": due})
        self.stats["quiz"] += 1
        print(f"   * [퀴즈] {act['name']} — 마감 {due or '?'}")

    # -- 동영상 (출석인정 마감 + 시청 여부) ---------------------------------
    def collect_videos(self, course: dict, acts: list[dict]):
        """동영상의 출석인정 마감(과목 화면에서 이미 읽음)과 시청 여부(진도 현황 한 번)를 모은다. 재생 화면은 열지 않는다.
        마감은 기간 전체가 아니라 **출석인정 기간의 끝**만 쓴다(사용자 요청 2026-10-02)."""
        vods = [a for a in acts if a["mod"] in C.VIDEO_MODULES]
        if not vods:
            return
        progress: dict[str, dict] = {}
        try:
            soup = self.c.page(C.VOD_PROGRESS_URL.format(course_id=course["id"]))
            if soup is not None:
                progress = parse_vod_progress(soup)
        except Exception as e:
            self._soft(f"{course['name']} 진도 현황", e)
        for a in vods:
            p = progress.get(a["name"])
            if p:
                status = "시청 완료" if p["watched"] else f"미시청 · 진도율 {p['progress']:g}%"
                desc = f"출석인정 요구시간 {p['required']} / 콘텐츠 길이 {p['length']} · 진도율 {p['progress']:g}%"
            else:
                status = "미시청" if progress else ""
                desc = f"콘텐츠 길이 {a.get('length') or '?'}" + ("" if progress else " · 진도 현황을 읽지 못했습니다")
            if a.get("vodStart"):
                desc += f"\n출석인정 기간 {a['vodStart']} ~ {a['vodEnd']} (마감만 캘린더에 올린다)"
            self.videos.append({"course_id": course["id"], "course": course["name"], "cmid": a["cmid"], "name": a["name"],
                                "url": a["url"], "due": a.get("vodEnd", ""), "status": status, "description": desc})
            self.stats["vod"] += 1
            print(f"   * [동영상] {a['name']} — 출석인정 마감 {a.get('vodEnd') or '?'} / {status or '?'}")

    # -- 캘린더 ---------------------------------------------------------
    def collect_calendar(self) -> list[dict]:
        soup = self.c.page(C.CALENDAR_URL)
        if soup is None:
            return []
        events = parse_calendar(soup, date.today())
        self.stats["calendar_events"] = len(events)
        return events

    # -- 마감 일정 통합 --------------------------------------------------
    def write_deadlines(self, events: list[dict]):
        items = merge_deadlines(events, self.assignments, self.quizzes, self.courses_index, self.videos)
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_json(C.DEADLINES_FILE, {"updated_at": now, "items": items})
        lines = [f"# 마감 일정  (갱신: {now})", "", "| 마감 | 과목 | 종류 | 항목 | 상태 |", "|---|---|---|---|---|"]
        for i in items:
            flag = "(지남) " if i["due"] < now else ""
            lines.append(f"| {flag}{i['due']} | {i['course']} | {i['type']} | [{i['name']}]({i['url']}) | {i['status']} |")
        (C.DATA_DIR / "deadlines.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return items


def resolve_course(name: str, courses: list[dict]) -> dict | None:
    """캘린더가 적은 과목 이름 → 과목. 캘린더는 '소프트웨어공학론' 처럼 분반·학수번호를 떼고 적는다(2026-09-30 실측)."""
    name = (name or "").strip()
    if not name:
        return None
    for c in courses:
        if c.get("name") == name:
            return c
    short = [c for c in courses if re.sub(r"\s*\[\d+\]\s*\([A-Za-z0-9]+\)\s*$", "", c.get("name", "")).strip() == name]
    return short[0] if len(short) == 1 else None


def merge_deadlines(events: list[dict], assignments: list[dict], quizzes: list[dict], courses: list[dict],
                    videos: list[dict] | None = None) -> list[dict]:
    """캘린더 일정 + 과제 + 퀴즈 + 동영상 → 마감 목록. 같은 활동(cmid)은 한 줄 — 과제 화면의 마감·상태가 캘린더보다 우선하고,
    동영상은 과목 화면의 출석인정 마감이 캘린더(시청 기간 전체)보다 우선한다."""
    by_url = {a["url"]: a for a in assignments}
    items = []
    for v in videos or []:
        if v["due"]:
            items.append({"due": v["due"], "start": "", "course": v["course"], "course_id": v["course_id"], "type": "동영상",
                          "name": v["name"], "url": v["url"], "cmid": v["cmid"], "status": v["status"], "source": "vod",
                          "description": v.get("description", "")})
    vod_urls = {i["url"] for i in items}
    for e in events:
        if e["url"] in vod_urls:
            continue
        a = by_url.get(e["url"])
        c = resolve_course(e["course"], courses)
        items.append({"due": (a or {}).get("due") or e["end"], "start": e["start"],
                      "course": (a or {}).get("course") or (c or {}).get("name") or e["course"],
                      "course_id": (a or {}).get("course_id") or (c or {}).get("id", ""),
                      "type": e["type"], "name": e["name"], "url": e["url"], "cmid": e.get("cmid") or cmid_of(e["url"]),
                      "status": a["submitted"] if a else "", "source": "calendar"})
    seen = {i["url"] for i in items}
    for a in assignments:
        if a["url"] in seen or not a["due"]:
            continue
        items.append({"due": a["due"], "start": "", "course": a["course"], "course_id": a["course_id"], "type": "과제",
                      "name": a["name"], "url": a["url"], "cmid": a["cmid"], "status": a["submitted"], "source": "assign"})
        seen.add(a["url"])
    for q in quizzes:
        if q["url"] in seen or not q["due"]:
            continue
        items.append({"due": q["due"], "start": "", "course": q["course"], "course_id": q["course_id"], "type": "퀴즈",
                      "name": q["name"], "url": q["url"], "cmid": q["cmid"], "status": "", "source": "quiz"})
        seen.add(q["url"])
    items.sort(key=lambda i: i["due"])
    return items


# ---------------------------------------------------------------- 실행

@dataclass
class Result:
    code: int
    counts: dict = field(default_factory=dict)
    error: str | None = None
    full: bool = False              # 전체 과목·과제·마감을 봤다 → 원장이 '사라진 과제'를 판정해도 된다 (F6-R23)


def _c3_login():
    """C3_Login_agent 의 login 패키지 (세션 파일 · reauthenticate · session_ok)."""
    if not (C.C3_AGENT_DIR / "login" / "__init__.py").exists():
        raise RuntimeError(f"C3_Login_agent 가 없습니다: {C.C3_AGENT_DIR}")
    if str(C.C3_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C3_AGENT_DIR))
    import login                    # type: ignore[import-not-found]
    return login


def _probe(p) -> None:
    """e클래스에 닿는지 먼저 본다 — 인터넷이 없을 때 '세션 만료'로 잘못 알리지 않게."""
    req = p.request.new_context(user_agent=C.USER_AGENT, timeout=20_000)
    try:
        req.get(C.BASE_URL, max_redirects=0)
    except Exception as e:
        raise NetworkError(str(e)[:200]) from e
    finally:
        req.dispose()


def run(dry_run: bool = False, courses_only: list[str] | None = None, only: set[str] | None = None) -> Result:
    """수집 한 번. 잠금·기록은 runner 몫이고 여기서는 결과(code·건수)만 돌려준다."""
    only = set(only or ALL_PARTS)
    login = _c3_login()
    login.config.use_browsers()     # C3 의 Chromium — Playwright 드라이버가 뜨기 전에 정해야 자식 프로세스가 물려받는다
    from playwright.sync_api import sync_playwright

    if not login.STATE_FILE.exists() and not login.CRED_FILE.exists():
        print("학교 로그인 기록이 없습니다. C3_Login_agent 의 login.cmd(또는 화면의 '로그인 창 열기')를 먼저 실행하세요.")
        return Result(C.EXIT_LOGIN, error="로그인 기록 없음")
    C.ensure_dirs()
    s = None
    c = None
    try:
        with sync_playwright() as p:
            _probe(p)

            def new_req():
                kw = {"user_agent": C.USER_AGENT, "timeout": 60_000}
                if login.STATE_FILE.exists():
                    kw["storage_state"] = str(login.STATE_FILE)
                return p.request.new_context(**kw)

            req = new_req()
            if not login.session_ok(req):
                req.dispose()
                print("e클래스 세션 만료 → 재인증 시도 (C3_Login_agent)...")
                if not login.reauthenticate(p):
                    _probe(p)        # 재인증 도중 네트워크가 끊긴 것이면 로그인 문제로 알리지 않는다
                    print("자동 재인증 실패. '로그인 창 열기'(C3_Login_agent\\login.cmd)로 한 번 로그인하세요.")
                    return Result(C.EXIT_LOGIN, error="세션 만료 — 자동 재인증 실패 (로그인 필요)")
                req = new_req()
            c = Client(req)
            s = Sync(c, load_manifest(), dry_run)

            courses = find_courses(c)
            if not courses:
                print("과목을 찾지 못했습니다. config.COURSE_LIST_URLS 를 확인하세요 (e클래스 화면 구조가 바뀌었을 수 있습니다).")
                return Result(C.EXIT_ERROR, error="과목 목록을 찾지 못했습니다 — 화면 구조 변경 의심")
            if courses_only:
                courses = [x for x in courses if x["id"] in courses_only]

            for course in courses:
                print(f"\n== [{course['id']}] {course['name']}")
                acts = find_activities(c, course)
                counts = Counter(a["mod"] for a in acts.values())
                print("   활동:", ", ".join(f"{k}x{v}" for k, v in counts.most_common()) or "없음")
                s.courses_index.append({**course, "activities": list(acts.values())})
                for act in acts.values():
                    mod = act["mod"]
                    if mod in C.RESOURCE_MODULES and "files" in only:
                        s.collect_files(course, act)
                    elif mod == "ubboard" and "boards" in only:
                        if any(k in act["name"] for k in C.BOARD_INCLUDE):
                            try:
                                s.collect_board(course, act)
                            except Exception as e:
                                s._soft(act["name"], e)
                        else:
                            s.stats["board_excluded"] += 1
                    elif mod == "assign" and "assign" in only:
                        try:
                            s.collect_assignment(course, act)
                        except Exception as e:
                            s._soft(act["name"], e)
                    elif mod == "quiz" and "assign" in only:
                        s.collect_quiz(course, act)
                if "assign" in only:
                    s.collect_videos(course, list(acts.values()))

            events =s.collect_calendar() if "deadlines" in only else []
            if not courses_only:
                save_json(C.COURSES_FILE, s.courses_index)
            # 메타데이터 JSON 은 --dry-run 에서도 갱신한다 (파일·글만 안 받는다). 과목을 골라 돌렸으면 전체 목록을 덮어쓰지 않는다.
            items = []
            if "assign" in only and not courses_only:
                save_json(C.ASSIGNMENTS_FILE, s.assignments)
            if "deadlines" in only and not courses_only:
                items = s.write_deadlines(events)
                print(f"\n== 마감 일정 {len(items)}건 -> data/deadlines.md")
                for i in items[:10]:
                    print(f"   {i['due']}  {i['course'][:18]:18s} {i['type']:6s} {i['name'][:40]}  {i['status']}")
            req.dispose()
    except SessionExpired:
        print("\n수집 도중 세션이 만료되었습니다. 다음 실행에서 자동 재인증을 시도합니다.")
        return Result(C.EXIT_LOGIN, _counts(s, c), error="수집 도중 세션 만료")
    except Exception as e:                                  # noqa: BLE001
        if is_network_error(e):
            print(f"\n네트워크 오류: {str(e)[:200]}")
            return Result(C.EXIT_NETWORK, _counts(s, c), error=f"네트워크 오류 — {str(e)[:120]}")
        raise

    counts = _counts(s, c)
    counts["deadlines"] = len(items)
    print("\n완료:", ", ".join(f"{k}={v}" for k, v in sorted(s.stats.items())) or "변경 없음", f"(요청 {c.requests}회)")
    full = not courses_only and {"assign", "deadlines"} <= only
    return Result(C.EXIT_OK, counts, full=full)


def _counts(s: Sync | None, c: Client | None) -> dict:
    if s is None:
        return {}
    return {"courses": len(s.courses_index), "assignments": len(s.assignments), "quizzes": len(s.quizzes),
            "videos": len(s.videos),
            "files": s.stats.get("downloaded", 0), "posts": s.stats.get("post_saved", 0),
            "errors": s.stats.get("error", 0), "requests": c.requests if c else 0}
