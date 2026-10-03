"""테스트 공통 — 임시 data/·state/ 와 작은 학과 마스터 (저장소의 스냅숏·내 프로필을 건드리지 않는다)."""
import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="c2test_"))
os.environ["C2_DATA_DIR"] = str(_TMP / "data")
os.environ["C2_STATE_DIR"] = str(_TMP / "state")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

MASTER = {
    "updatedAt": "2026-09-28T00:00:00", "year": 2026,
    "colleges": [
        {"code": "30001229", "name": "AI융합대학", "departments": [
            {"code": "30001265", "name": "인공지능학부", "majors": [
                {"code": "30001266", "name": "소프트웨어전공"}, {"code": "30001267", "name": "인공지능전공"}]},
            {"code": "30001230", "name": "로봇공학융합전공", "majors": [{"code": "30001231", "name": "로봇공학융합전공"}]},
        ]},
        {"code": "30000088", "name": "공과대학", "departments": [
            {"code": "30000150", "name": "컴퓨터공학과", "majors": []},
        ]},
    ],
}


@pytest.fixture()
def db():
    from student import config as C, store
    C.LOCAL_MASTER.parent.mkdir(parents=True, exist_ok=True)
    C.LOCAL_MASTER.write_text(json.dumps(MASTER, ensure_ascii=False), encoding="utf-8")
    for p in C.DB_PATH.parent.glob("profile.db*"):
        p.unlink()
    store._initialized.clear()
    with store.connect() as con:
        yield con
