"""테스트 공통 — 임시 data/ 와 **가짜 e클래스 게시판**을 쓴다.

내 시험·계획(F5_Test_agent/data)도, e클래스 수집분(F6_Eclass_agent/data)도, 강의자료 목록(F4)도 건드리지 않는다.
네트워크에 닿는 코드가 아예 없다 — F5 는 파일을 내려받지 않는다(수집은 F6, 로그인은 C3).

기본값으로 **F4·F3·F1 을 못 읽는 상태**를 만든다 — 자료가 없어도 계획을 만들 수 있어야 하고(F5-R11),
학사일정이 없으면 임의 시험 일정을 만들지 않는다. 쪽수 자동 채움은 `materials`, 임의 일정은 `semester` 픽스처로 따로 시험한다.
"""
import json
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f5test_"))
os.environ["F5_DATA_DIR"] = str(_TMP / "f5data")
os.environ["F6_AGENT_DIR"] = str(_TMP / "eclass")
os.environ["F4_AGENT_DIR"] = str(_TMP / "no-f4")
os.environ["F1_DATA_DIR"] = str(_TMP / "f1")          # 학사일정 — 기본은 없음(임의 일정을 만들지 않는다)
os.environ["F3_AGENT_DIR"] = str(_TMP / "no-f3")      # 출결 수업 회차 — 기본은 없음
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

TODAY = date(2026, 10, 13)          # 요구사항정의서 F5 5절 예시의 '오늘'

COURSES = [
    {"id": "74245", "name": "운영체제[2] (CIS2001)", "short": "운영체제", "code": "CIS2001", "section": "2",
     "color": "#4f46e5"},
    {"id": "74261", "name": "소프트웨어공학론[1] (CIS3030)", "short": "소프트웨어공학론", "code": "CIS3030",
     "section": "1", "color": "#d97706"},
]


def courses() -> list[dict]:
    return COURSES


def make_eclass(posts=()) -> None:
    """F6 수집기가 쓰는 모양 그대로 — data/manifest.json(posts) + data/<과목>/게시판/<게시판>/<날짜>_<제목>.md.

    posts = [(과목 id, 작성일 'YYYY-MM-DD HH:MM', 제목, 본문)]
    작성일을 `':\\r\\n\\t\\t\\t\\t2026-09-6 21:30'` 처럼 **0 없는 날짜**로 넣는 것은 실제 manifest 가 그렇기 때문이다.
    """
    from exams import config as C
    root = C.ECLASS_ROOT
    out = {}
    for i, (cid, posted, title, body) in enumerate(posts):
        rel = f"data\\과목{cid}\\게시판\\공지사항 게시판\\{posted[:10]}_{i}.md"
        path = root / rel.replace("\\", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([f"# {title}", "", f"- 과목: {cid}", "- 게시판: 공지사항 게시판",
                                   "- 작성자: 교수", f"- 작성일: :\r\n\t\t\t\t{posted}",
                                   f"- 링크: https://sel.jnu.ac.kr/{i}", "", "## 본문", "", body, ""]),
                        encoding="utf-8")
        out[f"1000:{i}"] = {"url": f"https://sel.jnu.ac.kr/{i}", "path": rel, "title": title,
                            "date": f":\r\n\t\t\t\t{posted}", "course_id": cid,
                            "activity": "공지사항 게시판", "attachments": []}
    C.ECLASS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    C.ECLASS_MANIFEST.write_text(json.dumps({"files": {}, "posts": out}, ensure_ascii=False), encoding="utf-8")
    from exams import notices
    notices._cache.update(key=None, value=None)


@pytest.fixture()
def db():
    """빈 exams.db + 빈 e클래스 게시판."""
    from exams import academic, classes, config as C, scope, store
    make_eclass()
    scope.reset()
    classes.reset()
    academic.reset_cache()
    if C.F1_DB.exists():
        C.F1_DB.unlink()
    for p in C.DB_PATH.parent.glob("exams.db*"):
        p.unlink()
    store._initialized.clear()
    with store.connect() as con:
        yield con


