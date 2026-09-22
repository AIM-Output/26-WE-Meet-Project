"""1단계 수집 — 게시판 목록 → 신규 글 판별 → 본문·첨부 저장.  (기능명세서 DF-5 ①②)

    python -m scripts.collect                       # 설정된 소스 전부
    python -m scripts.collect --source jnu_home_scholarship --source aisw_dept
    python -m scripts.collect --dry-run             # 목록만 보고 본문은 안 받음
    python -m scripts.collect --pages 3             # 처음 한 번은 페이지를 늘려 과거 글까지
    python -m scripts.collect --refetch             # 이미 받은 글도 다시 받음 (구조 바뀐 뒤 검증용)
    python -m scripts.collect --source hakstd_catalog --interactive   # SSO 세션이 없을 때 창 띄워 로그인

결과
    data/notices/<source>/<id>.json   Notice (schemas.py)
    data/attachments/<id>/…           공고문 파일
    data/manifest.json                {notice_id: {hash, title, url, first_seen, last_seen}} — 신규 판별 기준
표준 출력에 신규/변경 목록을 찍는다. 이후 단계(extract → match → draft)는 pipeline.py 가 이어서 돈다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from . import config as C
from .attachments import fetch_attachments
from .http import Http
from .schemas import Notice
from .sources import make_source
from .textutil import sanitize_filename


def load_manifest() -> dict:
    if C.MANIFEST_FILE.exists():
        return json.loads(C.MANIFEST_FILE.read_text(encoding="utf-8"))
    return {}


def save_manifest(m: dict) -> None:
    C.MANIFEST_FILE.parent.mkdir(parents=True, exist_ok=True)
    C.MANIFEST_FILE.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def notice_path(notice_id: str):
    src, _, native = notice_id.partition(":")
    return C.NOTICE_DIR / src / f"{sanitize_filename(native)}.json"


def save_notice(n: Notice) -> None:
    p = notice_path(n.id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(n.model_dump_json(indent=2, exclude_none=False), encoding="utf-8")


def load_notice(notice_id: str) -> Notice | None:
    p = notice_path(notice_id)
    if not p.exists():
        return None
    return Notice.model_validate_json(p.read_text(encoding="utf-8"))


def iter_notices(source_keys: list[str] | None = None):
    for src_dir in sorted(C.NOTICE_DIR.glob("*")):
        if not src_dir.is_dir():
            continue
        if source_keys and src_dir.name not in source_keys:
            continue
        for p in sorted(src_dir.glob("*.json")):
            yield Notice.model_validate_json(p.read_text(encoding="utf-8"))


def collect(source_keys: list[str] | None = None, pages: int = C.LIST_PAGES, dry_run: bool = False,
            refetch: bool = False, interactive: bool = False) -> dict:
    """반환: {"new": [ids], "updated": [ids], "unchanged": n, "skipped": n, "errors": [(source, msg)]}"""
    C.ensure_dirs()
    http = Http()
    manifest = load_manifest()
    now = datetime.now().isoformat(timespec="seconds")
    report = {"new": [], "updated": [], "unchanged": 0, "skipped": 0, "errors": []}

    for cfg in C.enabled_sources(source_keys):
        print(f"\n== [{cfg['key']}] {cfg['name']}")
        try:
            src = make_source(cfg, http)
            if cfg["kind"] == "hakstd":
                src.interactive = interactive
            items = src.list_items(pages)
        except Exception as e:
            msg = f"목록 수집 실패: {type(e).__name__}: {str(e)[:160]}"
            print("   !", msg)
            report["errors"].append((cfg["key"], msg))
            continue
        wanted = [it for it in items if src.wanted(it)]
        print(f"   목록 {len(items)}건 중 장학 관련 {len(wanted)}건")
        for it in wanted:
            nid = src.notice_id(it.native_id)
            known = manifest.get(nid)
            if known and not refetch and notice_path(nid).exists():
                # 목록 단계에서는 본문 해시를 모른다. 제목이 그대로면 변경 없음으로 본다 (요청 수 절약).
                if known.get("title") == it.title:
                    report["unchanged"] += 1
                    manifest[nid]["last_seen"] = now
                    continue
            if dry_run:
                print(f"   + {it.posted_at or '????-??-??'}  {it.title[:70]}")
                report["new"].append(nid)
                continue
            try:
                n = src.fetch_detail(it)
                fetch_attachments(http, n)
            except Exception as e:
                msg = f"{nid} 본문 수집 실패: {type(e).__name__}: {str(e)[:120]}"
                print("   !", msg)
                report["errors"].append((cfg["key"], msg))
                continue
            save_notice(n)
            entry = manifest.get(nid)
            if entry is None:
                manifest[nid] = {"hash": n.content_hash, "title": n.title, "url": n.url,
                                 "source": n.source, "posted_at": n.posted_at, "first_seen": now, "last_seen": now}
                report["new"].append(nid)
                tag = "NEW"
            elif entry.get("hash") != n.content_hash:
                entry.update({"hash": n.content_hash, "title": n.title, "last_seen": now, "updated_at": now})
                report["updated"].append(nid)
                tag = "UPD"
            else:
                entry["last_seen"] = now
                report["unchanged"] += 1
                tag = "same"
            flags = []
            if n.body_is_image_only:
                flags.append("이미지 본문")
            if any(a.local_path and not a.text_extracted for a in n.attachments):
                flags.append("첨부(텍스트 미추출)")
            if n.is_result_notice:
                flags.append("결과/홍보")
            print(f"   {tag:4s} {n.posted_at or '????-??-??'}  {n.title[:60]}  {'· '.join(flags)}")
            save_manifest(manifest)
        report["skipped"] += len(items) - len(wanted)

    save_manifest(manifest)
    print(f"\n완료: 신규 {len(report['new'])} · 변경 {len(report['updated'])} · 그대로 {report['unchanged']} · "
          f"장학 무관 {report['skipped']} · 오류 {len(report['errors'])} (요청 {http.requests}회)")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append", metavar="KEY", help="config.SOURCES 의 key (여러 번 가능)")
    ap.add_argument("--pages", type=int, default=C.LIST_PAGES)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--refetch", action="store_true")
    ap.add_argument("--interactive", action="store_true", help="SSO 소스에서 세션이 없으면 창을 띄워 직접 로그인")
    a = ap.parse_args(argv)
    rep = collect(a.source, a.pages, a.dry_run, a.refetch, a.interactive)
    return 1 if rep["errors"] and not (rep["new"] or rep["updated"] or rep["unchanged"]) else 0


if __name__ == "__main__":
    sys.exit(main())
