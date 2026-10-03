"""F2 명령줄 — run.cmd 가 부른다 (백엔드 .venv 의 python, 표준 라이브러리만).

    run.cmd status [--track single]     졸업까지 남은 학점 · 영역별 · 인증 (프로필은 C2 에서 읽는다)
    run.cmd courses                     이수 과목 (영역·제외 이유)
    run.cmd rulesets                    저장소의 기본 룰셋
    run.cmd import [--interactive]      학사정보시스템 기이수성적 가져오기 (C3_Login_agent 의 .venv·로그인 세션)
    run.cmd curriculum                  내 학과·전공·입학년도 교육과정 받기
    run.cmd curriculum 30001229 30001265 2024   단과대·학과(전공) 코드·연도를 직접
    run.cmd add "교내 AI 캠프(학점인정)" 2 --area free --year 2025 --semester 1
    run.cmd clear                       이수 내역·내 지정·수정본 전부 지우기
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional

from . import config as C
from . import curriculum, jobs, rules, service, store


def _profile() -> Optional[dict]:
    if str(C.C2_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C2_AGENT_DIR))
    try:
        from student import api as c2      # type: ignore[import-not-found]
        return c2.profile_for_matching()
    except Exception:                      # noqa: BLE001
        return None


def _apply_profile(fetched: dict) -> dict:
    if str(C.C2_AGENT_DIR) not in sys.path:
        sys.path.insert(0, str(C.C2_AGENT_DIR))
    from student import service as c2s, store as c2store   # type: ignore[import-not-found]
    with c2store.connect() as con:
        return c2s.apply_import(con, fetched)


def _fmt(x) -> str:
    return "—" if x is None else f"{x:g}" if isinstance(x, float) else str(x)


def cmd_status(a) -> int:
    p = _profile()
    with store.connect() as con:
        s = service.status(con, p, a.track)
    rs = s["ruleset"]
    print(f"기준: {rs['label']} ({rs['levelLabel']}){' · 내가 고침' if rs['edited'] else ''}")
    for w in rs["warnings"]:
        print(f"  ⚠ {w}")
    t = s["total"]
    print(f"판정: {s['verdict']}  —  총 {_fmt(t['earned'])}/{_fmt(t['required'])}학점, 더 들어야 할 학점 {_fmt(t['remaining'])}")
    if s["headline"]:
        print(f"  {s['headline']}")
    for a_ in s["areas"]:
        miss = f"  남은 과목: {', '.join(m['name'] for m in a_['missingCourses'])}" if a_["missingCourses"] else ""
        print(f"  {a_['label']:<6} {_fmt(a_['earned']):>5}/{_fmt(a_['required']):<4} 부족 {_fmt(a_['short'])}{miss}")
    for ch in s["checks"]:
        print(f"  [세부] {ch['label']:<12} {_fmt(ch['earned'])}/{_fmt(ch['required'])} {ch['state']}")
    for ce in s["certifications"]:
        print(f"  [인증] {ce['label']:<8} {ce['state']}{' — ' + ce['memo'] if ce['memo'] else ''}")
    if s["unmapped"]:
        print(f"  미분류 {len(s['unmapped'])}건: {', '.join(c['name'] for c in s['unmapped'][:8])}")
    for k, v in s["reasons"].items():
        if v:
            print(f"  ({k}) {' · '.join(v)}")
    print("※ 참고용 · 공식 졸업사정 아님 — 최종 확인은 학과 사무실·학사정보시스템에서")
    return 0


def cmd_courses(_a) -> int:
    with store.connect() as con:
        s = service.status(con, _profile())
    for c in s["courses"]:
        tag = "직접" if c["source"] == "manual" else "학사"
        note = f"  ✗ {c['excludedReason']}" if c["excluded"] else ""
        print(f"{_fmt(c['year'])}-{c['semester'] or '?':<3} [{tag}] {c['name']:<24} {_fmt(c['credits']):>4}학점 "
              f"{c['grade'] or '-':<3} {c['rawCategory'] or '':<6} → {c['area'] or '미분류'}{note}")
    print(f"{len(s['courses'])}과목 · 가져온 시각 {s['data']['importedAt'] or '없음'}")
    return 0


def cmd_rulesets(_a) -> int:
    for r in rules.listing():
        print(f"{r['id']:<28} {r['label']:<10} {r['department']} {r['major'] or ''} {r['totalCredits']}학점")
    return 0


def cmd_import(a) -> int:
    problem = jobs.import_problem(a.interactive)
    if problem:
        print(problem)
        return 2
    jobs.on_profile = _apply_profile
    st = jobs.run_import_blocking(a.interactive)
    print(json.dumps({k: st.get(k) for k in ("ok", "error", "needLogin", "result")}, ensure_ascii=False, indent=1))
    return 0 if st.get("ok") else 1


def cmd_curriculum(a) -> int:
    if a.college and a.code and a.year:
        college, codes, year = a.college, [a.code], a.year
    else:
        st = service.curriculum_state(_profile())
        college, codes, year = st["collegeCode"], st["codes"], st["year"]
    if not (college and codes and year):
        print("프로필에 단과대·학과·입학년도가 없습니다 — 코드를 직접 주세요: run.cmd curriculum <단과대> <학과> <연도>")
        return 2
    http = curriculum.Http()
    for code in codes:
        doc = curriculum.crawl(college, code, int(year), http=http)
        if doc["courses"]:
            print(f"  저장: {curriculum.save_local(doc)}")
    return 0


def cmd_add(a) -> int:
    with store.connect() as con:
        p = _profile()
        cid = service.add_manual(con, {"name": a.name, "credits": a.credits, "year": a.year, "semester": a.semester,
                                       "area": a.area, "grade": a.grade, "code": a.code}, service.area_keys(con, p))
    print(f"추가했습니다: {cid}")
    return 0


def cmd_clear(_a) -> int:
    with store.connect() as con:
        service.clear_all(con)
    print("이수 내역·내 지정·수정본·계획을 지웠습니다")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="graduation", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("status")
    s.add_argument("--track", choices=rules.TRACKS)
    sub.add_parser("courses")
    sub.add_parser("rulesets")
    s = sub.add_parser("import")
    s.add_argument("--interactive", action="store_true")
    s = sub.add_parser("curriculum")
    s.add_argument("college", nargs="?")
    s.add_argument("code", nargs="?")
    s.add_argument("year", nargs="?", type=int)
    s = sub.add_parser("add")
    s.add_argument("name")
    s.add_argument("credits", type=float)
    s.add_argument("--area")
    s.add_argument("--year", type=int)
    s.add_argument("--semester")
    s.add_argument("--grade", default="P")
    s.add_argument("--code")
    sub.add_parser("clear")
    a = ap.parse_args(argv)
    try:
        return {"status": cmd_status, "courses": cmd_courses, "rulesets": cmd_rulesets, "import": cmd_import,
                "curriculum": cmd_curriculum, "add": cmd_add, "clear": cmd_clear}[a.cmd](a)
    except (service.Invalid, rules.Invalid, service.NotFound, service.Conflict) as e:
        print(f"오류: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
