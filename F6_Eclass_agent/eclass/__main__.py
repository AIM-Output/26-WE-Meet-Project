"""F6 e클래스 명령줄.

수집 (playwright 가 있는 python — 앱 실행 파일 --run-module eclass · 개발 venv `desktop/cli.py eclass`)
    python -m eclass sync [--dry-run] [--course ID ...] [--only files,boards,assign,deadlines] [--source manual|button] [--log FILE]
    python -m eclass tick [--force] [--log FILE]          작업 스케줄러용 — 이번 주기를 이미 돌았으면 건너뛰고, 네트워크 오류면 재시도

보기 (표준 라이브러리만 — `desktop/cli.py eclass`)
    python -m eclass list [--tab open|done|past]          과제 목록
    python -m eclass runs [-n 10]                         실행 이력
    python -m eclass status                               요약 · 연속 실패 · 다음 주기 · 앞으로 울릴 알림
    python -m eclass reconcile                            수집 JSON 을 원장에 다시 반영 (부분 반영 — 사라짐 판정 안 함)
    python -m eclass interval [2|4|6|12]                  주기 보기·바꾸기 (작업 스케줄러는 register-task.ps1 로 다시 등록)

종료 코드 (sync · tick): 0 성공 · 1 오류 · 2 로그인 필요 · 3 다른 실행이 진행 중 · 4 네트워크 오류
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime

from . import config as C


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="python -m eclass", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("sync")
    s.add_argument("--dry-run", action="store_true", help="파일·글은 내려받지 않고 목록만 (메타데이터 JSON 은 갱신)")
    s.add_argument("--course", action="append", metavar="ID", help="특정 과목 id만 (여러 번 지정 가능)")
    s.add_argument("--only", metavar="PARTS", help="쉼표 구분: files,boards,assign,deadlines")
    s.add_argument("--source", default="manual", choices=["manual", "button"])
    s.add_argument("--log", metavar="FILE", help="출력을 이 파일에 덧붙인다 (실행마다 ======== 시각 ======== 머리줄)")
    t = sub.add_parser("tick")
    t.add_argument("--force", action="store_true", help="이번 주기를 이미 돌았어도 한 번 더")
    t.add_argument("--log", metavar="FILE")
    li = sub.add_parser("list")
    li.add_argument("--tab", choices=["open", "done", "past"])
    ru = sub.add_parser("runs")
    ru.add_argument("-n", type=int, default=10)
    sub.add_parser("status")
    sub.add_parser("reconcile")
    iv = sub.add_parser("interval")
    iv.add_argument("hours", nargs="?", type=int, choices=list(C.INTERVAL_CHOICES))
    a = ap.parse_args(argv)

    if a.cmd in ("sync", "tick"):
        from . import runner
        if a.log:
            runner.redirect_output(a.log)
            print(f"======== {datetime.now():%Y-%m-%d %H:%M:%S} ========")
        if a.cmd == "tick":
            return runner.tick(force=a.force)
        only = set(a.only.split(",")) if a.only else None
        if only and (bad := only - {"files", "boards", "assign", "deadlines"}):
            print("--only 값 오류:", ", ".join(sorted(bad)))
            return C.EXIT_ERROR
        return runner.sync(a.source, dry_run=a.dry_run, courses=a.course, only=only)

    from . import notify, reconcile, schedule, service, store
    from . import runs as R
    if a.cmd == "list":
        with store.connect() as con:
            service.ensure_reconciled(con)
            out = service.list_assignments(con, a.tab)
        print(f"진행 중 {out['counts']['open']} · 완료 {out['counts']['done']} · 지난 마감 {out['counts']['past']}")
        for x in out["items"]:
            mark = "✓" if x["submitted"] else ("☑" if x["userDone"] else " ")
            chg = f"  (변경: {x['changed']['before'][:16]} →)" if x["changed"] else ""
            print(f" {mark} {(x['due'] or '마감 없음')[:16]:16s}  {x['courseShort'][:14]:14s} {x['type']:4s} {x['title'][:40]}{chg}")
        return 0
    if a.cmd == "runs":
        for r in R.list_runs(a.n):
            print(f" {r.get('started_at', '')[:16]}  {r.get('source', ''):8s} #{r.get('attempt', 1)}  코드 {r.get('exit_code')}"
                  f"  {r.get('duration_s', '?')}초  {json.dumps(r.get('counts') or {}, ensure_ascii=False)}  {r.get('error') or ''}")
        return 0
    if a.cmd == "status":
        with store.connect() as con:
            service.ensure_reconciled(con)
            summ = service.summary(con)
            plan = notify.planned(con)[:8]
        run_list = R.list_runs(30)
        iv = R.settings()["intervalHours"]
        print(json.dumps({**summ, "streak": R.failure_streak(run_list), "retry": R.pending_retry(), "intervalHours": iv,
                          "nextSlot": schedule.next_slot(datetime.now(), iv).isoformat(timespec="minutes"),
                          "planned": plan}, ensure_ascii=False, indent=2))
        return 0
    if a.cmd == "reconcile":
        with store.connect() as con:
            print(json.dumps(reconcile.apply(con, full=False, force=True), ensure_ascii=False))
        return 0
    if a.cmd == "interval":
        if a.hours:
            R.save_settings(intervalHours=a.hours)
            print(f"주기 {a.hours}시간으로 저장했습니다. 작업 스케줄러에 반영하려면:"
                  f" powershell -ExecutionPolicy Bypass -File .\\register-task.ps1 -IntervalHours {a.hours}")
        else:
            iv = R.settings()["intervalHours"]
            print(f"주기 {iv}시간 — {', '.join(f'{h:02d}시' for h in schedule.slot_hours(iv))}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
