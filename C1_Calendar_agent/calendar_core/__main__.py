"""C1 명령줄 — `desktop/cli.py calendar_core` 로 부른다 (개발 venv · 표준 라이브러리만, fastapi 불필요).

    cli.py calendar_core list [--todo] [--from 2026-09-01] [--to 2026-12-31]   내 일정·할 일 (캘린더에 얹히는
                                                                  학사·마감·수업은 각 기능의 cli.py 로 본다)
    cli.py calendar_core add "회의" 2026-10-02T19:00 --end 2026-10-02T21:00 --category team
    cli.py calendar_core done <id>                                             할 일 완료 토글
    cli.py calendar_core rm <id>                                               지우기
    cli.py calendar_core count                                                 건수 · DB 자리
"""
from __future__ import annotations

import argparse
import sys

from . import config as C
from . import service, store


def _print(ev: dict) -> None:
    p = ev["extendedProps"]
    mark = ("[x] " if p["done"] else "[ ] ") if p["isTodo"] else "    "
    span = ev["start"] + (f" ~ {ev['end']}" if ev.get("end") else "")
    print(f"{ev['id']:>5}  {mark}{span:<40} {p['categoryLabel']:<4} {ev['title']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cli.py calendar_core", description="C1 서비스 캘린더 — 내 일정·할 일")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="내 일정·할 일 목록")
    p_list.add_argument("--todo", action="store_true", help="할 일만")
    p_list.add_argument("--from", dest="start", help="YYYY-MM-DD 부터")
    p_list.add_argument("--to", dest="end", help="YYYY-MM-DD 까지")

    p_add = sub.add_parser("add", help="내 일정·할 일 추가")
    p_add.add_argument("title")
    p_add.add_argument("start", help="YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM")
    p_add.add_argument("--end")
    p_add.add_argument("--category", default="personal", choices=sorted(C.CATEGORIES))
    p_add.add_argument("--todo", action="store_true", help="할 일로")
    p_add.add_argument("--memo", default="")

    sub.add_parser("count", help="건수 · DB 자리")
    for name, help_text in (("done", "할 일 완료 토글"), ("rm", "지우기")):
        sub.add_parser(name, help=help_text).add_argument("id", type=int)

    args = ap.parse_args(argv)
    store.init()

    if args.cmd == "list":
        events = [ev for ev in store.list_events() if service.overlaps(ev, args.start, args.end)]
        if args.todo:
            events = [ev for ev in events if ev["extendedProps"]["isTodo"]]
        for ev in events:
            _print(ev)
        print(f"— {len(events)}건")
        return 0

    if args.cmd == "add":
        if msg := service.date_error(args.start, args.end):
            print(msg, file=sys.stderr)
            return 2
        all_day = "T" not in args.start
        _print(store.create_event(title=args.title, start=args.start, end=args.end, all_day=all_day,
                                  category=args.category, memo=args.memo, is_todo=args.todo, done=False,
                                  origin=None))
        return 0

    if args.cmd == "done":
        current = store.get_event(args.id)
        if not current:
            print("일정이 없습니다.", file=sys.stderr)
            return 1
        _print(store.update_event(args.id, {"done": not current["extendedProps"]["done"]}))
        return 0

    if args.cmd == "rm":
        if not store.delete_event(args.id):
            print("일정이 없습니다.", file=sys.stderr)
            return 1
        print("지웠습니다.")
        return 0

    counts = store.count_events()
    print(f"일정 {counts['total']}건 · 할 일 {counts['todos']}건(완료 {counts['done']}) — {C.DB_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
