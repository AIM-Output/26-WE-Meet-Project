"""테스트 공통 — 임시 data/·state/ 를 쓴다(내 이수 내역·수정본을 건드리지 않는다). 룰셋·교육과정은 저장소의 것을 읽는다."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f2test_"))
os.environ["F2_DATA_DIR"] = str(_TMP / "data")
os.environ["F2_STATE_DIR"] = str(_TMP / "state")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# C2 matching_view 모양 — 인공지능학부 인공지능전공
PROFILE_2021 = {"collegeCode": "30001229", "college": "AI융합대학", "deptCode": "30001265", "department": "인공지능학부",
                "majorCode": "30001267", "major": "인공지능전공", "admissionYear": 2021, "track": "single",
                "gpa": {"value": 3.42, "scale": 4.5, "basis": "전체"}}


@pytest.fixture()
def db():
    from graduation import config as C, store
    for p in C.DB_PATH.parent.glob("graduation.db*"):
        p.unlink()
    store._initialized.clear()
    with store.connect() as con:
        yield con


@pytest.fixture()
def profile():
    return dict(PROFILE_2021)


def course(name, credits=3, cat="전선", grade="A0", year=2022, sem="1", code=None, **kw):
    """계산기 입력 한 줄."""
    return {"id": kw.pop("id", f"t:{name}:{year}:{sem}"), "name": name, "credits": credits, "rawCategory": cat,
            "grade": grade, "year": year, "semester": sem, "code": code, "source": kw.pop("source", "hakstd"), **kw}
