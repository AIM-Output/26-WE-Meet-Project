"""테스트 공통 — 실제 state/(로그인 세션·자격증명)를 건드리지 않도록 임시 폴더를 쓴다 (login.config 를 import 하기 전에)."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["C3_STATE_DIR"] = tempfile.mkdtemp(prefix="c3test_")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
