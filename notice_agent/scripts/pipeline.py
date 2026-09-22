"""전체 파이프라인 — 수집 → 추출 → 매칭 → 초안 → 알림 을 한 번에.  (기능명세서 DF-5)

    python -m scripts.pipeline                      # 신규 공지만 처리 (주기 실행용)
    python -m scripts.pipeline --pages 3 --all      # 처음 한 번: 과거 글까지 받고 전부 다시 추출
    python -m scripts.pipeline --skip-collect       # 수집 없이 추출부터 (프로필 바꾼 뒤 재판정)
    python -m scripts.pipeline --source jnu_home_scholarship --source aisw_dept
    python -m scripts.pipeline --no-draft           # 초안은 만들지 않고 판정·알림까지만

종료 코드: 0 정상 · 2 프로필 없음 · 3 수집 전부 실패
주기 실행은 register-task.ps1 (Windows 작업 스케줄러) 또는 서버의 cron/APScheduler 에서 이 명령을 호출한다.
"""
from __future__ import annotations

import argparse
import sys
import time

from . import config as C
from . import collect, draft, extract, match, notify


def run(sources=None, pages: int = C.LIST_PAGES, redo_all: bool = False, skip_collect: bool = False,
        do_draft: bool = True, deadline_days: int = 3, interactive: bool = False) -> int:
    t0 = time.time()
    C.ensure_dirs()
    if not C.PROFILE_FILE.exists():
        print(f"프로필이 없습니다: {C.PROFILE_FILE}\n  assets/profile.example.json 을 복사해 채우거나 "
              f"`python -m scripts.profile_from_hakstd` 를 실행하세요.")
        return 2

    new_ids: list[str] = []
    if not skip_collect:
        print("▶ 1/5 수집")
        rep = collect.collect(sources, pages, interactive=interactive)
        new_ids = rep["new"] + rep["updated"]
        if rep["errors"] and not (rep["new"] or rep["updated"] or rep["unchanged"]):
            print("수집이 전부 실패했습니다. 네트워크/사이트 구조를 확인하세요 (references/site-structure.md).")
            return 3

    print("\n▶ 2/5 자격 요건 추출")
    if redo_all:
        extract.run(None, redo=True)
    elif new_ids:
        extract.run(new_ids)
    else:
        extract.run(None)          # 아직 추출 안 된 것만

    print("\n▶ 3/5 프로필 매칭")
    ids = None if (redo_all or skip_collect) else (new_ids or None)
    match.run(None, ids)

    if do_draft:
        print("\n▶ 4/5 신청서 초안")
        draft.run(ids, redo=redo_all)
    else:
        print("\n▶ 4/5 신청서 초안 — 건너뜀 (--no-draft)")

    print("\n▶ 5/5 알림")
    notify.run(deadline_days)
    print(f"\n완료 ({time.time() - t0:.0f}초)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", action="append")
    ap.add_argument("--pages", type=int, default=C.LIST_PAGES)
    ap.add_argument("--all", action="store_true", help="이미 처리한 공지도 전부 다시 추출·판정·초안")
    ap.add_argument("--skip-collect", action="store_true")
    ap.add_argument("--no-draft", action="store_true")
    ap.add_argument("--deadline", type=int, default=3, help="D-N 이내 마감 리마인더 (기본 3)")
    ap.add_argument("--interactive", action="store_true", help="SSO 세션이 없으면 창을 띄워 직접 로그인")
    a = ap.parse_args(argv)
    return run(a.source, a.pages, a.all, a.skip_collect, not a.no_draft, a.deadline, a.interactive)


if __name__ == "__main__":
    sys.exit(main())
