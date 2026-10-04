"""수집 한 번 — 원천마다 받기 → 추출 → 등록, 결과를 sources 표에 기록 (F1-R01~R06).

- 원천은 서로 독립이다. 하나가 실패해도 나머지는 진행하고, 실패한 원천만 빨갛게 보인다 (F1-S12, 9절).
- 중복 실행 방지: 도는 동안 state/sync.lock(pid). 대시보드 버튼·예약 작업·수동 실행이 겹치면 뒤의 것이 exit 3.
- 끝나면 state/sync.last.json 에 결과를 남긴다 (대시보드가 예약 실행의 결과도 볼 수 있게).
- DB 트랜잭션은 원천·글 단위로 짧게 잡는다 — 수집 중에도 대시보드가 읽고 쓸 수 있어야 한다.

원천 4곳: ① 학교 학사일정 표 ② 학교 공지 › 학사안내 ③ 내 단과대학 공지 ④ 내 학부 공지 (③·④ 는 프로필 소속으로 찾는다)
종료 코드: 0 전부 성공 · 1 일부 원천 실패 · 3 다른 실행이 진행 중 · 4 전부 실패
(프로필에 소속이 없어 ③·④ 를 건너뛴 것은 실패로 세지 않는다)
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
from datetime import date, datetime, timedelta
from typing import Optional

from . import config as C
from . import extract, homepages, llm, store
from .profile import load_local_profile
from .register import add_notification, register, retire_source_items, snapshot_window
from .sources import BOARD_KINDS, calendar_table, k2web_discover
from .sources.base import FormatChanged, Http, NeedsProfile, NotListed, SourceError
from .textutil import parse_board_url, short_hash


# ── 잠금 (F6_Eclass_agent/eclass/runs.py 와 같은 방식) ─────────────────

pid_alive = C.pid_alive          # C0 osenv (Windows tasklist · 그 외 os.kill)


def read_lock() -> dict:
    try:
        info = json.loads(C.LOCK_FILE.read_text(encoding="utf-8"))
        return info if isinstance(info, dict) else {}
    except (OSError, ValueError):
        return {}


def acquire_lock(args: list[str], by: str = "manual") -> bool:
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(C.LOCK_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            info = read_lock()
            pid = info.get("pid")
            if isinstance(pid, int) and pid_alive(pid):
                print(f"이미 수집 중입니다 (pid {pid}, {info.get('started_at', '?')} 시작) — 이번 실행은 건너뜁니다.")
                return False
            if not info:
                time.sleep(1)
            C.LOCK_FILE.unlink(missing_ok=True)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump({"pid": os.getpid(), "started_at": datetime.now().isoformat(timespec="seconds"), "args": args,
                       "by": by}, f)
        return True
    return False


def release_lock(exit_code: int, results: dict) -> None:
    info = read_lock()
    if info.get("pid") != os.getpid():
        return
    C.LAST_RUN_FILE.write_text(json.dumps({**info, "finished_at": datetime.now().isoformat(timespec="seconds"),
                                           "exit_code": exit_code, "sources": results}, ensure_ascii=False, indent=1),
                               encoding="utf-8")
    C.LOCK_FILE.unlink(missing_ok=True)


# ── 원천별 수집 ─────────────────────────────────────────────

def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        return ""
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((p.extract_text() or "") for p in reader.pages[:20])
    except Exception:
        return ""


def run_table(cfg: dict, http: Http, dry_run: bool) -> dict:
    rows, meta = calendar_table.fetch(cfg, http)
    cands = extract.from_table(rows, cfg)
    print(f"  표 {meta['rows']}행 → 가져온 일정 {len(cands)}건 (최근 {C.TABLE_KEEP_MONTHS}개월부터)")
    if dry_run:
        for c in cands[:15]:
            print(f"    {c.start} {c.end or '':10} {c.type:12} {c.title}")
        return {"count": len(cands)}
    with store.connect() as con:
        stats = register(con, cfg["key"], cands, snapshot_since=snapshot_window())
        store.touch(con)
    return {"count": len(cands), **stats}


def run_board(cfg: dict, http: Http, dry_run: bool, pages: int) -> dict:
    mod = BOARD_KINDS[cfg["kind"]]
    posts = mod.list_posts(cfg, http, pages)
    picked = mod.select(posts, cfg) if cfg["kind"] == "k2web" else mod.select(posts)
    print(f"  글 {len(posts)}건 중 학사 글 {len(picked)}건")
    recent_cut = (date.today() - timedelta(days=C.RECHECK_DAYS)).isoformat()
    stats = {"count": 0, "new": 0, "changed": 0, "same": 0, "removed": 0, "posts": 0, "skipped": 0}
    rechecks = 0
    for p in picked:
        with store.connect() as con:
            known = con.execute("SELECT * FROM posts WHERE source_key = ? AND post_id = ?",
                                (cfg["key"], p.post_id)).fetchone()
        outdated = known is not None and known["version"] != C.EXTRACT_VERSION     # 추출 규칙이 바뀜 → 다시 읽는다
        if known and not outdated:
            recent = (known["posted_at"] or p.posted_at or "") >= recent_cut
            if not recent or rechecks >= C.RECHECK_MAX:
                stats["skipped"] += 1
                continue
            rechecks += 1
        mod.fetch_detail(p, http)
        h = short_hash(p.title, p.body, *(a["url"] for a in p.attachments), n=16)
        if known and not outdated and known["content_hash"] == h:
            stats["skipped"] += 1
            continue
        cands = extract.from_post(p, cfg)
        extra: list[tuple[str, str]] = []
        if not any(c.start for c in cands) and p.attachments:
            for a in p.attachments[:3]:
                if not a["name"].lower().endswith(".pdf"):
                    continue
                data = http.download(a["url"])
                text = _pdf_text(data) if data else ""
                if text.strip():
                    extra.append(("attachment", text))
            if extra:
                cands = extract.from_post(p, cfg, extra=extra)
        if llm.available():
            cands = llm.refine(p, "\n".join([p.body, *(t for _, t in extra)]), cands)
        flags = sorted({f for c in cands for f in c.flags} | ({"image_only"} if p.image_only else set()))
        print(f"    [{p.post_id}] {p.title[:50]} → {len(cands)}건" + (f" {flags}" if flags else ""))
        if dry_run:
            for c in cands:
                print(f"        {c.start} {c.start_time or ''} ~ {c.end or ''} {c.end_time or ''} {c.confidence} {c.title}")
            continue
        with store.connect() as con:
            st = register(con, cfg["key"], cands, post_id=p.post_id)
            con.execute(
                "INSERT INTO posts(source_key, post_id, title, url, posted_at, writer, content_hash, fetched_at, relevant, "
                "n_items, flags, version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?) ON CONFLICT(source_key, post_id) "
                "DO UPDATE SET title = excluded.title, content_hash = excluded.content_hash, fetched_at = excluded.fetched_at, "
                "n_items = excluded.n_items, flags = excluded.flags, version = excluded.version",
                (cfg["key"], p.post_id, p.title, p.url, p.posted_at, p.writer, h, store.now_iso(), len(cands),
                 store.dumps(flags), C.EXTRACT_VERSION))
            store.touch(con)
        stats["posts"] += 1
        for k in ("new", "changed", "same", "removed"):
            stats[k] += st[k]
    with store.connect() as con:
        stats["count"] = con.execute(
            "SELECT COUNT(*) FROM items WHERE source_key = ? AND removed_at IS NULL", (cfg["key"],)).fetchone()[0]
    return stats


_BOARD_KEYS = ("base", "site", "board", "boardLabel", "boardUrl", "category", "categoryParam", "categoryLabel",
               "discoveredAt", "via")


def _fresh(rt: dict, homepage: str) -> bool:
    """찾아 둔 게시판을 그대로 써도 되나 — 같은 홈페이지이고 7일 안에 찾은 것."""
    if rt.get("via") != "auto" or rt.get("homepage") != homepage or not rt.get("board"):
        return False
    try:
        return datetime.now() - datetime.fromisoformat(rt["discoveredAt"]) < timedelta(days=C.DISCOVERY_MAX_AGE_DAYS)
    except (KeyError, ValueError):
        return False


def run_profile_board(cfg: dict, http: Http, dry_run: bool, pages: int) -> dict:
    """③ 내 단과대학 · ④ 내 학부 — 프로필(C2) 소속 → 홈페이지(homepages) → 학사 공지 게시판(k2web_discover) → K2Web 수집.

    사용자가 게시판 주소를 직접 지정했으면(user.overrideUrl) 그것을 쓴다. 읽는 게시판이 바뀌면(소속 변경 등)
    이전 게시판에서 온 항목을 정리한다 — 새 소속과 상관없는 공지가 남지 않게.
    """
    scope = cfg["scope"]
    profile = load_local_profile()
    res = homepages.resolve(scope, profile)
    override = (cfg.get("user") or {}).get("overrideUrl")
    rt = dict(cfg.get("runtime") or {})
    if override:
        parsed = parse_board_url(override)
        if not parsed:
            raise SourceError(f"직접 지정한 주소가 학과·단과대학 게시판 주소가 아닙니다: {override}")
        homepage = parsed["base"]
        board = {"base": parsed["base"], "site": parsed["site"], "board": parsed["board"],
                 "category": parsed["category"], "categoryParam": parsed["categoryParam"],
                 "categoryLabel": "직접 지정한 말머리" if parsed["category"] else None, "boardLabel": "직접 지정",
                 "boardUrl": override, "discoveredAt": store.now_iso(), "via": "manual"}
    else:
        if res["status"] == "needs_profile":
            raise NeedsProfile("설정 › 내 프로필에서 " + ("단과대학(학과)을" if scope == "college" else "학과를")
                               + " 고르면 그 홈페이지 공지를 받습니다")
        if res["status"] == "not_found":
            raise NotListed(f"'{res['target']}' 홈페이지를 학교 목록에서 찾지 못했습니다 — 게시판 주소를 직접 지정해 주세요")
        homepage = res["homepage"]
        if _fresh(rt, homepage):
            board = {k: rt.get(k) for k in _BOARD_KEYS}
        else:
            print(f"  {res['target']} 홈페이지에서 학사 공지 게시판 찾는 중: {homepage}")
            board = {**k2web_discover.discover(homepage, http), "via": "auto"}
    identity = f"{board['base']}|{board['site']}|{board['board']}|{board.get('category') or ''}"
    target = res["target"] or board["boardLabel"]
    print(f"  {target} → {board['boardUrl']} ({board['boardLabel']}"
          + (f" · 말머리 '{board['categoryLabel']}'" if board.get("category") else " · 말머리 없음 → 제목으로 학사 글만") + ")")
    if not dry_run:
        with store.connect() as con:
            if rt.get("identity") and rt["identity"] != identity:
                n = retire_source_items(con, cfg["key"])
                print(f"  읽는 게시판이 바뀌어 이전 게시판의 일정 {n}건을 정리했습니다")
            store.set_runtime(con, cfg["key"], {**board, "homepage": homepage, "target": target, "scope": scope,
                                                "identity": identity, "listedAs": res.get("listedAs")})
    # 이 게시판의 일정은 그 소속 학생 대상 — 프로필 소속이 바뀌면 '해당 없음'이 된다
    p = profile or {}
    audience: Optional[dict] = None
    if scope == "college" and p.get("college"):
        audience = {"colleges": [p["college"]]}
    elif scope == "dept" and p.get("department"):
        audience = {"departments": [p["department"]]}
    bcfg = {**cfg, "kind": "k2web", **{k: board.get(k) for k in _BOARD_KEYS}, "audience": audience}
    return run_board(bcfg, http, dry_run, pages)


def run(keys: Optional[list[str]] = None, pages: int = C.LIST_PAGES, dry_run: bool = False, by: str = "manual") -> int:
    """by = 누가 띄웠나 (button 대시보드 · manual 명령줄 · schedule/catchup/retry 예약) — sync.last.json 에 남는다."""
    C.ensure_dirs()
    args = sys.argv[1:]
    if not dry_run and not acquire_lock(args, by):
        return 3
    results: dict[str, dict] = {}
    code = 0
    prev_run: Optional[str] = None
    try:
        with store.connect() as con:
            rows = store.list_sources(con)
            if not dry_run:           # 이 시각 뒤에 처음 본 일정 = 이번 수집의 '신규' (대시보드 '신규 일정 N건')
                prev_run = store.get_meta(con, "last_run_started")
                store.set_meta(con, "last_run_started", store.now_iso())
        targets = [store.source_config(r) for r in rows
                   if (keys and r["key"] in keys) or (not keys and r["enabled"])]
        if keys and not targets:
            print(f"그런 원천이 없습니다: {keys}")
            return 1
        http = Http()
        for cfg in targets:
            print(f"■ {cfg['name']} ({cfg['key']})")
            t0 = time.time()
            try:
                if cfg["kind"] == "calendar_table":
                    res = run_table(cfg, http, dry_run)
                elif cfg["kind"] == "profile_board":
                    res = run_profile_board(cfg, http, dry_run, pages)
                elif cfg["kind"] in BOARD_KINDS:
                    res = run_board(cfg, http, dry_run, pages)
                else:
                    raise SourceError(f"알 수 없는 수집기 kind: {cfg['kind']}")
                results[cfg["key"]] = {"result": "ok", **res, "seconds": round(time.time() - t0, 1)}
                if not dry_run:
                    with store.connect() as con:
                        store.record_source_run(con, cfg["key"], "ok", res.get("count"), None)
                        store.touch(con)
                print(f"  완료 {res}")
            except (SourceError, OSError, ValueError) as e:
                kind = getattr(e, "result", None) or ("format_changed" if isinstance(e, FormatChanged) else "failed")
                reason = getattr(e, "reason", "오류")
                results[cfg["key"]] = {"result": kind, "error": f"{reason}: {e}"}
                print(f"  {'대기' if kind == 'needs_profile' else '실패'} — {reason}: {e}")
                if not dry_run:
                    with store.connect() as con:
                        store.record_source_run(con, cfg["key"], kind, None, f"{reason}: {str(e)[:200]}")
                        if kind == "format_changed":     # 형식이 바뀌면 알림 1건 (하루 한 번)
                            add_notification(con, f"sys:{cfg['key']}:{date.today():%Y%m%d}", "system", None,
                                             f"{cfg['name']} 형식이 바뀐 것 같습니다",
                                             "자동 등록을 멈췄습니다. 수집 원천 화면에서 확인하세요.", "/settings/sources")
                        store.touch(con)
        # 프로필에 소속이 아직 없는 것('대기')은 실패로 세지 않는다
        failed = [k for k, v in results.items() if v["result"] not in ("ok", "needs_profile")]
        code = 0 if not failed else (4 if len(failed) == len(results) else 1)
        return code
    except Exception as e:                  # 예상 못 한 오류도 잠금은 풀고 결과를 남긴다
        print(f"수집 중 오류: {type(e).__name__}: {e}")
        code = 4
        return code
    finally:
        if not dry_run:
            if code == 4:             # 하나도 못 받았으면 지난번 '신규'를 그대로 둔다 (네트워크 오류로 신규가 0 이 되지 않게)
                with store.connect() as con:
                    store.set_meta(con, "last_run_started", prev_run)
            release_lock(code, results)
