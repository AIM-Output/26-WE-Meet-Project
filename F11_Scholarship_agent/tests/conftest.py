"""테스트 공통 — 임시 data/·state/ 를 쓴다. 내 장학 데이터(F11_Scholarship_agent/data)는 건드리지 않는다.

학교 사이트에 접속하지 않는다 — 수집기는 저장된 HTML 조각으로, 판정·서비스는 손으로 넣은 공지로 시험한다.
학과 홈페이지 목록은 F1 이 저장소에 넣어 둔 스냅숏(F1_Bachelor_agent/directory/homepages.json)을 읽기만 한다.
"""
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f11test_"))
os.environ["F11_DATA_DIR"] = str(_TMP / "data")
os.environ["F11_STATE_DIR"] = str(_TMP / "state")
os.environ["F11_AUTOSYNC"] = "off"
os.environ["F12_STATE_DIR"] = str(_TMP / "f12-state")      # F12 수집 잠금(기다리는 상대)도 임시 자리
os.environ["F1_DATA_DIR"] = str(_TMP / "no-f1-data")        # 내려받은 홈페이지 목록 대신 저장소 스냅숏
for k in ("LLM_MAIN_BASE_URL", "LLM_MAIN_API_KEY", "LLM_MAIN_MODEL"):
    os.environ[k] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

TODAY = date(2026, 10, 9)

# 인공지능학부 3학년 · 광주 거주 · 해당 사항 '없음'을 고른 사람 (요구사항정의서 F11 3절 US-2 예시와 같은 평점)
PROFILE = {
    "grade": 3, "enrollmentStatus": "재학", "semestersCompleted": 5,
    "gpa": {"value": 3.42, "scale": 4.5, "basis": "전체"}, "lastSemesterGpa": {"value": 3.6, "scale": 4.5, "basis": "직전학기"},
    "earnedCredits": 90, "lastSemesterCredits": 18, "incomeBracket": None, "residenceRegion": "광주", "highSchoolRegion": None,
    "flags": {}, "college": "AI융합대학", "department": "인공지능학부", "major": None,
}


@pytest.fixture(autouse=True)
def fresh_db():
    from scholarship import config as C
    for p in (C.DB_PATH, C.DB_PATH.with_name(C.DB_PATH.name + "-wal"), C.DB_PATH.with_name(C.DB_PATH.name + "-shm")):
        if p.exists():
            p.unlink()
    from scholarship import store
    store._initialized.clear()
    yield


@pytest.fixture
def profile():
    return {**PROFILE, "gpa": dict(PROFILE["gpa"]), "lastSemesterGpa": dict(PROFILE["lastSemesterGpa"]), "flags": {}}


def add_notice(con, nid="www:1", title="[장학안내] 테스트 장학생 선발 안내", body="", *, source="jnu_scholarship",
               posted="2026-10-01", kind="notice", writer="학생과", unit_key=None, attach_text="", is_result=False):
    """수집기를 거치지 않고 공지 한 건을 넣는다 (요건 추출은 수집기와 같은 build_req)."""
    from scholarship import collect, registry, store
    from scholarship.textutil import content_hash, norm_title
    row = {"id": nid, "source": source, "source_name": "테스트", "unit_key": unit_key, "kind": kind, "title": title,
           "url": f"https://example.invalid/{nid}", "posted_at": posted, "writer": writer, "category": None, "body": body,
           "attach_text": attach_text, "attachments": [], "image_only": False, "content_hash": content_hash(title, body),
           "is_result": is_result, "title_key": norm_title(title), "dup_of": None}
    row["req"] = collect.build_req(row, registry.get(unit_key) if unit_key else None)
    from scholarship import config as C
    row["extract_ver"] = C.EXTRACT_VERSION
    return store.upsert_notice(con, row)