@pytest.fixture()
def materials(monkeypatch):
    """F4 자료 목록을 흉내낸다 — `scope` 가 F4 를 읽는 자리만 갈아 끼운다.

    (F4 를 실제로 물려 보는 것은 F4 쪽 테스트의 일이다. 여기서는 쪽수 합계 규칙만 본다.)
    """
    from exams import scope
    rows = [
        _m("mt:a", "1강", week=1, pages=30),
        _m("mt:b", "2강", week=2, pages=40),
        _m("mt:c", "3강", week=3, pages=50),
        _m("mt:d", "4강 (쪽수 못 셈)", week=4, pages=None),
        _m("mt:e", "5강", week=5, pages=25),
        _m("mt:f", "1강 사본", week=1, pages=30, dupOf="mt:a"),     # 중복은 두 번 세지 않는다
        _m("mt:g", "지운 파일", week=6, pages=99, missing=True),      # 사라진 파일은 세지 않는다
    ]
    monkeypatch.setattr(scope, "_rows", lambda course_id: list(rows) if course_id == "74261" else [])
    monkeypatch.setattr(scope, "available", lambda: True)
    monkeypatch.setattr(scope, "error", lambda: None)
    return rows


def _m(mid, title, week, pages, dupOf=None, missing=False) -> dict:
    return {"id": mid, "title": title, "week": week, "weekGuess": False, "pages": pages,
            "kind": "lecture", "ext": ".pdf", "activity": f"{title} 파일", "missing": missing,
            "dupOf": dupOf, "state": "pending"}


def add_exam(con, when="2026-10-23", etype="midterm", course="74261", **kw):
    """시험 한 줄 (수기) — 계획 시험에 쓰는 최소 입력."""
    from exams import service
    body = {"courseId": course, "type": etype, "date": when, **kw}
    return service.add_exam(con, body, courses, today=TODAY)


# ---------------------------------------------------------------- 학사일정 · 수업 회차 (임의 시험 일정)

# 2026-10-01 실측 학사일정에서 F5 가 쓰는 행 + 섞여 있던 학과 공지 행(걸러야 한다)
F1_ITEMS = [
    ("제2학기 개강", "2026-09-01", None),
    ("제2학기 종강", "2026-12-21", None),
    ("제2학기 중간 수업평가", "2026-10-12", "2026-10-23"),
    ("제2학기 중간고사", "2026-10-19", "2026-10-23"),
    ("제2학기 최종 수업평가", "2026-12-15", "2026-12-31"),
    ("제2학기 기말고사", "2026-12-15", "2026-12-21"),
    ("중간고사 시험기간 302호, 402호 강의실, 스튜던트라운지 룸 1,2 열람", "2026-10-13", "2026-10-24"),
]


def make_f1(items=F1_ITEMS):
    import sqlite3
    from exams import academic, config as C
    C.F1_DB.parent.mkdir(parents=True, exist_ok=True)
    if C.F1_DB.exists():
        C.F1_DB.unlink()
    con = sqlite3.connect(C.F1_DB)
    con.execute("CREATE TABLE items (title TEXT, start_date TEXT, end_date TEXT, removed_at TEXT)")
    con.executemany("INSERT INTO items VALUES (?, ?, ?, NULL)", items)
    con.commit()
    con.close()
    academic.reset_cache()


def weekly_sessions(weekdays, start, end, times):
    """F3 회차 모양 — weekdays 는 0=월. times = {요일: (시작, 끝)}"""
    from datetime import date, timedelta
    d, last, out = date.fromisoformat(start), date.fromisoformat(end), []
    while d <= last:
        if d.weekday() in weekdays:
            s, e = times[d.weekday()]
            out.append({"date": d.isoformat(), "weekday": d.weekday(), "start": s, "end": e})
        d += timedelta(days=1)
    return out


# 운영체제 월·수 13:00 · 소프트웨어공학론 화·목 15:00 (2026-2 실측 시간표)
SESSIONS = {
    "74245": weekly_sessions({0, 2}, "2026-09-01", "2026-12-21", {0: ("13:00", "14:50"), 2: ("13:00", "13:50")}),
    "74261": weekly_sessions({1, 3}, "2026-09-01", "2026-12-21", {1: ("15:00", "16:15"), 3: ("15:00", "16:15")}),
}


@pytest.fixture()
def semester(monkeypatch):
    """학사일정(F1) + 수업 회차(F3)가 있는 상태 — 임의 시험 일정이 잡힌다."""
    from exams import classes
    make_f1()
    data = {k: list(v) for k, v in SESSIONS.items()}
    monkeypatch.setattr(classes, "sessions", lambda sid: data)
    monkeypatch.setattr(classes, "stamp", lambda: ("fake", len(str(data))))
    return data
