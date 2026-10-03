"""F5 명령줄 — run.cmd 가 부른다 (표준 라이브러리만, fastapi 없이 돈다).

    run.cmd status                          시험 목록 · D-day · 계획 상태 · 오늘 분량
    run.cmd sync                            e클래스 공지에서 시험 찾기 (넣거나 갱신)
    run.cmd notices                         공지에서 읽힌 것만 보기 (저장하지 않는다)
    run.cmd show ex:74261:...                시험 하나 — 범위·근거·계획 옵션 기본값
    run.cmd add 소프트웨어공학론 midterm 2026-10-22 --time 15:00 --place 박물관   시험 직접 추가
    run.cmd scope 소프트웨어공학론 --weeks 1-5   범위 안 자료 쪽수 (F4)
    run.cmd preview ex:74261:... --difficulty hard --cap 180 --exclude 2026-10-15
                                            계획 미리보기 (저장하지 않는다)
    run.cmd plan ex:74261:... [같은 옵션]     계획 등록 (캘린더에 학습 블록 생성)
    run.cmd progress                        진행 중 계획의 진도 · 밀림
    run.cmd done pl:1 2026-10-13            그날 블록 완료 체크 (--undo 로 되돌리기)
    run.cmd rebalance pl:1                  재조정 미리보기
    run.cmd cancel pl:1                     계획 취소 (미완료 블록만 지운다)
    run.cmd events [--from 2026-10-01 --to 2026-10-31]   캘린더에 나갈 일정 (kind=exam·study)
    run.cmd courses                         과목별 시험 유무 + 중간·기말 상태 (임의 일정 포함)
    run.cmd course 산학협력 --no-midterm --no-final   시험을 안 보는 과목 끄기 (--midterm/--final 로 다시 켜기)
    run.cmd defaults [--date 2026-10-24]    임의 시험 일정을 지금 맞춘다 (날짜를 주면 그날인 것처럼)
    run.cmd clear                           시험·계획·진도 전부 지우기
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from typing import Any, Optional

from . import academic, defaults, notices, plan as P, scope, service, store
from . import config as C

_RANGE = re.compile(r"^(\d{1,2})\s*-\s*(\d{1,2})$")


def _courses() -> list[dict]:
    return list(service.course_map().values())


def _find_exam(con, needle: str) -> Any:
    """id 그대로 · 과목 이름 일부 + (유형) 로 찾는다."""
    rows = store.exam_rows(con)
    for r in rows:
        if r["id"] == needle:
            return r
    names = service.course_map()
    hit = [r for r in rows if needle in (names.get(r["course_id"], {}).get("short") or r["course"] or "")
           or needle in C.type_label(r["type"])]
    if not hit:
        raise service.NotFound(f"그런 시험이 없습니다: {needle}")
    if len(hit) > 1:
        print(f"여러 건이 맞습니다 — id 로 골라 주세요:", file=sys.stderr)
        for r in hit:
            print(f"  {r['id']}  {r['date']} {C.type_label(r['type'])} "
                  f"{names.get(r['course_id'], {}).get('short', r['course'])}", file=sys.stderr)
        raise service.Invalid("시험이 여러 건입니다")
    return hit[0]


def _course_id(needle: str) -> str:
    courses = service.course_map()
    if needle in courses:
        return needle
    hit = [c for c in courses.values() if needle in c["short"] or needle in c["name"]]
    if len(hit) != 1:
        raise service.Invalid(f"과목을 하나로 찾지 못했습니다: {needle} "
                              f"({', '.join(c['short'] for c in courses.values()) or '과목 목록이 없습니다'})")
    return hit[0]["id"]


def _weeks(raw: Optional[list[str]]) -> Optional[list[int]]:
    if not raw:
        return None
    out: set[int] = set()
    for item in raw:
        for part in str(item).split(","):
            part = part.strip()
            if m := _RANGE.match(part):
                out.update(range(int(m.group(1)), int(m.group(2)) + 1))
            elif part.isdigit():
                out.add(int(part))
    return sorted(out)


def _options(a) -> dict:
    o: dict[str, Any] = {}
    if getattr(a, "pages", None):
        o["totalPages"] = a.pages
        o["unit"] = "pages"
    if getattr(a, "minutes", None):
        o["totalMinutes"] = a.minutes
        o["unit"] = "minutes"
    if getattr(a, "difficulty", None):
        o["difficulty"] = a.difficulty
    if getattr(a, "cap", None):
        o["capMinutes"] = a.cap
    if getattr(a, "review", None) is not None:
        o["reviewDays"] = a.review
    if getattr(a, "exclude", None):
        o["excludedDates"] = a.exclude
    if getattr(a, "quiz", None) is not None:
        o["includeQuiz"] = True
        o["quizCount"] = a.quiz
    if weeks := _weeks(getattr(a, "weeks", None)):
        o["scopeWeeks"] = weeks
    return o


def _hm(minutes: int) -> str:
    h, m = divmod(int(minutes), 60)
    return f"{h}시간 {m}분" if h and m else (f"{h}시간" if h else f"{m}분")


# ---------------------------------------------------------------- 명령

def cmd_status(a) -> int:
    with store.connect() as con:
        o = service.overview(con, _courses, a.semester)
    sem = o["semester"]
    c = o["counts"]
    print(f"{sem['label']} — 시험 {c['total']}건 (다가옴 {c['upcoming']} · 지남 {c['past']}) · "
          f"확인 필요 {c['review']} · 진행 중 계획 {c['planned']} · 밀림 {c['behind']}")
    today = o["today"]
    print(f"오늘 공부: {today['text'] or '없음'}"
          + (f"   |  가장 가까운 시험 {today['nextExam']['course']} {today['nextExam']['typeLabel']} "
             f"{today['nextExam']['ddayLabel']}" if today["nextExam"] else ""))
    if not o["exams"] and not o["past"]:
        print("등록된 시험이 없습니다 — `run.cmd sync` 로 공지에서 찾거나 `run.cmd add` 로 직접 넣으세요")
    for e in o["exams"] + o["past"]:
        flag = " ⚠확인필요" if e["needsReview"] else ""
        when = f"{e['date']}({e['weekday']}) {e['time'] or '시각미정'}"
        print(f"- {e['ddayLabel']:>5}  {e['course']} {e['typeLabel']}  {when}  {e['place'] or ''}{flag}")
        sc = e["scope"]
        where = "·".join(f"{w}주" for w in sc["weeks"]) if sc["weeks"] else (sc["note"] or "미지정")
        print(f"         범위 {where} · {sc.get('autoNote') or '자료 —'}")
        if e["plan"]:
            pr = e["plan"]["progress"]
            print(f"         계획 {e['plan']['stateLabel']} — 진도 {pr['donePages']}/{pr['plannedPages']}쪽 "
                  f"({pr['percent']}%) {e['plan']['id']}")
            if e["plan"]["behind"]:
                print(f"         ⚠ {e['plan']['behindMessage']}")
        else:
            print(f"         계획 없음 — `run.cmd preview {e['id']}`")
        if e["changed"]:
            ch = e["changed"]
            print(f"         ⚠ 공지에서 날짜가 바뀌었습니다: {ch.get('from')} → {ch.get('to')}")
    for e in o["review"]:
        print(f"확인 필요: {e['course']} {e['typeLabel']} {e['date']} (신뢰도 {e['confidence']}) "
              f"← {(e['evidence'] or [{}])[0].get('quote', '')[:60]}")
    return 0


def cmd_sync(a) -> int:
    with store.connect() as con:
        out = service.sync_notices(con, get_courses=_courses)
    if not out["available"]:
        print(out.get("error") or "e클래스 공지를 읽을 수 없습니다", file=sys.stderr)
        return 1
    print(f"공지 {out['posts']}건을 읽었습니다 — 새 시험 {out['new']} · 갱신 {out['updated']} · "
          f"확인 필요 {out['reviewCount']}")
    for p in out["postponed"]:
        print(f"  ⚠ {p['course']} {p['typeLabel']} 날짜 변경: {p['from']} → {p['to']}")
    for h in out["hints"]:
        print(f"  ? {h['course']} '{h['noticeTitle']}' — {h['why']}")
    return 0


def cmd_notices(a) -> int:
    found = notices.load()
    if not found["available"]:
        print(f"e클래스 게시판 목록이 없습니다: {C.ECLASS_MANIFEST}", file=sys.stderr)
        return 1
    names = service.course_map()
    print(f"공지 {found['posts']}건에서 찾은 것 (저장하지 않았습니다)")
    for cid, slot in found["byCourse"].items():
        short = names.get(cid, {}).get("short", cid)
        for e in slot["exams"]:
            print(f"- {short} {C.type_label(e['type'])} {e['date']} {e['time'] or '시각미정'}"
                  f"{'~' + e['endTime'] if e['endTime'] else ''} {e['place'] or ''} "
                  f"(신뢰도 {e['confidence']} · {e['status']})")
            print(f"    근거 '{e['evidence'][0]['quote'][:70]}'")
            if e["scopeNote"] or e["scopeWeeks"]:
                print(f"    범위 {e['scopeWeeks'] or ''} {e['scopeNote']}")
        for h in slot["hints"]:
            print(f"- {short} ? '{h['noticeTitle']}' — {h['why']}")
    return 0


def cmd_show(a) -> int:
    with store.connect() as con:
        row = _find_exam(con, a.exam)
        out = service.detail(con, row["id"], _courses)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_add(a) -> int:
    body = {"courseId": _course_id(a.course), "type": a.type, "date": a.date}
    for key, v in (("time", a.time), ("place", a.place), ("scopeNote", a.note)):
        if v:
            body[key] = v
    if weeks := _weeks(a.weeks):
        body["scopeWeeks"] = weeks
    with store.connect() as con:
        e = service.add_exam(con, body, _courses)
    print(f"넣었습니다: {e['id']}  {e['course']} {e['typeLabel']} {e['date']} {e['time'] or '시각미정'}")
    return 0


def cmd_scope(a) -> int:
    cid = _course_id(a.course)
    info = scope.measure(cid, _weeks(a.weeks))
    print(f"{info['note']}  (자료 {info['files']}개 · 주차 {info['weeks']})")
    for m in info["materials"]:
        print(f"  {m['week'] or '—':>2}주  {m['pages'] or '—':>4}쪽  {m['title']}")
    return 0


def _print_days(days: list[dict], warnings=(), adjustments=(), verdict: str = "") -> None:
    for w in warnings:
        print(f"  {({'error': '✖', 'warn': '⚠'}).get(w['level'], '·')} {w['message']}")
    for d in days:
        if d["kind"] == "excluded":
            print(f"  {d['date']}({d['weekday']})  — 제외일")
            continue
        label = f"{d['pages']}쪽" if d["kind"] == "study" else "전체 복습"
        quiz = f" + 문제 {d['quiz']}개" if d["quiz"] else ""
        print(f"  {d['date']}({d['weekday']})  {label}{quiz} · {_hm(d['minutes'])}"
              f"{'  ✔' if d['done'] else ''}")
    real = [d for d in days if d["kind"] != "excluded"]
    print(f"  ─ 합계 {sum(d['pages'] for d in real)}쪽 · {_hm(sum(d['minutes'] for d in real))}"
          + (f" · 문제 {sum(d['quiz'] for d in real)}개" if any(d["quiz"] for d in real) else "")
          + (f"   [{verdict}]" if verdict else ""))
    for adj in adjustments:
        print(f"  조정안 · {adj['label']}: {adj['detail']}   {json.dumps(adj['apply'], ensure_ascii=False)}")


def cmd_preview(a) -> int:
    with store.connect() as con:
        row = _find_exam(con, a.exam)
        out = service.preview(con, row["id"], _options(a), get_courses=_courses)
    print(f"[미리보기 — 저장하지 않았습니다]  분량 원천: {out['scope']['note']}")
    print(f"{out['courseName']} {out['examTypeLabel']} {out['examDate']} — "
          f"학습일 {out['studyDays']}일 · 복습일 {out['reviewDays']}일 · 하루 {out['dailyPages']}쪽 "
          f"({_hm(out['dailyMinutes'])}) · 상한 {_hm(out['capMinutes'])}")
    _print_days(out["days"], out["warnings"], out["adjustments"], out["verdictLabel"])
    return 0


def cmd_plan(a) -> int:
    with store.connect() as con:
        row = _find_exam(con, a.exam)
        out = service.create_plan(con, row["id"], _options(a), get_courses=_courses)
    v, e = out["plan"], out["exam"]
    print(f"{out['message']}  ({v['id']})")
    print(f"{e['course']} {e['typeLabel']} {e['date']} — 하루 상한 {_hm(v['capMinutes'])} · "
          f"난이도 {v['difficultyLabel']}({v['pageMinutes']:g}분/쪽)")
    _print_days(v["days"], out["warnings"], (), out["verdictLabel"])
    return 0


def cmd_progress(a) -> int:
    with store.connect() as con:
        rows = store.plan_rows(con, state="active")
        if not rows:
            print("진행 중인 계획이 없습니다")
            return 0
        for p in rows:
            row = store.exam(con, p["exam_id"])
            if row is None:
                continue
            v = service.plan_view(p, store.days(con, p["id"]), row, date.today())
            e = service.exam_view(row, service.course_map(_courses), date.today())
            pr = v["progress"]
            print(f"{v['id']}  {e['course']} {e['typeLabel']} {e['date']} ({e['ddayLabel']})")
            print(f"  진도 {pr['donePages']}/{pr['plannedPages']}쪽 ({pr['percent']}%) · "
                  f"완료 {pr['doneDays']}/{pr['totalDays']}일 · 오늘 {pr['todayPages']}쪽")
            if v["behind"]:
                print(f"  ⚠ {v['behindMessage']}  → `run.cmd rebalance {v['id']}`")
    return 0


def cmd_done(a) -> int:
    with store.connect() as con:
        out = service.patch_day(con, service.parse_plan_id(a.plan), a.date, {"done": not a.undo},
                                get_courses=_courses)
    pr = out["plan"]["progress"]
    print(f"{a.date} {'되돌렸습니다' if a.undo else '완료했습니다'} — "
          f"진도 {pr['donePages']}/{pr['plannedPages']}쪽 ({pr['percent']}%)")
    if out["plan"]["behind"]:
        print(f"  ⚠ {out['plan']['behindMessage']}")
    return 0


def cmd_rebalance(a) -> int:
    with store.connect() as con:
        out = service.rebalance(con, service.parse_plan_id(a.plan), _options(a), get_courses=_courses)
    print(f"[재조정 미리보기 — 아직 적용하지 않았습니다]  "
          f"{out['rebalanceOf']['behindMessage'] or '밀린 진도가 없습니다'}")
    print(f"{out['courseName']} {out['examTypeLabel']} {out['examDate']} — "
          f"남은 학습일 {out['studyDays']}일 · 하루 {out['dailyPages']}쪽 "
          f"(이미 마친 {out['carried']['pages']}쪽은 뺐습니다)")
    _print_days(out["days"], out["warnings"], out["adjustments"], out["verdictLabel"])
    print(f"  적용: run.cmd plan {out['examId']}")
    return 0


def cmd_cancel(a) -> int:
    with store.connect() as con:
        out = service.cancel_plan(con, service.parse_plan_id(a.plan))
    print(out["message"])
    return 0


def cmd_events(a) -> int:
    with store.connect() as con:
        evs = service.calendar_events(con, a.from_, a.to, _courses)
    for e in sorted(evs, key=lambda x: x["start"]):
        p = e["extendedProps"]
        print(f"{e['start'][:16]:<16} [{p['kind']:5}] {e['title']}"
              + (f"  {p.get('place') or ''}" if p["kind"] == "exam" else
                 f"  {'✔' if p.get('done') else ''}"))
    print(f"— {len(evs)}건")
    return 0


def _print_courses(rows: list[dict]) -> None:
    for c in rows:
        parts = []
        for kind in C.DEFAULT_EXAM_TYPES:
            on = c[kind]
            e = c[f"{kind}Exam"]
            name = C.type_label(kind)
            if e:
                parts.append(f"{name} {e['date']}{' ' + e['time'] if e['time'] else ''} ({e['sourceLabel']})")
            elif on:
                parts.append(f"{name} 아직 없음")
            else:
                parts.append(f"{name} 안 봄")
        print(f"- {c['course']:<20} " + " · ".join(parts))


def cmd_courses(a) -> int:
    today = date.today()
    with store.connect() as con:
        made = defaults.ensure(con, today, _courses)
        rows = service.course_settings_view(con, service.course_map(_courses), today)
    per = defaults.period_view(academic.periods(service.semester_of(today)))
    print(f"{per['semester']} — 중간: {per['midterm']['label'] or '기간 없음'} · 기말: {per['final']['label'] or '기간 없음'}")
    _print_courses(rows)
    for h in made.get("hints", []):
        print(f"  ⚠ {h}")
    return 0


def cmd_course(a) -> int:
    body = {k: v for k, v in (("midterm", a.midterm), ("final", a.final)) if v is not None}
    with store.connect() as con:
        out = service.set_course_exams(con, _course_id(a.course), body, _courses)
    _print_courses([out["course"]])
    for x in out["created"]:
        print(f"  + {x['label']} {x['date']} {x['time'] or ''} (임의)")
    for x in out["removed"]:
        print(f"  - {x['label']} 임의 일정을 치웠습니다")
    return 0


def cmd_defaults(a) -> int:
    today = date.fromisoformat(a.date) if a.date else date.today()
    with store.connect() as con:
        out = defaults.ensure(con, today, _courses, force=True)
    print(f"{out['semester']} 기준 {today} — 새로 {len(out['created'])} · 옮김 {len(out['moved'])} · 치움 {len(out['removed'])}"
          f" · 시각 채움 {len(out.get('timed', []))}")
    for x in out.get("timed", []):
        print(f"  ⏱ {x['course']} {x['date']} → {x['time']} ({x['how']})")
    for x in out["created"]:
        print(f"  + {x['label']} {x['date']} {x['time'] or '시각 미정'}")
    for x in out["moved"]:
        print(f"  ~ {x['label']} {x['from']} → {x['to']}")
    for x in out["removed"]:
        print(f"  - {x['label']}")
    for h in out["hints"]:
        print(f"  ⚠ {h}")
    return 0


def cmd_clear(a) -> int:
    for p in C.DB_PATH.parent.glob("exams.db*"):
        p.unlink()
    store._initialized.clear()
    print("시험·학습 계획·진도를 지웠습니다")
    return 0


def _plan_args(p) -> None:
    p.add_argument("--pages", type=int, help="총 쪽수 (자료가 없을 때 직접 입력, F5-R11)")
    p.add_argument("--minutes", type=int, help="총 학습 시간(분) — 쪽수 대신")
    p.add_argument("--difficulty", choices=list(C.DIFFICULTY), help="난이도 (쪽당 1.5/2.5/4분)")
    p.add_argument("--cap", type=int, help="하루 상한(분, 기본 240)")
    p.add_argument("--review", type=int, help="마무리 복습일 (중간·기말 기본 2일)")
    p.add_argument("--exclude", action="append", metavar="YYYY-MM-DD", help="제외일 (여러 번)")
    p.add_argument("--quiz", type=int, metavar="N", help="마무리 복습일에 예상 문제 N개 풀이 포함")
    p.add_argument("--weeks", action="append", metavar="1-5", help="범위 주차 (`3-7` 또는 `3,4,5`)")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="exams", description="F5 시험 공부 일정 자동 추천")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("status", help="시험 목록 · 진도")
    p.add_argument("--semester")
    p.set_defaults(fn=cmd_status)
    sub.add_parser("sync", help="공지에서 시험 찾기").set_defaults(fn=cmd_sync)
    sub.add_parser("notices", help="공지에서 읽힌 것만 보기").set_defaults(fn=cmd_notices)
    sub.add_parser("progress", help="진행 중 계획의 진도").set_defaults(fn=cmd_progress)
    sub.add_parser("clear", help="전부 지우기").set_defaults(fn=cmd_clear)

    p = sub.add_parser("show", help="시험 하나 (JSON)")
    p.add_argument("exam")
    p.set_defaults(fn=cmd_show)

    p = sub.add_parser("add", help="시험 직접 추가")
    p.add_argument("course")
    p.add_argument("type", choices=list(C.TYPES))
    p.add_argument("date")
    p.add_argument("--time")
    p.add_argument("--place")
    p.add_argument("--note", help="범위 문구")
    p.add_argument("--weeks", action="append", metavar="1-5")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("scope", help="범위 안 자료 쪽수 (F4)")
    p.add_argument("course")
    p.add_argument("--weeks", action="append", metavar="1-5")
    p.set_defaults(fn=cmd_scope)

    for name, fn, helptext in (("preview", cmd_preview, "계획 미리보기 (저장 안 함)"),
                               ("plan", cmd_plan, "계획 등록 (캘린더에 학습 블록)")):
        p = sub.add_parser(name, help=helptext)
        p.add_argument("exam")
        _plan_args(p)
        p.set_defaults(fn=fn)

    p = sub.add_parser("rebalance", help="재조정 미리보기")
    p.add_argument("plan")
    _plan_args(p)
    p.set_defaults(fn=cmd_rebalance)

    p = sub.add_parser("done", help="그날 블록 완료 체크")
    p.add_argument("plan")
    p.add_argument("date")
    p.add_argument("--undo", action="store_true")
    p.set_defaults(fn=cmd_done)

    sub.add_parser("courses", help="과목별 시험 유무").set_defaults(fn=cmd_courses)
    p = sub.add_parser("course", help="과목 시험 유무 바꾸기")
    p.add_argument("course")
    p.add_argument("--midterm", dest="midterm", action="store_true", default=None)
    p.add_argument("--no-midterm", dest="midterm", action="store_false")
    p.add_argument("--final", dest="final", action="store_true", default=None)
    p.add_argument("--no-final", dest="final", action="store_false")
    p.set_defaults(fn=cmd_course)
    p = sub.add_parser("defaults", help="임의 시험 일정 맞추기")
    p.add_argument("--date", help="그날인 것처럼 (YYYY-MM-DD)")
    p.set_defaults(fn=cmd_defaults)

    p = sub.add_parser("cancel", help="계획 취소")
    p.add_argument("plan")
    p.set_defaults(fn=cmd_cancel)

    p = sub.add_parser("events", help="캘린더에 나갈 일정")
    p.add_argument("--from", dest="from_")
    p.add_argument("--to")
    p.set_defaults(fn=cmd_events)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except (service.Invalid, service.NotFound, service.Conflict, P.Invalid) as e:
        print(f"오류: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
