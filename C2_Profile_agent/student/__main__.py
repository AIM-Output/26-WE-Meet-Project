"""C2 프로필 — 명령줄 (대시보드 없이 확인·관리할 때).

    python -m student show                         내 프로필 (민감정보는 '입력됨'으로만)
    python -m student set grade=3 track=single     항목 저장 (값은 JSON 으로 읽고, 안 되면 글자)
    python -m student dept <검색어>                 학과 마스터에서 찾기 (코드 확인용)
    python -m student set-dept <deptCode> [majorCode]
    python -m student import [--interactive]       학사정보시스템에서 가져오기 (C3_Login_agent 의 .venv 로 띄운다)
    python -m student master-sync [--year 2026]    교육과정검색에서 학과 목록 다시 받기
    python -m student export-notice                F11(notice_agent/data/profile.json)로 넘기기
    python -m student clear                        내 정보 전부 지우기
"""
from __future__ import annotations

import argparse
import json
import sys

from . import jobs, master, master_crawl, notice_bridge, schema, service, store


def _value(raw: str):
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m student", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show")
    s = sub.add_parser("set")
    s.add_argument("pairs", nargs="+", metavar="key=value")
    d = sub.add_parser("dept")
    d.add_argument("query")
    sd = sub.add_parser("set-dept")
    sd.add_argument("dept_code")
    sd.add_argument("major_code", nargs="?")
    i = sub.add_parser("import")
    i.add_argument("--interactive", action="store_true")
    m = sub.add_parser("master-sync")
    m.add_argument("--year", type=int)
    sub.add_parser("export-notice")
    sub.add_parser("clear")
    a = ap.parse_args(argv)

    try:
        if a.cmd == "show":
            with store.connect() as con:
                doc = service.get(con)
            p = doc["profile"]
            print(f"소속     {p['deptPath'] or '미입력'}{' (폐지·개편된 학과)' if p['affiliationRetired'] else ''}")
            for k, (sec, _, used, label, _) in schema.FIELDS.items():
                v = p[k]
                if v in (None, {}, []):
                    continue
                shown = "입력됨" if sec == "sensitive" else (f"{v['value']}/{v['scale']}" if isinstance(v, dict) and "scale" in v else v)
                src = {"auto": "자동", "user": "입력"}.get(doc["filledBy"].get(k, ""), "")
                print(f"{label:10} {shown}  [{src}{', 수정함' if k in doc['edited'] else ''}] ({'·'.join(used)})")
            print(f"필수 항목 {'모두 입력됨' if doc['complete'] else '빠짐: ' + ', '.join(doc['missing'])}")
            return 0
        if a.cmd == "set":
            data = {}
            for pair in a.pairs:
                k, _, v = pair.partition("=")
                data[k.strip()] = _value(v)
            with store.connect() as con:
                res = service.patch(con, data)
            print(f"바뀜: {', '.join(res['changed']) or '없음'}")
            return 0
        if a.cmd == "dept":
            q = "".join(a.query.split())
            for e in master.entries():
                if q in "".join(e["path"].split()):
                    print(f"  {e['deptCode']} {e['majorCode'] or '-':9} {e['path']}{' (폐지)' if e['retired'] else ''}")
            return 0
        if a.cmd == "set-dept":
            with store.connect() as con:
                service.patch(con, {"affiliation": {"deptCode": a.dept_code, "majorCode": a.major_code}})
                print(service.get(con)["profile"]["deptPath"])
            return 0
        if a.cmd == "import":
            problem = jobs.import_problem(a.interactive)
            if problem:
                print(problem)
                return 2
            st = jobs.run_import_blocking(a.interactive)
            if not st.get("ok"):
                print(st.get("error"))
                return 2 if st.get("needLogin") else 1
            r = st["result"]
            print(f"가져옴: {', '.join(r['found']) or '없음'} · 바뀜: {', '.join(r['changed']) or '없음'}"
                  f"{' · 건너뜀(내가 입력한 값): ' + ', '.join(r['skipped']) if r['skipped'] else ''}")
            return 0
        if a.cmd == "master-sync":
            new = master_crawl.crawl(a.year)
            old = master.load() if master.load().get("colleges") else None
            master.save_local(master.merge_retired(new, old))
            print(master.summary())
            return 0
        if a.cmd == "export-notice":
            with store.connect() as con:
                p = service.get(con)["profile"]
            print(f"저장: {notice_bridge.export(p)}")
            return 0
        if a.cmd == "clear":
            with store.connect() as con:
                service.delete_all(con)
            print("지웠습니다")
            return 0
    except schema.Invalid as e:
        print(f"저장하지 않았습니다: {e}")
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
