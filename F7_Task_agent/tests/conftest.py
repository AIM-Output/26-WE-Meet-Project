"""테스트 공통 — 임시 data/ 를 쓴다. 내 설정(F7_Task_agent/data)도, F6 과제 원장도 건드리지 않는다.

다른 기능 폴더는 **없는 자리**를 가리키게 한다 — F7 계산은 넘겨받은 과제·일정만으로 돌아야 하고(service 는 파일을 열지 않는다),
명령줄의 sources.py 는 못 읽으면 problems 에 적고 빈 목록으로 계속해야 한다.
"""
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f7test_"))
os.environ["F7_DATA_DIR"] = str(_TMP / "f7data")
os.environ["F6_AGENT_DIR"] = str(_TMP / "no-f6")
os.environ["C1_AGENT_DIR"] = str(_TMP / "no-c1")
os.environ["F3_AGENT_DIR"] = str(_TMP / "no-f3")
os.environ["F5_AGENT_DIR"] = str(_TMP / "no-f5")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

NOW = datetime(2026, 9, 25, 14, 0)          # 요구사항정의서 F7 5절 예시의 '지금'


@pytest.fixture(autouse=True)
def clean_settings():
    from tasks import config as C
    if C.SETTINGS_FILE.exists():
        C.SETTINGS_FILE.unlink()
    yield
    if C.SETTINGS_FILE.exists():
        C.SETTINGS_FILE.unlink()


def item(iid, title, due, etype="과제", course="운영체제", est=None, **kw):
    """F6 원장의 화면용 과제 모양(eclass.service.view) 중 F7 이 읽는 칸."""
    base = {
        "id": iid, "title": title, "type": etype, "due": due, "course": f"{course}[1] (CIS0000)",
        "courseId": f"c-{course}", "courseShort": course, "courseColor": "#4f46e5", "url": "",
        "submitted": False, "userDone": False, "done": False, "removed": False, "estimateHours": est,
        "isNew": False, "changed": None, "status": "",
    }
    base.update(kw)
    if base["submitted"] or base["userDone"]:
        base["done"] = True
    return base


def example_items():
    """5절 예시 표 그대로 — 품질 보고서·팀 프로젝트·기말 프로젝트는 사용자가 소요시간을 고친 것으로 둔다."""
    return [
        item("dl:1", "퀴즈 2회", "2026-09-25T23:59:00", etype="퀴즈", course="컴퓨터네트워크"),
        item("dl:2", "실습 과제", "2026-09-26T23:59:00", course="운영체제"),
        item("dl:3", "팀 프로젝트 보고서", "2026-09-30T23:59:00", course="캡스톤디자인", est=50),
        item("dl:4", "품질 보고서", "2026-09-28T18:00:00", course="소프트웨어공학론", est=5),
        item("dl:5", "기말 프로젝트", "2026-12-10T23:59:00", course="캡스톤디자인", est=20),
    ]


def spec():
    """요구사항정의서 F7 5절 예시가 쓰는 입력 — 안전계수 1.5 · 과제 3시간 · 퀴즈 30분 · 동영상 1시간 · 프로젝트 5시간.
    기본값은 2026-10-06 에 바뀌었다(1.0 · 2시간 · 30분 · 50분 · 4시간). 계산 규칙 테스트는 이 값을 명시해 기본값과 떼어 둔다."""
    return {"safetyFactor": 1.5, "defaultHours": {"assignment": 3.0, "quiz": 0.5, "video": 1.0, "project": 5.0},
            "bedTime": "24:00"}
