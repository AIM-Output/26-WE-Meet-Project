"""저장된 세션으로 본인 수강 과목의 자료·공지·과제·마감 일정을 모은다.

- 브라우저를 띄우지 않고 HTTP 요청만 사용 (서버 부하 최소화)
- 요청 간격 config.REQUEST_INTERVAL, 동시성 1
- 다운로드 전에 확장자를 검사해 동영상 등은 요청 자체를 하지 않음
- 동영상(vod)은 제목·링크만 기록, 학생 글이 올라오는 게시판은 건드리지 않음
- 세션이 만료되면 즉시 중단하고 login 재실행을 안내

결과물 (data/ 아래):
  <과목>/<활동>/<파일>              강의자료 파일
  <과목>/게시판/<게시판>/<날짜>_<제목>.md   공지·자료실 글 (+첨부)
  <과목>/과제/<과제>.md              과제 설명·첨부·마감·제출상태
  deadlines.md / deadlines.json     마감 일정 (캘린더 + 과제, 날짜순)
  assignments.json                  과제 전체
  courses.json                      과목·활동 목록 (동영상 제목 포함)
  manifest.json                     내려받은 파일·글 목록

중복 실행 방지: 도는 동안 state/sync.lock (pid) 을 잡는다. 예약 작업·대시보드 버튼·수동 실행이 겹치면
뒤의 것이 exit 3 으로 물러난다. 끝나면 state/sync.last.json 에 결과(exit_code)를 남긴다 — 대시보드가 읽는다.
종료 코드: 0 성공 · 1 설정/세션 파일 오류 · 2 세션 만료(재인증 실패) · 3 다른 실행이 진행 중

사용:
    python sync.py --dry-run            # 내려받지 않고 목록만 (메타데이터 JSON은 갱신)
    python sync.py                      # 전체
    python sync.py --course 12345       # 특정 과목만 (여러 번 지정 가능)
    python sync.py --only deadlines     # files,boards,assign,deadlines 중 골라서
    python sync.py --log state/sync.log # 출력을 그 파일에 덧붙인다 (run-sync.cmd 가 이렇게 부른다)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

import config as C
from login import reauthenticate, session_ok

MOD_RE = re.compile(r"/mod/([a-z0-9_]+)/view\.php\?id=(\d+)")
UNSAFE_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')
KDATE = re.compile(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일(?:\s*\([^)]*\))?\s*,?\s*(\d{1,2}):(\d{2})")
RELDATE = re.compile(r"(오늘|내일|모레|어제)\s*,?\s*(\d{1,2}):(\d{2})")
REL_DAYS = {"오늘": 0, "내일": 1, "모레": 2, "어제": -1}
ALL_PARTS = ("files", "boards", "assign", "deadlines")


class SessionExpired(Exception):
    pass


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


def parse_kdate(text: str, today: date) -> str:
    """'2026년 9월 15일(화요일), 23:59' / '내일, 23:59' → 'YYYY-MM-DD HH:MM'. 못 읽으면 원문."""
    m = KDATE.search(text)
    if m:
        y, mo, d, h, mi = map(int, m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d} {h:02d}:{mi:02d}"
    m = RELDATE.search(text)
    if m:
        d = today + timedelta(days=REL_DAYS[m.group(1)])
        return f"{d.isoformat()} {int(m.group(2)):02d}:{m.group(3)}"
    return text.strip()


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
        name = text_of(a)
        cur = acts.get(cmid)
        if cur is None or len(name) > len(cur["name"]):
            acts[cmid] = {"mod": mod, "cmid": cmid, "name": name or f"{mod}_{cmid}",
                          "url": f"{C.BASE_URL}/mod/{mod}/view.php?id={cmid}"}
    return acts


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
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def download(c: Client, url: str, dest: Path) -> int:
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
    return len(body)


class Sync:
    def __init__(self, c: Client, manifest: dict, dry: bool):
        self.c = c
        self.manifest = manifest
        self.dry = dry
        self.stats: Counter = Counter()
        self.assignments: list[dict] = []
        self.courses_index: list[dict] = []

    def save_manifest(self):
        save_json(C.MANIFEST_FILE, self.manifest)

    # -- 파일 하나 ------------------------------------------------------
    def fetch_file(self, url: str, dest: Path, meta: dict) -> str | None:
        """허용 확장자면 내려받고 data/ 기준 상대경로를 돌려준다. 이미 있으면 그 경로."""
        if ext_of(url) not in C.ALLOWED_EXT:
            self.stats["skip_ext"] += 1
            return None
        key = file_key(url)
        entry = self.manifest["files"].get(key)
        if entry and (C.ROOT / entry["path"]).exists():
            self.stats["exists"] += 1
            return entry["path"]
        rel = dest.relative_to(C.DATA_DIR)
        if self.dry:
            print(f"   + {rel}")
            self.stats["planned"] += 1
            return None
        try:
            size = download(self.c, url, dest)
        except SessionExpired:
            raise
        except Exception as e:
            print(f"   ! {dest.name}: {e}")
            self.stats["error"] += 1
            return None
        self.manifest["files"][key] = {
            "url": url, "path": str(dest.relative_to(C.ROOT)), "size": size,
            "downloaded_at": datetime.now().isoformat(timespec="seconds"), **meta,
        }
        self.save_manifest()
        self.stats["downloaded"] += 1
        print(f"   v {rel} ({size // 1024} KB)")
        return self.manifest["files"][key]["path"]

    # -- 자료 활동 -------------------------------------------------------
    def collect_files(self, course: dict, act: dict):
        try:
            urls = file_urls_for(self.c, act)
        except SessionExpired:
            raise
        except Exception as e:
            print(f"   ! {act['name']}: {e}")
            self.stats["error"] += 1
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
            if entry and (C.ROOT / entry["path"]).exists():
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
                "url": href, "path": str(md_path.relative_to(C.ROOT)), "title": title, "date": post["date"] or posted,
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
        status: dict[str, str] = {}
        for tr in soup.select("table.generaltable tr"):
            cells = tr.select("th, td")
            if len(cells) >= 2:
                k, v = text_of(cells[0]), text_of(cells[1])
                if k and "___" not in v:          # 템플릿 잔여물 제외
                    status[k] = v
        adir = C.DATA_DIR / sanitize(course["name"]) / "과제"
        meta = {"course_id": course["id"], "course": course["name"], "cmid": act["cmid"], "activity": act["name"]}
        attached = []
        if intro is not None:
            attached = [p for u in extract_pluginfiles(intro) if (p := self.fetch_file(u, adir / filename_of(u), meta))]
        info = {
            "course_id": course["id"], "course": course["name"], "cmid": act["cmid"],
            "name": act["name"], "url": act["url"],
            "due": status.get("종료 일시", ""), "remaining": status.get("마감까지 남은 기한", ""),
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

    # -- 캘린더 ---------------------------------------------------------
    def collect_calendar(self) -> list[dict]:
        soup = self.c.page(C.CALENDAR_URL)
        if soup is None:
            return []
        today = date.today()
        events: list[dict] = []
        for div in soup.select("div.event"):
            a = div.select_one("h3.referer a") or div.select_one("h3 a")
            if a is None:
                continue
            icon = div.select_one("img.icon")
            parts = [x.strip() for x in text_of(div.select_one(".date")).split("»")]
            ev = {
                "name": text_of(a), "url": urljoin(C.BASE_URL, a.get("href", "")),
                "type": icon.get("title", "") if icon is not None else "",
                "course": text_of(div.select_one(".course a")),
                "start": parse_kdate(parts[0], today) if len(parts) > 1 else "",
                "end": parse_kdate(parts[-1], today),
            }
            if ev not in events:
                events.append(ev)
        self.stats["calendar_events"] = len(events)
        return events

    # -- 마감 일정 통합 --------------------------------------------------
    def write_deadlines(self, events: list[dict]):
        by_url = {a["url"]: a for a in self.assignments}
        items = []
        for e in events:
            a = by_url.get(e["url"])
            items.append({"due": e["end"], "start": e["start"], "course": e["course"], "type": e["type"],
                          "name": e["name"], "url": e["url"], "status": a["submitted"] if a else "", "source": "calendar"})
        seen = {i["url"] for i in items}
        for a in self.assignments:
            if a["url"] in seen or not a["due"]:
                continue
            items.append({"due": a["due"], "start": "", "course": a["course"], "type": "과제",
                          "name": a["name"], "url": a["url"], "status": a["submitted"], "source": "assign"})
        items.sort(key=lambda i: i["due"])
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        save_json(C.DATA_DIR / "deadlines.json", {"updated_at": now, "items": items})
        lines = [f"# 마감 일정  (갱신: {now})", "", "| 마감 | 과목 | 종류 | 항목 | 상태 |", "|---|---|---|---|---|"]
        for i in items:
            flag = "(지남) " if i["due"] < now else ""
            lines.append(f"| {flag}{i['due']} | {i['course']} | {i['type']} | [{i['name']}]({i['url']}) | {i['status']} |")
        (C.DATA_DIR / "deadlines.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return items


# ---------------------------------------------------------------- 중복 실행 방지 (잠금 파일)
#
# 예약 작업(run-sync.cmd)·대시보드 버튼·수동 실행이 전부 이 스크립트를 지나므로 여기서 막는다.
# state/sync.lock 에 pid 를 적어 두고, 그 pid 가 살아 있으면 새 실행은 exit 3 으로 물러난다.
# 프로세스가 죽고 남은 잠금은 치우고 진행한다.

def pid_alive(pid: int) -> bool:
    """pid 가 살아 있는 python 프로세스인가. Windows 는 tasklist 로 본다 (os.kill 은 Windows 에서 프로세스를 죽인다)."""
    if sys.platform == "win32":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                             capture_output=True, text=True, errors="replace").stdout
        return f'"{pid}"' in out and "python" in out.lower()
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def redirect_output(path: str) -> None:
    """stdout/stderr(fd 1·2)를 path 에 덧붙인다. 파이썬이 열면 공유 모드라 여러 실행이 같은 로그를 써도 되지만
    (cmd 의 >> 는 두 번째 실행이 열지 못하고 죽는다), fd 를 바꾸므로 Playwright 드라이버 같은 자식 출력도 들어간다."""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    sys.stdout = open(1, "w", encoding="utf-8", buffering=1, closefd=False)   # 줄 단위 flush → 진행 상황이 바로 보인다
    sys.stderr = open(2, "w", encoding="utf-8", buffering=1, closefd=False)


def read_lock() -> tuple[dict, float]:
    """잠금 내용과 나이(초). 파일이 없으면 ({}, 0), 있는데 못 읽으면 ({}, 나이)."""
    try:
        age = time.time() - C.LOCK_FILE.stat().st_mtime
    except OSError:
        return {}, 0.0
    try:
        info = json.loads(C.LOCK_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        info = {}
    return (info if isinstance(info, dict) else {}), age


def acquire_lock() -> bool:
    """state/sync.lock 을 원자적으로(O_EXCL) 만든다. 살아 있는 실행이 잡고 있으면 False."""
    C.LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(C.LOCK_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            info, age = read_lock()
            pid = info.get("pid")
            if isinstance(pid, int) and pid_alive(pid):
                print(f"이미 실행 중입니다 (pid {pid}, {info.get('started_at', '?')} 시작) — 이번 실행은 건너뜁니다.")
                return False
            if not info and age < 30:
                time.sleep(1)          # 다른 실행이 막 만드는 중이거나 방금 사라진 것 → 잠깐 뒤 다시
                continue
            print(f"남아 있던 잠금 파일 정리 (pid {pid or '?'} 는 이미 종료)")
            C.LOCK_FILE.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started_at": datetime.now().isoformat(timespec="seconds"),
                       "args": sys.argv[1:]}, f, ensure_ascii=False)
        return True
    print(f"잠금 파일을 잡지 못했습니다 ({C.LOCK_FILE}) — 이번 실행은 건너뜁니다.")
    return False


def release_lock(exit_code: int) -> None:
    """내 잠금을 풀고 결과를 state/sync.last.json 에 남긴다 (대시보드가 예약 실행의 결과도 볼 수 있게)."""
    info, _ = read_lock()
    if info.get("pid") != os.getpid():      # 내 것이 아니면 건드리지 않는다
        return
    save_json(C.LAST_RUN_FILE, {**info, "finished_at": datetime.now().isoformat(timespec="seconds"),
                                "exit_code": exit_code})
    C.LOCK_FILE.unlink(missing_ok=True)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="파일·글은 내려받지 않고 목록만 (메타데이터 JSON 은 갱신)")
    ap.add_argument("--course", action="append", metavar="ID", help="특정 과목 id만 (여러 번 지정 가능)")
    ap.add_argument("--only", metavar="PARTS", help="쉼표 구분: " + ",".join(ALL_PARTS))
    ap.add_argument("--log", metavar="FILE", help="출력을 이 파일에 덧붙인다 (실행마다 ======== 시각 ======== 머리줄)")
    args = ap.parse_args()
    only = set(args.only.split(",")) if args.only else set(ALL_PARTS)
    if bad := only - set(ALL_PARTS):
        print("--only 값 오류:", ", ".join(sorted(bad)))
        return 1
    if args.log:
        redirect_output(args.log)
        print(f"======== {datetime.now():%Y-%m-%d %H:%M:%S} ========")

    if not acquire_lock():
        return 3
    code = 1                                 # run() 이 예외로 죽으면 1 로 기록된다
    try:
        code = run(args, only)
    finally:
        release_lock(code)
    return code


def run(args, only: set[str]) -> int:
    if not C.STATE_FILE.exists():
        print("세션 파일이 없습니다. 먼저 login 을 실행하세요.")
        return 1

    def new_req(p):
        return p.request.new_context(storage_state=str(C.STATE_FILE), user_agent=C.USER_AGENT, timeout=60_000)

    try:
        with sync_playwright() as p:
            req = new_req(p)
            if not session_ok(req):
                req.dispose()
                print("e클래스 세션 만료 → 재인증 시도...")
                if not reauthenticate(p):
                    print("자동 재인증 실패. `login.cmd` (수동) 또는 `setup-creds.cmd`(무인 저장) 를 실행하세요.")
                    return 2
                req = new_req(p)
            c = Client(req)
            s = Sync(c, load_manifest(), args.dry_run)

            courses = find_courses(c)
            if not courses:
                print("과목을 찾지 못했습니다. config.COURSE_LIST_URLS 를 확인하세요.")
                return 1
            if args.course:
                courses = [x for x in courses if x["id"] in args.course]

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
                            s.collect_board(course, act)
                        else:
                            s.stats["board_excluded"] += 1
                    elif mod == "assign" and "assign" in only:
                        s.collect_assignment(course, act)

            events = s.collect_calendar() if "deadlines" in only else []
            save_json(C.DATA_DIR / "courses.json", s.courses_index)
            if "assign" in only:
                save_json(C.DATA_DIR / "assignments.json", s.assignments)
            if "deadlines" in only:
                items = s.write_deadlines(events)
                print(f"\n== 마감 일정 {len(items)}건 -> data/deadlines.md")
                for i in items[:10]:
                    print(f"   {i['due']}  {i['course'][:18]:18s} {i['type']:6s} {i['name'][:40]}  {i['status']}")
            req.dispose()
    except SessionExpired:
        print("\n세션이 만료되었습니다. login 을 다시 실행한 뒤 재시도하세요.")
        return 2

    print("\n완료:", ", ".join(f"{k}={v}" for k, v in sorted(s.stats.items())) or "변경 없음", f"(요청 {c.requests}회)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
