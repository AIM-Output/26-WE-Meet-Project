"""상태 JSON 을 쓰다 죽어도(디스크 가득·강제 종료) 원래 파일이 반쯤 쓴 채로 남지 않는다 — 임시 파일 + os.replace."""
from pathlib import Path

import pytest

from student import config as C, jobs


def _half_write(monkeypatch):
    real = Path.write_text

    def broken(self, data, *a, **kw):
        real(self, data[: len(data) // 2], *a, **kw)
        raise OSError("디스크 가득")
    monkeypatch.setattr(Path, "write_text", broken)


def test_last_state_survives_crash_mid_write(monkeypatch):
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    jobs._last_file("master").write_text('{"ok": true}', encoding="utf-8")
    _half_write(monkeypatch)
    with pytest.raises(OSError):
        jobs._finish("master", ok=False)
    monkeypatch.undo()
    assert jobs._last_file("master").read_text(encoding="utf-8") == '{"ok": true}'
