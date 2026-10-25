"""F11 명령줄 — `desktop/cli.py scholarship …` 로 부른다 (개발 venv).

    cli.py scholarship sync [--source jnu_scholarship …] [--dry-run] [--college 'AI융합대학' --dept 인공지능학부]
                                                     공지 수집 (앱은 06·18시·켜질 때 자동으로, 화면 '지금 수집'으로도)
    cli.py scholarship sources [--college … --dept …]  원천 목록 — 내 소속에 맞는지 · 켜져 있는지 · 마지막 수집
    cli.py scholarship list [--all] [--json]          판정 목록 (해당 → 확인 필요 → … , 프로필은 C2 에서 읽는다)
    cli.py scholarship show <id>                      한 건 — 조건별 근거 · 요건 추출값
    cli.py scholarship catalog                        상시 장학 안내만 다시 받기

프로필은 C2_Profile_agent 의 DB 에서 읽는다(대시보드와 같은 값). --college/--dept/--major 를 주면 그 값으로 바꿔 본다.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import config as C
from . import registry, service, store


def _c2_profile() -> Optional[dict]:
    """C2 프로필(민감정보 포함) — 명령줄 전용. 대시보드에서는 백엔드가 넘겨준다."""
    import os
    from pathlib import Path
    c2 = Path(os.environ.get("C2_AGENT_DIR") or C.PROJECT_ROOT / "C2_Profile_agent")
    if str(c2) not in sys.path:
        sys.path.append(str(c2))
    try:
        from student import service as s2, store as st2      # type: ignore[import-not-found]
        with st2.connect() as con:
            doc = s2.get(con)
        return doc["profile"] if doc["exists"] else None
    except Exception as e:                                   # noqa: BLE001
        print(f"  ! C2 프로필을 읽지 못했습니다: {e}", file=sys.stderr)
        return None


def _profile(a) -> dict:
    p = dict(_c2_profile() or {})
    for k in ("college", "dept", "major"):
        v = getattr(a, k, None)
        if v:
            p["department" if k == "dept" else k] = v
    return p


def cmd_sync(a) -> int:
    from . import collect
    return collect.run(a.source, _profile(a), by=a.by, dry_run=a.dry_run)


def cmd_catalog(a) -> int:
    from . import collect
    return collect.run(["jnu_catalog"], _profile(a), by="manual", force_catalog=True)


def cmd_sources(a) -> int:
    p = _profile(a)
    with store.connect() as con:
        rows = service.source_rows(con, p)
    for g in ("school", "office", "project", "mine"):
        print(f"\n[{registry.load()['groups'][g]}]")
        for r in [r for r in rows if r["group"] == g]:
            on = "켬" if r["enabled"] else "끔"
            last = r["lastOkAt"] or "-"
            print(f"  {on} {r['key']:16s} {r['relevance']['level']:13s} {r['name'][:38]:38s} 최근 {last[:16]} · {r['relevance']['why'][:40]}")
    return 0


def cmd_list(a) -> int:
    p = _profile(a)
    with store.connect() as con:
        ov = service.overview(con, p)
    if a.json:
        print(json.dumps(ov, ensure_ascii=False, indent=1))
        return 0
    for it in ov["items"]:
        if not a.all and it["verdict"] in ("ineligible", "expired", "not_applicable"):
            continue
        dd = f"D-{it['daysLeft']}" if it["daysLeft"] is not None and it["daysLeft"] >= 0 else (it["deadline"] or "")[:10]
        print(f"  {it['label']:6s} {dd:>10s}  {it['title'][:60]:60s} {it.get('hint') or ''}")
    print("\n", ov["counts"])
    return 0


def cmd_show(a) -> int:
    with store.connect() as con:
        d = service.detail(con, a.id, _profile(a))
    if not d:
        print("없습니다", file=sys.stderr)
        return 1
    print(f"{d['title']}\n{d['url']}\n판정: {d['label']} · 신뢰도 {d['confidence']}")
    for r in d["reasons"]:
        print(f"  [{r['status']:7s}] {r['label']}: {r['message']}")
    print(json.dumps({k: v for k, v in d["requirements"].items() if k != "evidence"}, ensure_ascii=False, indent=1))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="scholarship", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def prof(sp):
        sp.add_argument("--college")
        sp.add_argument("--dept")
        sp.add_argument("--major")

    sp = sub.add_parser("sync"); prof(sp)
    sp.add_argument("--source", action="append")
    sp.add_argument("--dry-run", action="store_true")
    sp.add_argument("--by", default="manual", choices=("manual", "button", "schedule", "catchup"))
    sp.add_argument("--log", help="(대시보드가 붙인다 — 로그는 항상 state/sync.log 에도 남는다)")
    sp.set_defaults(fn=cmd_sync)
    sp = sub.add_parser("catalog"); prof(sp); sp.set_defaults(fn=cmd_catalog)
    sp = sub.add_parser("sources"); prof(sp); sp.set_defaults(fn=cmd_sources)
    sp = sub.add_parser("list"); prof(sp)
    sp.add_argument("--all", action="store_true")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("show"); prof(sp)
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
