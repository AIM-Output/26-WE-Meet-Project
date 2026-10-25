"""수집 — 켜진 원천의 게시판 목록 → 새 글 상세(+첨부 글자) → 요건 추출 → 저장. 자식 프로세스(`-m scholarship sync`)에서 돈다.

    python -m scholarship sync [--source jnu_scholarship …] [--college AI융합대학 --dept 인공지능학부 --major …]

순서 (원천마다, 요청 간격 1.5초 · 동시성 1)
  1. 목록 1~2쪽(처음 보는 원천은 3쪽) — 장학 전용 게시판·말머리가 아니면 제목 어휘(config.SCHOLARSHIP_WORDS)로 거른다
  2. 처음 보는 글만 상세를 받는다(원천마다 최대 25건). 최근 14일 글은 몇 건씩 다시 받아 수정 여부(내용 해시)를 본다
  3. 첨부 PDF·HWP·HWPX·DOCX 의 글자를 읽어 본문과 함께 추출한다(파일은 저장하지 않는다). 글자 없는 스캔 PDF·그림만 든 HWP,
     그리고 본문이 짧으면 본문 이미지·이미지 첨부는 OS 내장 OCR 로 (attachments.gather — 이 컴퓨터에 한국어 OCR 이 있을 때만)
  4. 같은 글이 다른 게시판에 또 올라왔으면(제목 키) 먼저 들어온 것에 묶는다(dup_of)
  5. 예전 판으로 읽어 못 읽은 공지(본문 이미지·HWP 첨부)는 원천마다 REREAD_MAX 건씩 상세를 다시 받아 읽는다 (notices.reader_ver)
  내 단과대학·학과(profile_board)는 프로필 소속 → 홈페이지(F1 목록) → 장학 게시판 찾기(k2web.discover, 7일마다 다시)
  상시 장학 안내(catalog)는 7일에 한 번.
  F12 대외활동 수집이 돌고 있으면 끝날 때까지 기다린다 — 같은 게시판을 읽으므로 동시성 1 을 두 기능 사이에서도 지킨다.
종료 코드: 0 성공 · 2 일부 원천 실패 · 3 이미 수집 중 · 4 전부 실패(대개 네트워크)
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from datetime import date, datetime, timedelta
from typing import Optional

from . import attachments, config as C, extract, registry, store
from .textutil import content_hash, has_any, is_result, is_scholarship, norm_title, to_date


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
    """같은 게시판이면 같은 글 id 가 되게 — 'www:70601' · 'aisw:937224' · 'aicoss:4117' · 'ile:division-notice-11049'."""
    if cfg.get("site"):
        return cfg["site"]
    host = cfg["base"].split("//", 1)[-1].split("/")[0]
    return host.split(".")[0] if not host.startswith("jnu.") else host.split(".")[1]


def _fix_year(req: dict, posted: Optional[str]) -> None:
    """연도 없는 '1. 5.(월)까지' 를 게시 연도로 읽어 게시일보다 앞서면 다음 해로 (12월 공지의 1월 마감)."""
    p = req.get("period") or {}
    pd = to_date(posted)
    if not pd or not p.get("end") or (p.get("raw") and str(pd.year) in p["raw"]):
        return
    end = to_date(p["end"])
    if end and end < pd - timedelta(days=30):
        p["end"] = p["end"].replace(str(end.year), str(end.year + 1), 1)
        if p.get("start"):
            p["start"] = p["start"].replace(str(end.year), str(end.year + 1), 1)


def build_req(row_like: dict, unit: Optional[dict], unread: int = 0) -> dict:
    """저장된 공지 한 줄 → 요건. 서비스(규칙 판이 바뀐 공지 다시 뽑기)도 같은 함수를 쓴다."""
    posted = row_like.get("posted_at")
    year = to_date(posted).year if to_date(posted) else None
    text = row_like.get("body") or ""
    if row_like.get("attach_text"):
        text = f"{text}\n\n{row_like['attach_text']}"
    req = extract.extract(row_like["title"], text, unit=unit, image_only=bool(row_like.get("image_only")),
                          attachments_unread=unread, default_year=year, catalog=row_like.get("kind") == "catalog",
                          ocr=attachments.has_ocr(row_like.get("attach_text")))
    _fix_year(req, posted)
    return req


def _save_post(con, cfg: dict, post, http, hk: str, unit_cfg: Optional[dict], ocr=None) -> str:
    attach_text, infos, unread = (attachments.gather(post, http, max_read=C.MAX_ATTACH_PER_NOTICE, ocr=ocr)
                                  if post.attachments or post.images else ("", [], 0))
    unit = unit_cfg or registry.unit_for(post.writer, post.title, post.category)
    nid = f"{hk}:{post.native_id}"
    tk = norm_title(post.title)
    row = {
        "id": nid, "source": cfg["key"], "source_name": cfg.get("name") or cfg["key"], "unit_key": unit["key"] if unit else None,
        "kind": "notice", "title": post.title, "url": post.url, "posted_at": post.posted_at, "writer": post.writer,
        "category": post.category, "body": post.body, "attach_text": attach_text, "attachments": infos,
        "image_only": post.image_only, "content_hash": content_hash(post.title, post.body, *[a.get("url", "") for a in infos]),
        "is_result": is_result(post.title), "title_key": tk, "dup_of": store.find_dup(con, tk, nid),
    }
    row["req"] = build_req(row, unit, unread)
    row["extract_ver"] = C.EXTRACT_VERSION
    row["reader_ver"] = attachments.reader_version(ocr)
    return store.upsert_notice(con, row)


def collect_source(cfg: dict, http, profile: dict, dry_run: bool = False, ocr=None) -> dict:
    from .sources import COLLECTORS, k2web
    from .sources.base import NeedsProfile, NotListed
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
            disc = {**k2web.discover(hp["homepage"], http), "homepage": hp["homepage"], "target": target,
                    "listedAs": hp["listedAs"]}
            if not dry_run:
                with store.connect() as con:
                    store.put_source(con, cfg["key"], discovered=json.dumps(disc, ensure_ascii=False),
                                     discovered_at=disc["discoveredAt"])
        cfg.update(base=disc["base"], site=disc["site"], board=disc["board"], category=disc.get("category"),
                   categoryParam=disc.get("categoryParam"), filter=disc.get("filter", "keyword"),
                   name=f"{disc.get('listedAs') or target} 공지")     # 학과를 바꾸면 목록이 예전 학과 공지를 이 이름으로 걸러 낸다
    mod = COLLECTORS[kind]
    pages = C.FIRST_LIST_PAGES if first else C.LIST_PAGES
    posts = mod.list_posts(cfg, http, pages)
    # 말머리로 거른 게시판도 상단 고정 공지는 다른 말머리 글이 섞여 온다 → 고정 글만 제목으로 한 번 더 거른다 (F1 k2web.select 와 같은 규칙)
    want = [p for p in posts if (cfg.get("filter") == "all" and not (p.pinned and cfg.get("category")))
            or (is_scholarship(p.title, p.category) and not has_any(p.title, C.NOT_APPLY_WORDS)
                and (not cfg.get("require") or has_any(p.title, cfg["require"])))]
    hk = _host_key(cfg)
    # 특정 학과·캠퍼스 대상 원천(사업단·공학교육혁신센터 …)의 글은 그 원천을 '주관'으로 붙여 관련 여부를 판정에 싣는다.
    # 학교 전체 대상 게시판(학생과·부서)은 작성 부서로 찾는다(학교 공지에 사업단이 올린 글).
    unit_cfg = registry.get(cfg["key"]) if (cfg.get("audience") or {}).get("scope") in ("related", "campus") else None
    with store.connect() as con:
        known = {r["id"]: r for r in con.execute("SELECT id, posted_at, content_hash, reader_ver, image_only, body, attachments "
                                                 "FROM notices WHERE id LIKE ?", (f"{hk}:%",))}
    new = [p for p in want if f"{hk}:{p.native_id}" not in known][:C.FIRST_MAX_DETAIL if first else C.MAX_DETAIL_PER_SOURCE]
    recent = date.today() - timedelta(days=C.RECHECK_DAYS)
    recheck = [p for p in want if f"{hk}:{p.native_id}" in known and to_date(p.posted_at) and to_date(p.posted_at) >= recent]
    recheck = recheck[:C.RECHECK_MAX]
    ver = attachments.reader_version(ocr)
    reread = [p for p in want if p not in recheck and f"{hk}:{p.native_id}" in known
              and attachments.needs_reread(known[f"{hk}:{p.native_id}"], ver)][:C.REREAD_MAX]
    counts = {"listed": len(posts), "matched": len(want), "new": 0, "changed": 0, "reread": len(reread)}
    if dry_run:
        for p in want:
            _log(f"  [{cfg['key']}] {'새' if p in new else '  '} {p.posted_at or '?':10s} {p.title[:70]}")
        counts["new"] = len(new)
        return counts
    for p in new + recheck + reread:
        try:
            p = mod.fetch_detail(p, cfg, http)
        except Exception as e:                   # noqa: BLE001 — 글 하나 실패로 원천 전체를 버리지 않는다
            _log(f"  ! [{cfg['key']}] 상세 실패 {p.url}: {type(e).__name__}: {e}")
            continue
        with store.connect() as con:
            res = _save_post(con, cfg, p, http, hk, unit_cfg, ocr)
        if res in ("new", "changed"):
            counts[res] += 1
    return counts


def collect_catalog(cfg: dict, http, force: bool = False) -> dict:
    from .sources import catalog
    with store.connect() as con:
        at = store.get_meta(con, "catalog_at")
    if at and not force and (datetime.now() - datetime.fromisoformat(at)).days < C.CATALOG_MAX_AGE_DAYS:
        return {"listed": 0, "matched": 0, "new": 0, "changed": 0, "skipped": True}
    items = catalog.fetch(cfg["urls"], http)
    counts = {"listed": len(items), "matched": len(items), "new": 0, "changed": 0}
    with store.connect() as con:
        for it in items:
            # 지급액 칸의 여러 줄(진리장학1·2·3 …)은 한 줄로 — 줄마다 조건으로 읽히지 않게
            amount = " / ".join(x.strip() for x in (it.get("amount") or "").splitlines() if x.strip())
            body = "\n".join(x for x in (f"[{it['section']}]" if it.get("section") else "", it["qualification"],
                                         f"지급액: {amount}" if amount else "",
                                         f"(장학기본성적) {it['base']}" if it.get("base") else "") if x)
            row = {"id": f"cat:{it['native_id']}", "source": cfg["key"], "source_name": cfg["name"], "unit_key": None,
                   "kind": "catalog", "title": it["title"], "url": it["url"], "posted_at": None, "writer": "학생과",
                   "category": it.get("section"), "body": body, "attach_text": "", "attachments": [], "image_only": False,
                   "content_hash": content_hash(it["title"], body), "is_result": False, "title_key": norm_title(it["title"]),
                   "dup_of": None}
            row["req"] = build_req(row, None)
            row["req"]["amount"] = amount or row["req"].get("amount")
            row["extract_ver"] = C.EXTRACT_VERSION
            res = store.upsert_notice(con, row)
            if res in ("new", "changed"):
                counts[res] += 1
        store.set_meta(con, "catalog_at", store.now_iso())
    return counts


# ── 실행 (잠금 · 기록) ───────────────────────────────────────

def _lock() -> bool:
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(C.LOCK_FILE.read_text(encoding="utf-8"))
        if isinstance(data.get("pid"), int) and data["pid"] != os.getpid() and C.pid_alive(data["pid"]):
            return False
    except (OSError, ValueError):
        pass
    C.LOCK_FILE.write_text(json.dumps({"pid": os.getpid(), "started_at": store.now_iso()}), encoding="utf-8")
    return True


def _wait_for_peer(sleep=time.sleep, now=time.monotonic) -> bool:
    """F12 대외활동 수집이 돌고 있으면 끝날 때까지 기다린다 — 두 기능이 같은 학교 서버를 동시에 읽지 않게. 반환: 기다렸는가."""
    until = now() + C.PEER_WAIT_MIN * 60
    waited = False
    while now() < until:
        try:
            pid = json.loads(C.PEER_LOCK_FILE.read_text(encoding="utf-8")).get("pid")
        except (OSError, ValueError, AttributeError):
            return waited
        if not isinstance(pid, int) or pid == os.getpid() or not C.pid_alive(pid):
            return waited
        if not waited:
            _log("대외활동(F12) 수집이 끝나기를 기다립니다 — 같은 게시판을 동시에 읽지 않게")
        waited = True
        sleep(5)
    return waited


def run(keys: Optional[list[str]] = None, profile: Optional[dict] = None, *, by: str = "manual",
        dry_run: bool = False, force_catalog: bool = False) -> int:
    from .sources.base import Http, SourceError
    C.ensure_dirs()
    if not dry_run and not _lock():
        _log("이미 수집 중입니다 (state/sync.lock)")
        return 3
    if not dry_run:
        _wait_for_peer()
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
        ocr = None if dry_run else attachments.ocr_engine()
        _log(f"장학 수집 시작 ({by}) — 원천 {len(targets)}곳: {', '.join(t['key'] for t in targets)}")
        if not dry_run:
            st = attachments.ocr_status()
            _log(f"  OCR: {st.get('engine')} ({st.get('lang')})" if ocr else f"  OCR 없음 — {st.get('reason') or '한국어 OCR 을 쓸 수 없습니다'}")
        for cfg in targets:
            t0 = store.now_iso()
            try:
                if cfg["kind"] == "catalog":
                    c = collect_catalog(cfg, http, force=force_catalog or bool(keys))
                else:
                    c = collect_source(cfg, http, profile, dry_run, ocr=ocr)
                results[cfg["key"]] = {"ok": True, **c}
                _log(f"  [{cfg['key']}] 목록 {c['listed']} · 장학 {c['matched']} · 새 글 {c['new']} · 바뀜 {c['changed']}"
                     + (f" · 다시 읽음 {c['reread']}" if c.get("reread") else ""))
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
        _log(f"장학 수집 끝 — 성공 {len(oks)} · 실패 {len(fails)} · 요청 {http.count}회 (코드 {code})")
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
