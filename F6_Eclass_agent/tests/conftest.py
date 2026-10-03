"""테스트 공통 — 임시 data/·state/ 와 가짜 C3 폴더를 쓴다 (내 과제 원장·수업자료·로그인 세션을 건드리지 않는다).
e클래스에는 접속하지 않는다 — 수집(collect.run)은 가짜로 바꿔 끼운다. 작업 스케줄러도 건드리지 않는다(F6_TASKS=off)."""
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f6test_"))
os.environ["F6_DATA_DIR"] = str(_TMP / "data")
os.environ["F6_STATE_DIR"] = str(_TMP / "state")
os.environ["C3_AGENT_DIR"] = str(_TMP / "c3")
os.environ["F6_TASKS"] = "off"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

NOW = datetime(2026, 9, 28, 12, 0)           # 월요일 점심

COURSES = [
    {"id": "74245", "name": "운영체제[2] (CIS2001)", "url": "https://sel.jnu.ac.kr/course/view.php?id=74245", "activities": []},
    {"id": "78570", "name": "산학협력프로젝트(캡스톤디자인)[1] (SAI0029)", "url": "https://sel.jnu.ac.kr/course/view.php?id=78570",
     "activities": []},
]


def assign(cmid, due, submitted="제출 안 함", course=1, name=None, desc="설명", attachments=()):
    c = COURSES[course]
    return {"course_id": c["id"], "course": c["name"], "cmid": str(cmid), "name": name or f"과제{cmid}",
            "url": f"https://sel.jnu.ac.kr/mod/assign/view.php?id={cmid}", "due": due, "remaining": "",
            "submitted": submitted, "graded": "채점되지 않음", "status": {"제출 여부": submitted}, "description": desc,
            "attachments": list(attachments), "fetched_at": "2026-09-28T12:00:00"}


def cal(cmid, due, mod="vod", course=0, name=None, start=""):
    c = COURSES[course]
    return {"due": due, "start": start, "course": c["name"], "course_id": c["id"], "type": "동영상" if mod == "vod" else "퀴즈",
            "name": name or f"{mod}{cmid}", "url": f"https://sel.jnu.ac.kr/mod/{mod}/view.php?id={cmid}", "cmid": str(cmid),
            "status": "", "source": "calendar"}


def write_data(assignments=(), deadlines=None, stamp="2026-09-28 12:00", courses=COURSES):
    """수집기가 쓰는 모양 그대로 — courses.json · assignments.json · deadlines.json."""
    from eclass import config as C
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    (C.COURSES_FILE).write_text(json.dumps(list(courses), ensure_ascii=False), encoding="utf-8")
    C.ASSIGNMENTS_FILE.write_text(json.dumps(list(assignments), ensure_ascii=False), encoding="utf-8")
    if deadlines is None:
        deadlines = [{"due": a["due"], "start": "", "course": a["course"], "course_id": a["course_id"], "type": "과제",
                      "name": a["name"], "url": a["url"], "cmid": a["cmid"], "status": a["submitted"], "source": "assign"}
                     for a in assignments if a["due"]]
    C.DEADLINES_FILE.write_text(json.dumps({"updated_at": stamp, "items": list(deadlines)}, ensure_ascii=False),
                                encoding="utf-8")


@pytest.fixture()
def db():
    from eclass import config as C, store
    for p in C.DATA_DIR.glob("*"):
        if p.is_file():
            p.unlink()
    store._initialized.clear()
    with store.connect() as con:
        yield con


@pytest.fixture()
def state():
    from eclass import config as C
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    for p in C.STATE_DIR.glob("*"):
        p.unlink()
    yield C.STATE_DIR


class FakePush:
    """알림 센터 대역 — F1 notify.push 와 같은 규칙(같은 id 무시 · upsert 는 안 읽었으면 고쳐 쓰기)."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def __call__(self, nid, kind, ref_id, title, body, href, fire_at, missed, upsert):
        if nid in self.rows:
            if upsert and (self.rows[nid]["title"], self.rows[nid]["body"]) != (title, body):
                self.rows[nid].update(title=title, body=body)
                return True
            return False
        self.rows[nid] = {"kind": kind, "ref": ref_id, "title": title, "body": body, "href": href, "fire": fire_at,
                          "missed": missed}
        return True
