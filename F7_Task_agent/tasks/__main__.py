"""F7 명령줄 — `desktop/cli.py tasks` 로 부른다 (개발 venv · 표준 라이브러리만, fastapi 없이 돈다).

    cli.py tasks list [--course 운영체제] [--now 2026-10-06T14:00] [--all]   급한 순 목록 (그룹 · 이유 · 소요시간)
    cli.py tasks top [-n 3]                                                  먼저 할 것 N건 + 총 소요시간 (브리핑에 실리는 것)
    cli.py tasks today [--now …]                                             오늘 남은 시간 (취침 − 지금 − 수업·일정 − 학습 분량)
    cli.py tasks settings                                                    설정 보기
    cli.py tasks settings --safety 1.5 --hours quiz=0.5 project=6 --bed 01:00   설정 바꾸기 (--reset 으로 전부 기본값)
    cli.py tasks json [--now …]                                              /api/priority 응답 그대로 (JSON)

과제·내가 체크함·소요시간은 F6 원장(F6_Eclass_agent/data/eclass.db)을 읽기만 한다. 과제별 소요시간 수정은 화면이나
F6 의 PATCH /api/assignments/{id} 로 한다 — F7 은 설정 파일(data/settings.json) 말고는 아무것도 쓰지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from typing import Optional

from . import config as C
from . import rules, service, sources
from . import settings as S


def _now(s: Optional[str]) -> datetime:
    if not s:
        return datetime.now()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        raise SystemExit(f"--now 는 2026-10-06T14:00 모양이어야 합니다: {s}")


def _overview(args) -> dict:
    now = _now(getattr(args, "now", None))
    start = (now - timedelta(days=1)).date().isoformat()
    end = (now + timedelta(days=1)).date().isoformat()
    return service.overview(sources.assignments(), now, S.load(), sources.events(start, end),
                            sources.study_minutes(), getattr(args, "course", None))


def _problems() -> None:
    for p in sources.problems:
        print(f"  ! {p}", file=sys.stderr)


def _today_line(t: dict) -> str:
    return (f"오늘 남은 {rules.fmt_hours(t['leftHours'])} (취침 {t['bedTime']}까지 {rules.fmt_hours(t['untilBedHours'])}"
            f" − 수업·일정 {rules.fmt_hours(t['busyHours'])} − 공부 {rules.fmt_hours(t['studyHours'])})")


def cmd_list(args) -> int:
    ov = _overview(args)
    _problems()
    if not ov["items"]:
        print("마감이 남은 과제가 없습니다")
        return 0
    for g in ov["groups"]:
        rows = [r for r in ov["items"] if r["group"] == g["key"]]
        if not rows:
            if g["key"] == "now":
                print("\n■ 지금 해야 함 — 지금 해야 할 과제가 없습니다")
            continue
        head = f"\n■ {g['label']} {g['count']}"
        if g["key"] == "now":
            t = ov["today"]
            head += f" · 합계 {rules.fmt_hours(g['totalHours'])}  [{_today_line(t)}{' — 빠듯합니다' if t['over'] else ''}]"
        if g["staleCount"] and not args.all:
            head += f"  (2주 넘게 지난 {g['staleCount']}건 접음 — --all 로 보기)"
        print(head)
        for r in rows:
            if r.get("stale") and not args.all:
                continue
            est = rules.fmt_hours(r["estimatedHours"]) + ("*" if r["estimateSource"] == "user" else "")
            due = (r.get("due") or "")[:16].replace("T", " ") or "마감 없음"
            slack = "-" if r["slackHours"] is None else f"{r['slackHours']:.1f}h"
            print(f"  {r['rank']:>2}. [{r['kindLabel']}] {r['title']}  — {r['courseShort']}")
            print(f"      {r['reason']}   (마감 {due} · 소요 {est} · 여유 {slack})")
    print("\n(* = 직접 입력한 소요시간)")
    return 0


def cmd_top(args) -> int:
    b = service.brief(sources.assignments(), n=args.n)
    _problems()
    if not b["items"]:
        print("지금 급한 과제가 없습니다")
        return 0
    for i, r in enumerate(b["items"], 1):
        print(f"{i}. {r['title']}  {r['courseShort']}  {r['reason']}")
    print(f"총 {b['totalText']}" + (f" · 놓친 마감 {b['overdue']}건" if b["overdue"] else ""))
    return 0


def cmd_today(args) -> int:
    t = _overview(args)["today"]
    _problems()
    print(_today_line(t))
    print(f"지금 해야 함 합계 {rules.fmt_hours(t['needHours'])}" + (" — 오늘 다 하기는 빠듯합니다" if t["over"] else ""))
    for b in t["busy"]:
        print(f"  - {b['start'][11:]}~{b['end'][11:]} {b['title']} ({b['kind']})")
    return 0


def cmd_settings(args) -> int:
    patch: dict = {}
    if args.safety is not None:
        patch["safetyFactor"] = args.safety
    if args.hours:
        dh = {}
        for kv in args.hours:
            k, _, v = kv.partition("=")
            if k not in C.KINDS or not v:
                raise SystemExit(f"--hours 는 {'·'.join(C.KIND_ORDER)}=시간 모양이어야 합니다: {kv}")
            dh[k] = float(v)
        patch["defaultHours"] = dh
    if args.bed:
        patch["bedTime"] = args.bed
    try:
        v = S.save(patch, reset=args.reset) if (patch or args.reset) else S.view()
    except S.Invalid as e:
        print(f"설정을 바꾸지 못했습니다: {e}", file=sys.stderr)
        return 1
    print(f"안전계수 {v['safetyFactor']}  ·  취침 {v['bedTime']}")
    print("기본 소요시간: " + " · ".join(f"{k['label']} {rules.fmt_hours(v['defaultHours'][k['key']])}" for k in v["kinds"]))
    if v["changed"]:
        print("기본값에서 바꾼 것: " + ", ".join(v["changed"]))
    return 0


def cmd_json(args) -> int:
    print(json.dumps(_overview(args), ensure_ascii=False, indent=2))
    _problems()
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="cli.py tasks", description="F7 과제 우선순위 (급한 순 · 오늘 남은 시간 · 설정)")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("list", help="급한 순 목록")
    p.add_argument("--course")
    p.add_argument("--now")
    p.add_argument("--all", action="store_true", help="2주 넘게 지난 놓친 마감도 보이기")
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("top", help="먼저 할 것 N건")
    p.add_argument("-n", type=int, default=C.TOP_N)
    p.set_defaults(fn=cmd_top)

    p = sub.add_parser("today", help="오늘 남은 시간")
    p.add_argument("--now")
    p.set_defaults(fn=cmd_today)

    p = sub.add_parser("settings", help="설정 보기·바꾸기")
    p.add_argument("--safety", type=float)
    p.add_argument("--hours", nargs="+", metavar="KIND=H")
    p.add_argument("--bed")
    p.add_argument("--reset", action="store_true")
    p.set_defaults(fn=cmd_settings)

    p = sub.add_parser("json", help="/api/priority 응답 그대로")
    p.add_argument("--course")
    p.add_argument("--now")
    p.set_defaults(fn=cmd_json)

    args = ap.parse_args(argv)
    if not getattr(args, "fn", None):
        args = ap.parse_args(["list", *(argv or [])])
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
