"""기능 래퍼가 예외를 삼켜도 traceback 은 stderr(=backend.log)에 남고(같은 오류는 한 번), /api/status 의 sync 칸은 500 대신 error."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import eclass_data  # noqa: E402


class _Broken:
    def sync_state(self):
        raise RuntimeError("상태 파일 깨짐")

    def deliver(self, push):
        raise RuntimeError("알림 표 잠김")


def test_swallowed_errors_are_logged_once_and_sync_state_survives(monkeypatch, capsys):
    monkeypatch.setattr(eclass_data, "f6", _Broken())
    st = eclass_data.sync_state()
    assert st["running"] is False and "상태 파일 깨짐" in st["error"]
    assert eclass_data.deliver() == 0 and eclass_data.deliver() == 0
    err = capsys.readouterr().err
    assert "RuntimeError: 상태 파일 깨짐" in err and "Traceback" in err
    assert err.count("RuntimeError: 알림 표 잠김") == 1         # 1분마다 불려도 같은 오류는 한 번만
