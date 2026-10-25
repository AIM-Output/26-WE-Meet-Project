"""C4 브리핑 명령줄 — `desktop/cli.py briefing` 으로 부른다 (개발 venv).

    cli.py briefing today                       오늘 브리핑 (만들 때가 됐는데 없으면 지금 만든다 — 앱과 같은 규칙)
    cli.py briefing make                        다시 만들기 (지금 기준으로 덮어쓴다)
    cli.py briefing list [-n 30]                지난 브리핑 목록
    cli.py briefing show 2026-10-25             그날 스냅샷
    cli.py briefing json [2026-10-25]           /api/briefings/{date} 응답 그대로 (날짜를 빼면 /api/briefing/today)
    cli.py briefing settings [--on|--off] [--time 07:30] [--keep 14] [--reset]

today·make 는 재료를 **대시보드 백엔드의 기능 어댑터**(univ_us_local/backend/app)에서 빌린다 — 앱이 쓰는 것과 같은 함수라
숫자가 화면과 같다(F10-R17). list·show·settings 는 이 폴더의 data/briefing.db 만 읽는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import config as C
from . import service
from . import settings as S

ICON = {"alert": "⚠", "class": "📚", "calendar": "📅", "clock": "⏰", "flame": "🔥", "bell": "🔔"}
SOURCE_WORD = {"scheduled": "정시", "catchup": "놓친 브리핑", "manual": "다시 만듦"}


def backend_sources() -> service.Sources:
    """앱 백엔드를 import 해 그 어댑터가 만든 재료 함수를 그대로 쓴다 (main.py 가 C1 캘린더 소스를 엮는다)."""
    if str(C.BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(C.BACKEND_DIR))
    from app import main  # type: ignore[import-not-found]  # noqa: F401 — 라우터를 붙이며 어댑터의 재료 함수를 엮는다
    from app import briefing as adapter  # type: ignore[import-not-found]
    return adapter.sources()


def render(b: dict) -> str:
    out = []
    head = f"☀ {b['date']} 브리핑 · {b['generatedAt'][11:16]} 생성 · {SOURCE_WORD.get(b['source'], b['source'])}"
    if b["missed"] and b["source"] != "catchup":
        head += f" (처음엔 놓친 브리핑 · {b['firstGeneratedAt'][11:16]})"
    out.append(head + f"  [{b['scheduledFor']} 예정]")
    if b.get("headline"):
        out.append(f"  {b['headline']}")
    if b["empty"]:
        out.append(f"  {b['emptyText']}")
    for s in b["sections"]:
        out.append(f"{ICON.get(s['icon'], '·')} {s['label']} {s['count'] or ''}".rstrip())
        if not s["items"]:
            out.append(f"    {s['empty']}")
        for it in s["items"][:C.SHOW_LINES]:
            tag = f"[{it['tag']}] " if it.get("tag") else ""
            sub = f"  — {it['sub']}" if it.get("sub") else ""
            out.append(f"    {tag}{it['text']}{sub}")
        rest = s["count"] - min(len(s["items"]), C.SHOW_LINES)
        if rest > 0:
            out.append(f"    +{rest}건 더")
        if s.get("footer"):
            out.append(f"    {s['footer']}")
    if b["gaps"]:
        out.append(f"(못 읽은 재료: {', '.join(b['gaps'])})")
    return "\n".join(out)


def cmd_today(_args) -> int:
    t = service.ensure_today(backend_sources())
    if t["briefing"] is None:
        print({"before": f"아직 {t['scheduledFor']} 전입니다 — 'make' 로 지금 만들 수 있습니다",
               "pending": f"수집이 끝나기를 기다리는 중: {', '.join(t['waitingFor'])} (최대 {C.WAIT_COLLECT_MIN}분)",
               "off": "브리핑이 꺼져 있습니다 — settings --on"}.get(t["state"], t["state"]))
        return 0
    print(render(t["briefing"]))
    return 0


def cmd_make(_args) -> int:
    print(render(service.regenerate(backend_sources())))
    return 0


def cmd_list(args) -> int:
    h = service.history(args.n)
    if not h["items"]:
        print("저장된 브리핑이 없습니다")
        return 0
    for b in h["items"]:
        chip = " [놓침]" if b["missed"] else ""
        print(f"{b['date']}  {b['generatedAt'][11:16]} {SOURCE_WORD.get(b['source'], b['source'])}{chip}  {b['summary']}")
    print(f"(보관 {h['keepDays']}일)")
    return 0


def cmd_show(args) -> int:
    try:
        print(render(service.get(args.date)))
    except service.NotFound:
        print(f"{args.date} 브리핑이 없습니다", file=sys.stderr)
        return 1
    return 0


def cmd_json(args) -> int:
    if args.date:
        try:
            out = service.get(args.date)
        except service.NotFound:
            print(f"{args.date} 브리핑이 없습니다", file=sys.stderr)
            return 1
    else:
        out = service.ensure_today(backend_sources())
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_settings(args) -> int:
    patch: dict = {}
    if args.on or args.off:
        patch["enabled"] = bool(args.on)
    if args.time:
        patch["time"] = args.time
    if args.keep is not None:
        patch["keepDays"] = args.keep
    try:
        v = service.save_settings(patch, reset=args.reset) if (patch or args.reset) else service.settings_view()
    except S.Invalid as e:
        print(f"설정을 바꾸지 못했습니다: {e}", file=sys.stderr)
        return 1
    print(f"브리핑 {'켜짐' if v['enabled'] else '꺼짐'} · {v['time']} · 보관 {v['keepDays']}일 · 한 줄 요약(LLM) {'있음' if v['llm'] else '없음'}")
    if v["changed"]:
        print("기본값에서 바꾼 것: " + ", ".join(v["changed"]))
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="cli.py briefing", description="C4 브리핑 (오늘 · 다시 만들기 · 지난 목록 · 설정)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("today", help="오늘 브리핑").set_defaults(fn=cmd_today)
    sub.add_parser("make", help="다시 만들기").set_defaults(fn=cmd_make)
    p = sub.add_parser("list", help="지난 브리핑 목록")
    p.add_argument("-n", type=int, default=30)
    p.set_defaults(fn=cmd_list)
    p = sub.add_parser("show", help="그날 스냅샷")
    p.add_argument("date")
    p.set_defaults(fn=cmd_show)
    p = sub.add_parser("json", help="API 응답 그대로")
    p.add_argument("date", nargs="?")
    p.set_defaults(fn=cmd_json)
    p = sub.add_parser("settings", help="설정 보기·바꾸기")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--on", action="store_true")
    g.add_argument("--off", action="store_true")
    p.add_argument("--time")
    p.add_argument("--keep", type=int)
    p.add_argument("--reset", action="store_true")
    p.set_defaults(fn=cmd_settings)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        args = ap.parse_args(["list", *(argv or [])])
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
