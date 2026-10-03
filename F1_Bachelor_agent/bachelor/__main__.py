"""F1 학사 일정 — 명령줄.

    python -m bachelor sync [--source KEY ...] [--pages N] [--dry-run] [--log FILE]   수집 (run-sync.cmd 가 부른다)
    python -m bachelor tick [--force] [--log FILE]                                    예약 수집 — 매일 08시 한 번 + 실패 시 재시도 (run-scheduled.cmd)
    python -m bachelor list [--semester 2026-2] [--tab all|mine|review|hidden]         학사 일정 목록
    python -m bachelor approve|hide|restore <event_id>                                 확인 필요 승인 · 숨김 · 복원
    python -m bachelor notify                                                          때가 된 알림 배달 + 목록
    python -m bachelor sources                                                         원천 4곳 상태 · 내 소속 홈페이지
    python -m bachelor enable|disable <source_key>                                     원천 켜고 끄기
    python -m bachelor set-board <my_dept|my_college> [게시판 주소]                       ③·④ 게시판 직접 지정 (주소 없으면 자동으로)
    python -m bachelor directory-sync                                                  단과대학·학부 홈페이지 목록 다시 받기

프로필(학년·소속)은 C2_Profile_agent 에 대시보드가 저장한 것을 읽는다. 없으면 '판단 불가'로 나오고 ③·④ 는 대기한다.
"""
from __future__ import annotations

import argparse
import os
import sys

from . import config as C


def _redirect(path: str) -> None:
    """출력을 로그 파일에 덧붙인다 (예약 작업·대시보드 버튼 실행은 창이 없으므로)."""
    from datetime import datetime
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_BINARY", 0), 0o644)
    os.dup2(fd, 1)
    os.dup2(fd, 2)
    os.close(fd)
    sys.stdout = open(1, "w", encoding="utf-8", buffering=1, closefd=False)
    sys.stderr = open(2, "w", encoding="utf-8", buffering=1, closefd=False)
    print(f"\n======== {datetime.now():%Y-%m-%d %H:%M:%S} ========")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bachelor", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync", help="수집")
    s.add_argument("--source", action="append", metavar="KEY")
    s.add_argument("--pages", type=int, default=C.LIST_PAGES)
    s.add_argument("--dry-run", action="store_true", help="저장하지 않고 무엇을 찾는지만 본다")
    s.add_argument("--log", metavar="FILE")
    s.add_argument("--by", choices=("button", "manual"), default="manual", help="누가 띄웠나 (대시보드 버튼은 button)")
    tk = sub.add_parser("tick", help="예약 수집")
    tk.add_argument("--force", action="store_true", help="오늘 이미 했어도 돈다")
    tk.add_argument("--log", metavar="FILE")
    ls = sub.add_parser("list", help="목록")
    ls.add_argument("--semester")
    ls.add_argument("--tab", choices=("all", "mine", "review", "hidden"), default="all")
    for name in ("approve", "hide", "restore"):
        p = sub.add_parser(name)
        p.add_argument("event_id")
    sub.add_parser("notify")
    sub.add_parser("sources")
    for name in ("enable", "disable"):
        p = sub.add_parser(name)
        p.add_argument("source_key")
    b = sub.add_parser("set-board")
    b.add_argument("source_key", choices=("my_dept", "my_college"))
    b.add_argument("url", nargs="?")
    sub.add_parser("directory-sync")
    args = ap.parse_args(argv)

    if args.cmd == "sync":
        if args.log:
            _redirect(args.log)
        from .pipeline import run
        return run(keys=args.source, pages=args.pages, dry_run=args.dry_run, by=args.by)
    if args.cmd == "tick":
        if args.log:
            _redirect(args.log)
        from .schedule import tick
        return tick(force=args.force)
    if args.cmd == "directory-sync":
        import json
        from .sources import directory_crawl
        from .sources.base import Http
        d = directory_crawl.crawl(Http())
        C.LOCAL_DIRECTORY.parent.mkdir(parents=True, exist_ok=True)
        C.LOCAL_DIRECTORY.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장: {C.LOCAL_DIRECTORY} — 단과대학 {len(d['colleges'])}곳")
        return 0

    from . import notify, service, sources_admin, store
    from .profile import load_local_profile
    profile = load_local_profile()

    if args.cmd == "list":
        with store.connect() as con:
            ov = service.overview(con, profile)
        sem = args.semester or ov["currentSemester"]
        rows = [e for e in ov["items"] if e["semester"] == sem]
        pick = {
            "all": lambda e: e["status"] in ("auto", "approved"),
            "mine": lambda e: e["status"] in ("auto", "approved") and e["appliesToMe"] is True,
            "review": lambda e: e["status"] == "review",
            "hidden": lambda e: e["status"] == "hidden",
        }[args.tab]
        rows = [e for e in rows if pick(e)]
        mark = {True: "내 해당", False: "해당 없음", None: "판단 불가"}
        print(f"{sem}학기 · {args.tab} {len(rows)}건" + ("  (프로필 없음 — 대시보드에서 입력)" if not profile else ""))
        for e in rows:
            end = f" ~ {e['end'][:16]}" if e["end"] else ""
            print(f"  {e['start'] or '날짜 없음':16}{end:19} {e['typeLabel']:8} {e['confidence']:.2f} "
                  f"{mark[e['appliesToMe']]:6} {e['title']}  [{e['id']}]")
        return 0
    if args.cmd in ("approve", "hide", "restore"):
        status = {"approve": "approved", "hide": "hidden", "restore": "restore"}[args.cmd]
        with store.connect() as con:
            service.update_event(con, args.event_id, {"status": status})
        print("완료")
        return 0
    if args.cmd == "notify":
        with store.connect() as con:
            res = notify.list_notifications(con, profile)
        print(f"안 읽은 알림 {res['unread']}건")
        for n in res["items"]:
            print(f"  {'●' if not n['read'] else ' '} {n['at'][:16]} {'[놓침] ' if n['missed'] else ''}{n['title']} — {n['body']}")
        return 0
    if args.cmd == "sources":
        with store.connect() as con:
            for r in sources_admin.list_rows(con, profile):
                print(f"  {'켜짐' if r['enabled'] else '꺼짐'} {r['key']:12} {r['name']:14} {r['state']:13} "
                      f"마지막 {r['lastRunAt'] or '-'} · 보이는 일정 {r['items']}건")
                if r["scope"]:
                    where = r["board"]["url"] if r["board"] else (r["homepage"] or "-")
                    print(f"        소속 {r['target'] or '(프로필에 없음)'} → {where}"
                          + (" [직접 지정]" if r["overrideUrl"] else "") + (" · 다시 받아야 함" if r["stale"] else ""))
                if r["error"] and r["state"] != "ok":
                    print(f"        {r['error']}")
        return 0
    if args.cmd in ("enable", "disable"):
        with store.connect() as con:
            sources_admin.set_enabled(con, args.source_key, args.cmd == "enable")
            store.touch(con)
        print("완료")
        return 0
    if args.cmd == "set-board":
        with store.connect() as con:
            sources_admin.set_override(con, args.source_key, args.url)
            store.touch(con)
        print("직접 지정했습니다" if args.url else "자동으로 되돌렸습니다")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
