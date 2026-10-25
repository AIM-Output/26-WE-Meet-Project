"""수집 — 켜진 원천의 게시판 목록 → 장학이 아닌 새 글 상세(+짧으면 첨부 글자) → 정보 추출 → 저장. 자식 프로세스(`-m activity sync`)에서 돈다.

    python -m activity sync [--source jnu_notice …] [--college AI융합대학 --dept 인공지능학부 --major …]

게시판 수집기는 F11 의 것을 그대로 쓴다 (scholarship.sources — aspx · k2web · coss · coursemos, 요청 간격 1.5초·동시성 1).
순서 (원천마다)
  0. F11 장학 수집이 돌고 있으면 끝날 때까지 기다린다 — 두 기능이 같은 학교 서버를 동시에 읽지 않게 (최대 30분)
  1. 목록 2쪽(처음 보는 원천 3쪽, 학교 전체 공지는 3·5쪽) — 거르는 것:
       장학 글(F11 과 같은 어휘 — 장학 화면 몫) · 말머리 행정공고·입찰공고·채용공고 · 부고·입찰·교원 초빙 같은 어휘 ·
       원천의 require(총동창회는 모집·행사 글만) · 45일보다 오래된 글(상단 고정의 옛 안내)
  2. 처음 보는 글만 상세를 받는다(원천마다 최대 25건). 최근 10일 글은 몇 건씩 다시 받아 수정 여부(내용 해시)를 본다
  3. 본문이 짧으면 첨부 PDF·HWPX·DOCX 의 글자를 읽는다(모집 요강이 첨부에만 있는 경우, 파일은 저장하지 않는다)
  4. 같은 글이 다른 게시판에 또 올라왔으면(제목 키) 먼저 들어온 것에 묶는다(dup_of)
  내 단과대학·학과(profile_board)는 프로필 소속 → 홈페이지(F1 목록) → **공지 게시판 찾기**(장학 메뉴는 건너뛴다, 7일마다 다시)
종료 코드: 0 성공 · 2 일부 원천 실패 · 3 이미 수집 중 · 4 전부 실패(대개 네트워크)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Optional

from . import config as C
from . import extract, registry, store
from . import interests as I
from scholarship import attachments
from scholarship.textutil import content_hash, has_any, is_scholarship, norm_title, to_date


def _log(msg: str) -> None:
    line = f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    try:
        C.STATE_DIR.mkdir(parents=True, exist_ok=True)
        with open(C.LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _host_key(cfg: dict) -> str:
    """같은 게시판이면 같은 글 id — 'www:37467' · 'aisw:937224' · 'aicoss:4117' (F11 과 같은 규칙이라 같은 글은 같은 id)."""
    if cfg.get("site"):
        return cfg["site"]
    host = cfg["base"].split("//", 1)[-1].split("/")[0]
    return host.split(".")[0] if not host.startswith("jnu.") else host.split(".")[1]


def skip_reason(title: str, category: Optional[str], cfg: dict, writer: Optional[str] = None) -> Optional[str]:
    """이 글을 대외활동으로 모으지 않는 이유 — 없으면 None."""
    if is_scholarship(title, category):
        return "장학"
    bc = extract.board_category(title, category)
    if bc and bc in registry.drop_categories():
        return f"말머리 {bc}"
    if I.is_academic(title, writer):
        return "학사 행정 안내"
    if has_any(title, registry.drop_words()) or (cfg.get("dropWords") and has_any(title, cfg["dropWords"])):
        return "거르는 어휘"
    if cfg.get("require") and not has_any(title, cfg["require"]):
        return "원천 조건"
    return None


def _attachment_text(post, http) -> tuple[str, list[dict], int]:
    """본문이 짧을 때만 첨부 글자를 읽는다. 반환 (글자, 첨부 목록, 읽지 못한 첨부 수)."""
    short = len((post.body or "").strip()) < C.ATTACH_BODY_SHORT
    texts, infos, unread = [], [], 0
    for a in post.attachments[:8]:
        ext = attachments.ext_of(a.get("name", ""), a.get("url", ""))
        info = {"name": a.get("name"), "url": a.get("url"), "ext": ext, "read": False}
        if short and ext in attachments.READABLE and sum(1 for i in infos if i["read"]) < C.MAX_ATTACH_PER_NOTICE:
            data = http.download(a["url"])
            t = attachments.read_text(data, ext) if data else None
            if t and len(t.strip()) > 30:
                texts.append(f"[첨부: {a.get('name')}]\n{t.strip()}")
                info["read"] = True
        if short and not info["read"] and ext not in (".jpg", ".jpeg", ".png", ".zip"):
            unread += 1
        infos.append(info)
    return "\n\n".join(texts), infos, unread


def build_info(row_like: dict, unit: Optional[dict], unread: int = 0) -> dict:
    """저장된 공지 한 줄 → 정보. 서비스(규칙 판이 바뀐 공지 다시 뽑기)도 같은 함수를 쓴다."""
    text = row_like.get("body") or ""
    if row_like.get("attach_text"):
        text = f"{text}\n\n{row_like['attach_text']}"
    return extract.extract(row_like["title"], text, unit=unit, category=row_like.get("category"), writer=row_like.get("writer"),
                           image_only=bool(row_like.get("image_only")),
                           attachments_unread=unread, posted_at=row_like.get("posted_at"))


def _save_post(con, cfg: dict, post, http, hk: str, unit_cfg: Optional[dict]) -> str:
    attach_text, infos, unread = _attachment_text(post, http) if post.attachments else ("", [], 0)
    unit = unit_cfg or registry.unit_for(post.writer, post.title, post.category)
    nid = f"{hk}:{post.native_id}"
    tk = norm_title(post.title)
    row = {
        "id": nid, "source": cfg["key"], "source_name": cfg.get("name") or cfg["key"], "unit_key": unit["key"] if unit else None,
        "title": post.title, "url": post.url, "posted_at": post.posted_at, "writer": post.writer, "category": post.category,
        "body": post.body, "attach_text": attach_text, "attachments": infos, "image_only": post.image_only,
        "content_hash": content_hash(post.title, post.body, *[a.get("url", "") for a in infos]),
        "title_key": tk, "dup_of": store.find_dup(con, tk, nid),
    }
    row["info"] = build_info(row, unit, unread)
    row["extract_ver"] = C.EXTRACT_VERSION
    return store.upsert_notice(con, row)


# ── 내 단과대학·학과 공지 게시판 찾기 ──────────────────────────

def discover_notice(homepage: str, http) -> dict:
    """홈페이지 → 공지 게시판 {base, site, board, boardLabel, boardUrl, discoveredAt}.
    F11 k2web.discover 와 같은 길로 메뉴를 훑되 '장학' 메뉴는 건너뛰고(장학 화면 몫) 학부·학과 공지 > 공지사항 순으로 고른다.
    말머리는 걸지 않는다 — 공지 전체를 읽고 장학 글만 뺀다."""
    from urllib.parse import urlparse
    from scholarship.sources import k2web
    from scholarship.sources.base import FormatChanged
    r = http.get(homepage)
    base = f"{urlparse(r.url).scheme}://{urlparse(r.url).netloc}"
    label, ref = None, None
    for _score, text, url in [m for m in k2web._menus(r.text, r.url) if "장학" not in m[1]][:4]:
        ref = k2web._board_ref(http.get(url).text)
        if ref:
            label = text
            break
    if not ref:
        more = list(dict.fromkeys(re.findall(r"/bbs/([\w-]+)/(\d+)/artclList\.do", r.text)))
        if not more:
            raise FormatChanged(f"{base} 에서 공지 게시판을 찾지 못했습니다")
        ref, label = more[0], "첫 화면 공지"
    site, board = ref
    return {"base": base, "site": site, "board": board, "boardLabel": label,
            "boardUrl": f"{base}/bbs/{site}/{board}/artclList.do", "discoveredAt": datetime.now().isoformat(timespec="seconds")}


def collect_source(cfg: dict, http, profile: dict, dry_run: bool = False) -> dict:
    from scholarship.sources import COLLECTORS
    from scholarship.sources.base import NeedsProfile, NotListed
    kind = cfg["kind"]
    with store.connect() as con:
        srow = store.source_rows(con).get(cfg["key"])
    first = srow is None or not srow["last_ok_at"]
    cfg = dict(cfg)
    if kind == "profile_board":
        hp = registry.homepage(cfg.get("level", "dept"), profile)
        target = profile.get("college") if cfg.get("level") == "college" else (profile.get("department") or profile.get("major"))
        if not target:
            raise NeedsProfile("프로필에 소속이 없습니다")
        if not hp:
            raise NotListed(f"'{target}' 홈페이지를 목록에서 찾지 못했습니다")
        disc = json.loads(srow["discovered"]) if srow is not None and srow["discovered"] else None
        stale = (not disc or disc.get("homepage") != hp["homepage"]
                 or (datetime.now() - datetime.fromisoformat(disc.get("discoveredAt", "2000-01-01"))).days >= C.DISCOVERY_MAX_AGE_DAYS)
        if stale:
            disc = {**discover_notice(hp["homepage"], http), "homepage": hp["homepage"], "target": target, "listedAs": hp["listedAs"]}
            if not dry_run:
                with store.connect() as con:
                    store.put_source(con, cfg["key"], discovered=json.dumps(disc, ensure_ascii=False),
                                     discovered_at=disc["discoveredAt"])
        cfg.update(base=disc["base"], site=disc["site"], board=disc["board"], category=None, categoryParam=None,
                   name=f"{disc.get('listedAs') or target} 공지")     # 학과를 바꾸면 목록이 예전 학과 공지를 이 이름으로 걸러 낸다
    mod = COLLECTORS[kind]
    pages = (cfg.get("firstPages") or C.FIRST_LIST_PAGES) if first else (cfg.get("pages") or C.LIST_PAGES)
    posts = mod.list_posts(cfg, http, pages)
    oldest = date.today() - timedelta(days=C.FIRST_MAX_AGE_DAYS)
    want, skipped = [], {}
    for p in posts:
        why = skip_reason(p.title, p.category, cfg, p.writer)
        if why is None and to_date(p.posted_at) and to_date(p.posted_at) < oldest:
            why = "오래된 글"
        if why:
            skipped[why] = skipped.get(why, 0) + 1
        else:
            want.append(p)
    hk = _host_key(cfg)
    # 특정 학과·캠퍼스 대상 원천(사업단·공학교육혁신센터 …)의 글은 그 원천을 주관으로 붙인다. 학교 전체 게시판은 작성 부서로 찾는다.
    unit_cfg = registry.get(cfg["key"]) if (cfg.get("audience") or {}).get("scope") in ("related", "campus") else None
    with store.connect() as con:
        known = {r["id"] for r in con.execute("SELECT id FROM notices WHERE id LIKE ?", (f"{hk}:%",))}
    limit = (cfg.get("firstMaxDetail") or C.FIRST_MAX_DETAIL) if first else (cfg.get("maxDetail") or C.MAX_DETAIL_PER_SOURCE)
    new = [p for p in want if f"{hk}:{p.native_id}" not in known][:limit]
    recent = date.today() - timedelta(days=C.RECHECK_DAYS)
    recheck = [p for p in want if f"{hk}:{p.native_id}" in known and to_date(p.posted_at) and to_date(p.posted_at) >= recent]
    recheck = recheck[:C.RECHECK_MAX]
    counts = {"listed": len(posts), "matched": len(want), "new": 0, "changed": 0, "skipped": skipped}
    if dry_run:
        for p in posts:
            why = skip_reason(p.title, p.category, cfg, p.writer)
            mark = "새" if p in new else ("  " if p in want else "-")
            _log(f"  [{cfg['key']}] {mark} {p.posted_at or '?':10s} {p.title[:64]}{f'  ({why})' if why else ''}")
        counts["new"] = len(new)
        return counts
    for p in new + recheck:
        try:
            p = mod.fetch_detail(p, cfg, http)
        except Exception as e:                   # noqa: BLE001 — 글 하나 실패로 원천 전체를 버리지 않는다
            _log(f"  ! [{cfg['key']}] 상세 실패 {p.url}: {type(e).__name__}: {e}")
            continue
        if is_scholarship(p.title, p.category) or I.is_academic(p.title, p.writer):   # 상세에서야 보이는 제목·작성 부서
            continue
        if to_date(p.posted_at) and to_date(p.posted_at) < oldest:   # 목록에 날짜가 없는 게시판(XE·CNU Events) — 상세에서 본 날짜로
            continue
        with store.connect() as con:
            res = _save_post(con, cfg, p, http, hk, unit_cfg)
        if res in ("new", "changed"):
            counts[res] += 1
    return counts


# ── 실행 (F11 기다리기 · 잠금 · 기록) ─────────────────────────

def _read_lock(path) -> Optional[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def wait_for_peer(sleep=time.sleep, now=time.monotonic) -> bool:
    """F11 장학 수집이 돌고 있으면 끝날 때까지 기다린다 (자기 잠금을 잡기 **전에** — F11 은 잠금을 잡고 F12 를 기다리므로 서로 막히지 않는다).
    반환: 기다렸는가."""
    until = now() + C.PEER_WAIT_MIN * 60
    waited = False
    while now() < until:
        data = _read_lock(C.F11_LOCK_FILE)
        pid = (data or {}).get("pid")
        if not isinstance(pid, int) or pid == os.getpid() or not C.pid_alive(pid):
            return waited
        if not waited:
            _log("장학(F11) 수집이 끝나기를 기다립니다 — 같은 게시판을 동시에 읽지 않게")
        waited = True
        sleep(5)
    _log("장학 수집이 오래 걸려 기다리지 않고 시작합니다")
    return waited


def _lock() -> bool:
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    data = _read_lock(C.LOCK_FILE)
    if data and isinstance(data.get("pid"), int) and data["pid"] != os.getpid() and C.pid_alive(data["pid"]):
        return False
    C.LOCK_FILE.write_text(json.dumps({"pid": os.getpid(), "started_at": store.now_iso()}), encoding="utf-8")
    return True


def run(keys: Optional[list[str]] = None, profile: Optional[dict] = None, *, by: str = "manual", dry_run: bool = False) -> int:
    from scholarship.sources.base import Http, SourceError
    C.ensure_dirs()
    if not dry_run:
        wait_for_peer()
        if not _lock():
            _log("이미 수집 중입니다 (state/sync.lock)")
            return 3
    started = store.now_iso()
    profile = profile or {}
    results: dict[str, dict] = {}
    try:
        with store.connect() as con:
            rows = registry.resolve(profile, store.overrides(con))
        targets = registry.collectable(rows)
        if keys:
            targets = [r for r in rows if r["key"] in keys and r["kind"] != "relay"]
        http = Http()
        _log(f"대외활동 수집 시작 ({by}) — 원천 {len(targets)}곳: {', '.join(t['key'] for t in targets)}")
        for cfg in targets:
            t0 = store.now_iso()
            try:
                c = collect_source(cfg, http, profile, dry_run)
                results[cfg["key"]] = {"ok": True, **c}
                sk = " · ".join(f"{k} {v}" for k, v in c.get("skipped", {}).items())
                _log(f"  [{cfg['key']}] 목록 {c['listed']} · 대외활동 {c['matched']} · 새 글 {c['new']} · 바뀜 {c['changed']}"
                     + (f" (거름: {sk})" if sk else ""))
                if not dry_run:
                    with store.connect() as con:
                        store.put_source(con, cfg["key"], last_run_at=t0, last_ok_at=store.now_iso(), last_count=c["matched"],
                                         last_new=c["new"], last_error=None)
            except Exception as e:               # noqa: BLE001 — 원천 하나가 실패해도 나머지는 받는다
                reason = getattr(e, "reason", None) or ("접속 실패" if isinstance(e, SourceError) else "처리 오류")
                status = "needs_profile" if type(e).__name__ == "NeedsProfile" else "error"
                results[cfg["key"]] = {"ok": False, "status": status, "reason": reason, "error": str(e)[:300]}
                _log(f"  ! [{cfg['key']}] {reason}: {e}")
                if not isinstance(e, SourceError):
                    _log(traceback.format_exc(limit=3))
                if not dry_run:
                    with store.connect() as con:
                        store.put_source(con, cfg["key"], last_run_at=t0, last_error=f"{reason}: {str(e)[:200]}")
        oks = [k for k, v in results.items() if v["ok"]]
        fails = [k for k, v in results.items() if not v["ok"] and v.get("status") != "needs_profile"]
        code = 0 if not fails else (4 if not oks else 2)
        if not dry_run:
            with store.connect() as con:
                if oks and not store.get_meta(con, "baseline_at"):
                    store.set_meta(con, "baseline_at", store.now_iso())   # 첫 수집 = 알림 기준선 (그때까지 쌓인 글은 알리지 않는다)
                if oks:
                    store.set_meta(con, "last_ok_at", store.now_iso())
                store.set_meta(con, "last_run_at", started)
                store.touch(con)
        _log(f"대외활동 수집 끝 — 성공 {len(oks)} · 실패 {len(fails)} · 요청 {http.count}회 (코드 {code})")
        return code
    finally:
        if not dry_run:
            last = {"started_at": started, "finished_at": store.now_iso(), "by": by, "sources": results}
            last["exit_code"] = 0 if all(v["ok"] or v.get("status") == "needs_profile" for v in results.values()) else (
                4 if not any(v["ok"] for v in results.values()) else 2)
            try:
                C.LAST_RUN_FILE.write_text(json.dumps(last, ensure_ascii=False, indent=1), encoding="utf-8")
                C.LOCK_FILE.unlink(missing_ok=True)
            except OSError:
                pass


if __name__ == "__main__":
    sys.exit(run())
