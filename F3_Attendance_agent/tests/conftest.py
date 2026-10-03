"""테스트 공통 — 임시 data/·state/, 가짜 학사일정 DB, 가짜 e클래스 게시판을 쓴다
(내 출결 기록·F1 학사일정·e클래스 공지를 건드리지 않는다). 실제 학사정보시스템에는 접속하지 않는다."""
import json
import os
import sqlite3
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f3test_"))
os.environ["F3_DATA_DIR"] = str(_TMP / "data")
os.environ["F3_STATE_DIR"] = str(_TMP / "state")
os.environ["F1_DATA_DIR"] = str(_TMP / "f1")
os.environ["F6_AGENT_DIR"] = str(_TMP / "eclass")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 10, 20, 12, 0)          # 2026-2학기 8주차 화요일 점심

# 2026-09-28 실측 학사일정(F1 items)에서 F3 가 쓰는 행만
F1_ROWS = [
    ("제2학기 개강", "vacation", "2026-09-01", None),
    ("제2학기 종강", "vacation", "2026-12-21", None),
    ("추석연휴 (휴업)", "holiday", "2026-09-24", "2026-09-25"),
    ("개천절 대체휴일 (휴업)", "holiday", "2026-10-05", None),
    ("한글날 (휴업)", "holiday", "2026-10-09", None),
    ("자체 보강일", "etc", "2026-12-08", None),
    ("10. 5.(월) 개천절 대체휴일 보강", "etc", "2026-12-09", None),
    ("9. 24.(목) 추석연휴 보강", "etc", "2026-12-10", None),
    ("9. 25.(금) 추석연휴 보강", "etc", "2026-12-11", None),
    ("10. 9.(금) 한글날 보강", "etc", "2026-12-14", None),
    ("제2학기 수업일수 1/4", "etc", "2026-09-29", None),
]


def make_f1(rows=F1_ROWS, removed=()):
    from attendance import config as C
    C.F1_DB.parent.mkdir(parents=True, exist_ok=True)
    if C.F1_DB.exists():
        C.F1_DB.unlink()
    con = sqlite3.connect(C.F1_DB)
    con.execute("CREATE TABLE items (ident TEXT PRIMARY KEY, title TEXT, type TEXT, start_date TEXT, end_date TEXT, "
                "removed_at TEXT)")
    for i, (t, ty, s, e) in enumerate(rows):
        con.execute("INSERT INTO items VALUES (?, ?, ?, ?, ?, ?)", (f"i{i}", t, ty, s, e, "x" if t in removed else None))
    con.commit()
    con.close()


def make_eclass(posts=()):
    """F6 수집기가 쓰는 모양 그대로 — data/manifest.json(posts) + data/<과목>/게시판/<게시판>/<날짜>_<제목>.md.
    posts = [(과목 id, 작성일 'YYYY-MM-DD HH:MM', 제목, 본문)]"""
    from attendance import config as C
    root = C.ECLASS_ROOT
    out = {}
    for i, (cid, posted, title, body) in enumerate(posts):
        rel = f"data\\과목{cid}\\게시판\\공지사항 게시판\\{posted[:10]}_{i}.md"
        path = root / rel.replace("\\", "/")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([f"# {title}", "", f"- 과목: {cid}", "- 게시판: 공지사항 게시판", "- 작성자: 교수",
                                   f"- 작성일: {posted}", f"- 링크: https://sel.jnu.ac.kr/{i}", "", "## 본문", "", body, ""]),
                        encoding="utf-8")
        out[f"1:{i}"] = {"url": f"https://sel.jnu.ac.kr/{i}", "path": rel, "title": title,
                         "date": f":\r\n\t\t\t\t{posted}", "course_id": cid, "activity": "공지사항 게시판"}
    C.ECLASS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    C.ECLASS_MANIFEST.write_text(json.dumps({"files": {}, "posts": out}, ensure_ascii=False), encoding="utf-8")
    from attendance import notices
    notices._cache.update(key=None, value=None)


@pytest.fixture()
def f1():
    make_f1()
    make_eclass()
    yield
    from attendance import config as C
    if C.F1_DB.exists():
        C.F1_DB.unlink()


@pytest.fixture()
def db(f1):
    from attendance import config as C, store
    for p in C.DB_PATH.parent.glob("attendance.db*"):
        p.unlink()
    store._initialized.clear()
    with store.connect() as con:
        yield con


ECLASS = [
    {"id": "74245", "name": "운영체제[2] (CIS2001)", "short": "운영체제", "code": "CIS2001", "section": "2", "color": "#4f46e5"},
    {"id": "74261", "name": "소프트웨어공학론[1] (CIS3030)", "short": "소프트웨어공학론", "code": "CIS3030", "section": "1",
     "color": "#d97706"},
]
OS_MEETINGS = [{"weekday": 0, "periods": [5, 6]}, {"weekday": 2, "periods": [5]}]      # 월5월6수5
SE_MEETINGS = [{"weekday": 1, "periods": [5]}, {"weekday": 3, "periods": [5]}]         # 화5목5


def session(day, kind="regular", state="scheduled", attendance=None, start="09:00", end="10:50", sid=None, cancel=None):
    """계산기 입력 한 줄 (회 = 날 하나)."""
    d = date.fromisoformat(day)
    return {"id": sid or f"cl:t:{day}{':mk' if kind == 'makeup' else ''}", "courseId": "t", "date": day,
            "weekday": d.weekday(), "periods": [1], "start": start, "end": end, "room": "", "kind": kind,
            "origin": "timetable", "state": state, "baseState": state, "autoCancel": None,
            "cancelSource": cancel if state == "canceled" else None, "makeupFor": None, "makeupName": None,
            "attendance": attendance, "memo": ""}


def weekly(first, weeks, **kw):
    d = date.fromisoformat(first)
    return [session((d + timedelta(weeks=i)).isoformat(), **kw) for i in range(weeks)]
