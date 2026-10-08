"""명령줄 — 자료 목록을 눈으로 확인할 때. (대시보드 없이도 돈다)

    cli.py textbook scan [--force]     수집 폴더를 훑어 목록을 맞춘다 (--force: 쪽수·해시 다시 읽기)
    cli.py textbook list [과목]        자료 목록 (과목 이름 일부로 거를 수 있다)
    cli.py textbook courses            과목별 자료 수·쪽수
    cli.py textbook status             요약 한 줄 + 수집 폴더 위치
    cli.py textbook path <검색어>      파일 경로를 찍는다 (탐색기에서 열 때)
"""
from __future__ import annotations

import sys

from . import catalog, service, store

KIND_MARK = {"lecture": "강의", "board": "게시", "assignment": "과제", "upload": "직접"}


def _rows(con, needle: str | None):
    rows = store.all_rows(con)
    if needle:
        n = needle.lower()
        rows = [r for r in rows if n in (r["course"] or "").lower() or n in (r["title"] or "").lower()]
    return rows


def main(argv: list[str]) -> int:
    cmd = (argv[0] if argv else "status").lstrip("-")
    args = argv[1:]
    force = "--force" in args
    needle = next((a for a in args if not a.startswith("-")), None)

    with store.connect() as con:
        stats = catalog.scan(con, force=force and cmd == "scan")

        if cmd == "scan":
            print(f"자료 {stats['files']}개 — 새로 {stats['new']} · 바뀜 {stats['changed']} · 사라짐 {stats['removed']} "
                  f"· 보관 {stats['placed']} · 내려감 {stats['detached']} · 다시 읽음 {stats['reread']} "
                  f"· 중복 {stats['duplicates']} ({stats['elapsedMs']}ms)")
            return 0

        if cmd == "courses":
            for c in service.overview(con)["courses"]:
                if not c["files"]:
                    continue
                print(f"{c['short'][:24]:<26} 자료 {c['files']:>3}개 · {c['pages']:>5}쪽 · "
                      f"강의 {c['byKind']['lecture']} 게시 {c['byKind']['board']} 과제 {c['byKind']['assignment']} "
                      f"직접 {c['byKind']['upload']}" + (f" · 확인 {c['attention']}건" if c["attention"] else ""))
            return 0

        if cmd == "path":
            for r in _rows(con, needle):
                print(catalog.material_path(r))
            return 0

        if cmd == "list":
            course = ""
            for r in _rows(con, needle):
                if r["course"] != course:
                    course = r["course"]
                    print(f"\n[{course}]")
                pages = f"{r['pages']}쪽" if r["pages"] else "—"
                week = f"{r['week']}주" if r["week"] else "—"
                state = service.view(r)["stateLabel"]
                print(f"  {KIND_MARK.get(r['kind'], '?')} {week:>3} {pages:>5}  {state:<12} {r['title'][:52]}")
            return 0

        t = service.totals(store.all_rows(con))
        src = service.source_block()
        print(f"자료 {t['files']}개 · {t['pages']}쪽 · {t['sizeMB']}MB · 과목 {t['courses']}개"
              + (f" · 확인 필요 {t['attention']}건" if t["attention"] else ""))
        print(f"  종류: 강의자료 {t['byKind']['lecture']} · 게시판 첨부 {t['byKind']['board']} · "
              f"과제 첨부 {t['byKind']['assignment']} · 직접 추가 {t['byKind']['upload']}")
        keep = t["stored"]
        print(f"  보관함: {src['libraryDir']}"
              + (f" (하드링크 {keep['link']}" if keep.get("link") else " (")
              + (f" · 복사 {keep['copy']}" if keep.get("copy") else "")
              + (f" · 못 들여옴 {keep['eclass']}" if keep.get("eclass") else "") + ")")
        print(f"  수집 폴더(F6): {src['eclass']['dataDir']}"
              + (f" — 마지막 수집 {src['eclass']['manifestAt']}" if src["eclass"]["manifestAt"] else " — 아직 수집 전"))
        print(f"  직접 추가 폴더: {src['uploadDir']}"
              + (f" · e클래스에서 내려간 보관본 {t['detached']}건" if t["detached"] else ""))
        print("  요약·예상 문제·질문(RAG)은 아직 붙이지 않았습니다 — 1차는 자료 모으기·열람까지입니다.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
