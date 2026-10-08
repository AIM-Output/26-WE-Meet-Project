"""F8 공강 학습 플랜 명령줄 — `python -m placement <명령>` (run.cmd 가 부른다).

    preview  [--days 14] [--json]       배치 미리보기 (캘린더는 바뀌지 않는다)
    apply    [--days 14]                미리보기 그대로 등록 (자동 배치분만 새로 바뀐다)
    list     [--all]                    등록된 블록 (기본: 오늘부터)
    today                               오늘 블록
    conflicts                           겹친 블록
    clear    [--from D] [--to D]        자동 배치 블록 지우기 (고정·완료 제외)
    settings [--day 09:00-18:00] [--lunch on|off] [--buffer 10] [--block 30-120]
             [--weekend on|off] [--range 7|14] [--study on|off] [--reset]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, timedelta

from . import config as C
from . import service, sources, store
from . import settings as S


def _hm(m: int) -> str:
    h, r = divmod(int(m), 60)
    return f"{h}시간 {r}분" if h and r else f"{h}시간" if h else f"{r}분"


def _inputs(days: int) -> tuple[list[dict], list[dict], list[dict]]:
    t = date.today()
    first, last = (t - timedelta(days=C.TODO_LOOKBACK_DAYS)).isoformat(), (t + timedelta(days=days - 1)).isoformat()
    return sources.events(first, last), sources.exams(), sources.priority()


def _problems() -> None:
    for p in sources.problems:
        print(f"  ! {p}", file=sys.stderr)


def cmd_preview(a: argparse.Namespace) -> int:
    days = a.days or S.load()["rangeDays"]
    ev, st, pr = _inputs(days)
    with store.connect() as con:
        pv = service.preview(con, ev, st, pr, range_days=days)
    if a.json:
        print(json.dumps(pv, ensure_ascii=False, indent=2))
        return 0
    _problems()
    r = pv["range"]
    print(f"공강 배치 미리보기 {r['start']} ~ {r['end']} ({r['days']}일 · 낮 {pv['settings']['dayStart']}~{pv['settings']['dayEnd']}) — "
          f"새 블록 {len(pv['blocks'])}개 · {_hm(pv['totalMinutes'])} (공부 {_hm(pv['studyMinutes'])})")
    if pv["studyTargets"]:
        print("  공부 과목 순서 (남은 진도율 ÷ 남은 날수): " + ", ".join(
            f"{t['title']} {100 - int(t['percent'])}%·D-{t['dday']}" for t in pv["studyTargets"][:5]))
    if not pv["state"]["timetable"]:
        print("  (기간 안에 수업이 없습니다 — F3 시간표를 넣으면 수업 시간을 빼고 계산합니다)")
    if pv["existing"]:
        print(f"  이미 배치된 블록 {pv['existing']}개 — 자동 배치분만 다시 계산합니다")
    by_day: dict[str, list[dict]] = {}
    for b in pv["blocks"]:
        by_day.setdefault(b["date"], []).append(b)
    for d, tot in zip(pv["days"], pv["dailyTotals"]):
        print(f"\n{d['date']} ({d['weekday']})  합계 {_hm(tot['minutes'])}"
              + (f"  · 빈 시간 {', '.join(s['start'] + '~' + s['end'] for s in d['slots'])}" if d["slots"] else ""))
        for b in by_day.get(d["date"], []):
            kind = C.TASK_LABEL.get(b["taskType"], b["taskType"])
            print(f"  {b['start']}~{b['end']}  [{kind}] {b['title']}{' (' + b['part'] + ')' if b.get('part') else ''}  — {b['reason']}")
    if pv["unplaced"]:
        print(f"\n배치하지 못함 {len(pv['unplaced'])}건")
        for u in pv["unplaced"]:
            print(f"  - {u['text']}")
        for adj in pv["adjustments"]:
            print(f"  → {adj['label']}: {adj['text']}")
    for x in pv["deferred"]:
        print(f"  · {x['title']} — {x['text']}")
    return 0


def cmd_apply(a: argparse.Namespace) -> int:
    days = a.days or S.load()["rangeDays"]
    ev, st, pr = _inputs(days)
    with store.connect() as con:
        out = service.register(con, ev, st, pr, range_days=days)
    _problems()
    print(f"{out['created']}개 블록을 캘린더에 넣었습니다 (이전 자동 배치 {out['removed']}개는 바꿈) · 미배치 {out['unplaced']}건")
    return 0


def cmd_list(a: argparse.Namespace) -> int:
    with store.connect() as con:
        rows = store.rows(con, None if a.all else date.today().isoformat())
    if not rows:
        print("등록된 학습 블록이 없습니다")
        return 0
    for r in rows:
        tag = "완료" if r["done"] else "고정" if r["placed_by"] == "user" else "자동"
        print(f"pb:{r['id']:<4} {r['date']} {r['start']}~{r['end']}  [{tag}] {r['title']}  — {r['reason']}")
    return 0


def cmd_today(_: argparse.Namespace) -> int:
    with store.connect() as con:
        t = service.today(con)
    print(t["text"] or "오늘 남은 학습 블록이 없습니다")
    return 0


def cmd_conflicts(_: argparse.Namespace) -> int:
    t = date.today()
    ev = sources.events(t.isoformat(), (t + timedelta(days=60)).isoformat())
    refs = service.open_refs_of(sources.exams(False), sources.priority(), ev)
    with store.connect() as con:
        out = service.conflicts(con, ev, refs)
    _problems()
    if not out["items"]:
        print("겹친 블록이 없습니다")
    for b in out["items"]:
        print(f"{b['id']} {b['date']} {b['start']}~{b['end']} {b['title']} — {b['conflict']}")
    return 0


def cmd_clear(a: argparse.Namespace) -> int:
    with store.connect() as con:
        out = service.delete_auto(con, a.from_, a.to)
    print(f"자동 배치 블록 {out['deleted']}개를 지웠습니다 (남은 블록 {out['kept']}개 — 고정·완료·지난 것)")
    return 0


def _onoff(v: str) -> bool:
    if v.lower() in ("on", "켬", "1", "true", "yes"):
        return True
    if v.lower() in ("off", "끔", "0", "false", "no"):
        return False
    raise SystemExit(f"on 또는 off 로 주세요: {v}")


def cmd_settings(a: argparse.Namespace) -> int:
    patch: dict = {}
    if a.day:
        s, _, e = a.day.partition("-")
        patch.update({"dayStart": s, "dayEnd": e})
    if a.study:
        patch["fillStudy"] = _onoff(a.study)
    if a.lunch:
        patch["lunchBreak"] = _onoff(a.lunch)
    if a.buffer is not None:
        patch["bufferMinutes"] = a.buffer
    if a.block:
        lo, _, hi = a.block.partition("-")
        patch.update({"minSlotMinutes": int(lo), "maxBlockMinutes": int(hi)})
    if a.weekend:
        patch["useWeekend"] = _onoff(a.weekend)
    if a.range is not None:
        patch["rangeDays"] = a.range
    try:
        v = S.save(patch, reset=a.reset) if (patch or a.reset) else S.view()
    except S.Invalid as e:
        print(f"설정을 바꾸지 못했습니다: {e}", file=sys.stderr)
        return 2
    print(f"낮 시간대     {v['dayStart']} ~ {v['dayEnd']}  (저녁은 시험 공부 계획 몫 — F5 설정)")
    print(f"공부 블록     {'남는 공강을 채움' if v['fillStudy'] else '안 만듦'}")
    print(f"점심 제외     {v['lunchStart']} ~ {v['lunchEnd']}" if v["lunchBreak"] else "점심 제외     끔")
    print(f"수업 앞뒤 여유 {v['bufferMinutes']}분")
    print(f"블록 길이     {v['minSlotMinutes']}분 ~ {v['maxBlockMinutes']}분")
    print(f"주말 사용     {'켬' if v['useWeekend'] else '끔'}")
    print(f"배치 기간     {v['rangeDays']}일")
    print("하루 상한     없음 (2026-10-06)")
    if v["changed"]:
        print(f"(기본값과 다른 칸: {', '.join(v['changed'])} — {C.SETTINGS_FILE})")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="placement", description="F8 공강 기반 학습 플랜 자동 배치")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("preview", help="배치 미리보기")
    sp.add_argument("--days", type=int, choices=C.RANGE_DAYS_CHOICES)
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_preview)
    sp = sub.add_parser("apply", help="미리보기 그대로 등록")
    sp.add_argument("--days", type=int, choices=C.RANGE_DAYS_CHOICES)
    sp.set_defaults(fn=cmd_apply)
    sp = sub.add_parser("list", help="등록된 블록")
    sp.add_argument("--all", action="store_true")
    sp.set_defaults(fn=cmd_list)
    sub.add_parser("today", help="오늘 블록").set_defaults(fn=cmd_today)
    sub.add_parser("conflicts", help="겹친 블록").set_defaults(fn=cmd_conflicts)
    sp = sub.add_parser("clear", help="자동 배치 블록 지우기")
    sp.add_argument("--from", dest="from_")
    sp.add_argument("--to")
    sp.set_defaults(fn=cmd_clear)
    sp = sub.add_parser("settings", help="가용 시간 설정 보기·바꾸기")
    sp.add_argument("--day", help="09:00-18:00")
    sp.add_argument("--study", help="on|off — 남는 공강에 공부 블록")
    sp.add_argument("--lunch")
    sp.add_argument("--buffer", type=int)
    sp.add_argument("--block", help="30-120 (최소-최대 분)")
    sp.add_argument("--weekend")
    sp.add_argument("--range", type=int)
    sp.add_argument("--reset", action="store_true")
    sp.set_defaults(fn=cmd_settings)
    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except (service.Invalid, service.Stale, service.NotFound) as e:
        print(str(e), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
