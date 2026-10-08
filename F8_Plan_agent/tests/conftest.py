"""테스트 공통 — 임시 data/ 를 쓴다. 내 학습 블록·설정(F8_Plan_agent/data)도, 다른 기능 데이터도 건드리지 않는다.

다른 기능 폴더는 **없는 자리**를 가리키게 한다 — F8 계산은 넘겨받은 일정·시험·순위만으로 돌아야 하고(service 는 자기 DB 만 연다),
명령줄의 sources.py 는 못 읽으면 problems 에 적고 빈 목록으로 계속해야 한다.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f8test_"))
os.environ["F8_DATA_DIR"] = str(_TMP / "f8data")
for k in ("F3_AGENT_DIR", "F5_AGENT_DIR", "F6_AGENT_DIR", "F7_AGENT_DIR", "C1_AGENT_DIR"):
    os.environ[k] = str(_TMP / f"no-{k.lower()}")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

# 화요일 — 수업 09:00~10:50, 13:00~14:50 (요구사항정의서 F8 5절 예시)
TUE = "2026-09-29"
WED, THU, FRI = "2026-09-30", "2026-10-01", "2026-10-02"
NOW = datetime(2026, 9, 29, 8, 0)


@pytest.fixture(autouse=True)
def clean():
    from placement import config as C
    for p in (C.SETTINGS_FILE, C.DB_PATH):
        if p.exists():
            p.unlink()
    yield
    for p in (C.SETTINGS_FILE, C.DB_PATH):
        if p.exists():
            p.unlink()


@pytest.fixture
def con():
    from placement import store
    with store.connect() as c:
        yield c


def spec(**kw):
    """계산 규칙 테스트의 설정 — 5절 예시 그대로 적는다(기본값을 또 바꿔도 규칙 테스트는 그대로)."""
    s = {"dayStart": "09:00", "dayEnd": "18:00", "lunchBreak": True, "lunchStart": "12:00", "lunchEnd": "13:00",
         "bufferMinutes": 10, "minSlotMinutes": 30, "maxBlockMinutes": 120, "useWeekend": False, "rangeDays": 7,
         "fillStudy": True}
    s.update(kw)
    return s


def cls(d, start, end, title="수업", canceled=False):
    """F3 수업 회차 (/api/events kind=class 모양)."""
    return {"id": f"cl:{title}:{d}:{start}", "title": title, "start": f"{d}T{start}:00", "end": f"{d}T{end}:00",
            "allDay": False, "extendedProps": {"kind": "class", "state": "canceled" if canceled else "normal"}}


def ev(d, start, end, title="내 일정", kind="user", **p):
    return {"id": f"u:{title}:{d}", "title": title, "start": f"{d}T{start}:00", "end": f"{d}T{end}:00" if end else None,
            "allDay": False, "extendedProps": {"kind": kind, **p}}


def todo(iid, d, title="할 일", done=False):
    """C1 할 일 — 날짜만 (종일)."""
    return {"id": str(iid), "title": title, "start": d, "end": None, "allDay": True,
            "extendedProps": {"kind": "user", "isTodo": True, "done": done}}


def tuesday_classes(d=TUE):
    return [cls(d, "09:00", "10:50", "운영체제"), cls(d, "13:00", "14:50", "소프트웨어공학론")]


def exam(eid, course, d, percent=0, time="", type_label="중간고사", auto=False):
    """F5 공강 공부 대상 (exams.api.study_targets 모양)."""
    return {"examId": eid, "course": course, "courseName": course, "color": "#4f46e5", "type": "midterm",
            "typeLabel": type_label, "title": type_label, "date": d, "time": time, "dday": 0,
            "isAuto": auto, "needsReview": False, "confirmed": not auto, "percent": percent, "planned": False,
            "href": f"/exams?exam={eid}"}


def task(iid, title, due, hours, slack=None, course="소프트웨어공학론", group="week", stale=False):
    """F7 순위 목록 한 줄 (/api/priority items 중 F8 이 읽는 칸)."""
    return {"id": iid, "title": title, "due": due, "neededHours": hours, "estimatedHours": hours,
            "slackHours": slack if slack is not None else 0.0, "group": group, "stale": stale,
            "courseShort": course, "courseColor": "#d97706"}
