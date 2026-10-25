"""테스트 공통 — 임시 data/·state/ 를 쓴다. 내 대외활동 데이터(F12_Activity_agent/data)는 건드리지 않는다.

학교 사이트에 접속하지 않는다 — 수집 파이프라인은 가짜 수집기·HTML 조각으로, 등급·서비스는 손으로 넣은 공지로 시험한다.
F11 원천 목록(F11_Scholarship_agent/directory/sources.json)과 F1 홈페이지 스냅숏은 저장소에 있는 것을 읽기만 한다.
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f12test_"))
os.environ["F12_DATA_DIR"] = str(_TMP / "data")
os.environ["F12_STATE_DIR"] = str(_TMP / "state")
os.environ["F11_DATA_DIR"] = str(_TMP / "f11-data")
os.environ["F11_STATE_DIR"] = str(_TMP / "f11-state")        # 기다리는 상대(F11 수집 잠금)도 임시 자리
os.environ["F12_AUTOSYNC"] = "off"
os.environ["F11_AUTOSYNC"] = "off"
os.environ["F1_DATA_DIR"] = str(_TMP / "no-f1-data")        # 내려받은 홈페이지 목록 대신 저장소 스냅숏
for k in ("LLM_MAIN_BASE_URL", "LLM_MAIN_API_KEY", "LLM_MAIN_MODEL"):
    os.environ[k] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

TODAY = date(2026, 10, 10)

# 인공지능학부 3학년 — 관심사: AI·SW · 공모전, 키워드 '반도체', 제외 '대학원생'
PROFILE = {
    "grade": 3, "enrollmentStatus": "재학", "semestersCompleted": 5, "college": "AI융합대학", "department": "인공지능학부",
    "major": None, "draftContext": None,
    "interests": {"tags": ["AI·SW", "공모전·경진대회"], "keywords": ["반도체"], "exclude": ["대학원생"]},
}


@pytest.fixture(autouse=True)
def fresh_db():
    from activity import config as C
    for p in (C.DB_PATH, C.DB_PATH.with_name(C.DB_PATH.name + "-wal"), C.DB_PATH.with_name(C.DB_PATH.name + "-shm")):
        if p.exists():
            p.unlink()
    from activity import store
    store._initialized.clear()
    yield


@pytest.fixture
def profile():
    return {**PROFILE, "interests": {k: list(v) for k, v in PROFILE["interests"].items()}}


def add_notice(con, nid="www:1", title="[모집공고] 테스트 프로그램 참가자 모집", body="", *, source="jnu_notice",
               posted="2026-10-05", writer="학생과", unit_key=None, category=None, first_seen=None):
    """수집기를 거치지 않고 공지 한 건을 넣는다 (정보 추출은 수집기와 같은 build_info)."""
    from activity import collect, config as C, registry, store
    from scholarship.textutil import content_hash, norm_title
    row = {"id": nid, "source": source, "source_name": "테스트", "unit_key": unit_key, "title": title,
           "url": f"https://example.invalid/{nid}", "posted_at": posted, "writer": writer, "category": category, "body": body,
           "attach_text": "", "attachments": [], "image_only": False, "content_hash": content_hash(title, body),
           "title_key": norm_title(title), "dup_of": None}
    row["info"] = collect.build_info(row, registry.get(unit_key) if unit_key else None)
    row["extract_ver"] = C.EXTRACT_VERSION
    res = store.upsert_notice(con, row)
    if first_seen:
        con.execute("UPDATE notices SET first_seen = ? WHERE id = ?", (first_seen, nid))
    return res


class FakeCalendar:
    """C1 내 일정 대신 — add_event / remove_event 를 기록한다 (출처가 같으면 같은 일정, 백엔드 _add_event 와 같은 규칙)."""

    def __init__(self):
        self.events: dict[str, dict] = {}
        self.removed: list[str] = []

    def add(self, ev: dict) -> dict:
        for e in self.events.values():
            if e["origin"] == ev.get("origin"):
                return e
        eid = str(len(self.events) + 1)
        self.events[eid] = {**ev, "id": eid}
        return self.events[eid]

    def remove(self, eid: str) -> None:
        self.removed.append(eid)
        self.events.pop(eid, None)


@pytest.fixture
def cal():
    return FakeCalendar()
