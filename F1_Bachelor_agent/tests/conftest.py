"""테스트 공통 — 실제 data/·state/ 를 건드리지 않도록 임시 폴더를 쓴다 (bachelor.config 를 import 하기 전에 설정)."""
import os
import sys
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f1test_"))
os.environ["F1_DATA_DIR"] = str(_TMP / "data")
os.environ["F1_STATE_DIR"] = str(_TMP / "state")
os.environ["LLM_MAIN_API_KEY"] = ""           # 테스트에서 LLM 을 부르지 않는다
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402


@pytest.fixture()
def db():
    """빈 DB 하나 — 테스트마다 새로."""
    from bachelor import config as C, store
    for p in C.DB_PATH.parent.glob("academic.db*"):
        p.unlink()
    store._initialized.clear()
    with store.connect() as con:
        yield con
