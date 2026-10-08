"""C0 osenv — 앱 데이터 폴더(appdata) · 묶인 앱의 자식 프로세스 명령(module_cmd) · Chromium 상태."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import osenv  # noqa: E402
from osenv import appdata  # noqa: E402


def test_apply_mirrors_repo_layout(tmp_path):
    env = {"F6_STATE_DIR": "/이미/정해짐"}
    out = appdata.apply(tmp_path, env)
    assert env["F6_DATA_DIR"] == str(tmp_path / "F6_Eclass_agent" / "data")     # F6 상대경로 규칙('data\\…')이 살도록
    assert env["C3_STATE_DIR"] == str(tmp_path / "C3_Login_agent" / "state")
    assert env["F6_STATE_DIR"] == "/이미/정해짐" and "F6_STATE_DIR" not in out     # 이미 정한 것은 그대로
    assert env["PLAYWRIGHT_BROWSERS_PATH"] == str(tmp_path / "pw-browsers")
    assert "C1_STATE_DIR" not in env                                                # 없는 변수는 만들지 않는다


def test_migrate_copies_once(tmp_path):
    src, root = tmp_path / "repo", tmp_path / "app"
    (src / "F6_Eclass_agent" / "data" / "과목").mkdir(parents=True)
    (src / "F6_Eclass_agent" / "data" / "과목" / "a.pdf").write_bytes(b"pdf")
    (src / "F6_Eclass_agent" / "state").mkdir()
    (src / "F6_Eclass_agent" / "state" / "sync.lock").write_text("1")              # 잠금은 옮기지 않는다
    (src / "F6_Eclass_agent" / ".venv").mkdir()
    done = appdata.migrate(src, root, log=lambda *_: None)
    assert done == ["F6_Eclass_agent/data"]                                          # state 에는 잠금뿐 → 옮길 것 없음
    assert (root / "F6_Eclass_agent" / "data" / "과목" / "a.pdf").read_bytes() == b"pdf"
    assert not (root / "F6_Eclass_agent" / "state" / "sync.lock").exists()
    assert not (root / "F6_Eclass_agent" / ".venv").exists()
    (root / "F6_Eclass_agent" / "data" / "new.txt").write_text("앱에서 생긴 것")
    assert appdata.migrate(src, root, log=lambda *_: None) == []                   # 두 번째는 덮어쓰지 않는다


def test_module_cmd(monkeypatch, tmp_path):
    monkeypatch.setattr(osenv, "FROZEN", False)                                  # 개발 모드 — 지금 도는 python 그대로
    monkeypatch.setattr(sys, "executable", str(tmp_path / "desktop" / "sidecar" / ".venv" / "bin" / "python"))
    assert osenv.module_cmd("eclass", "sync") == [sys.executable, "-X", "utf8", "-m", "eclass", "sync"]
    monkeypatch.setattr(osenv, "FROZEN", True)
    monkeypatch.setattr(sys, "executable", "/Applications/UnivUs.app/univus-backend")
    assert osenv.module_cmd("eclass", "sync") == [
        "/Applications/UnivUs.app/univus-backend", "--run-module", "eclass", "sync"]


def test_browsers_dir_and_state(monkeypatch, tmp_path):
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(sys, "prefix", str(tmp_path / ".venv"))
    assert osenv.browsers_dir() == tmp_path / ".venv" / "pw-browsers"           # 명령줄에서 바로 — 그 python 의 venv
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", str(tmp_path / "app" / "pw-browsers"))
    b = osenv.browsers_dir()
    assert b == tmp_path / "app" / "pw-browsers"
    assert osenv.chromium_state(b) == "missing"
    b.mkdir(parents=True)
    (b / osenv.INSTALLING_MARK).write_text("1")
    assert osenv.chromium_state(b) == "installing"
    (b / osenv.INSTALLING_MARK).unlink()
    assert osenv.chromium_state(b) == "ready"


def test_default_root_is_app_id_folder(monkeypatch, tmp_path):
    """설치 폴더(%LOCALAPPDATA%\\UnivUs)와 겹치지 않게 앱 식별자 폴더 아래 data — tauri.conf.json identifier 와 같아야 한다."""
    import json
    conf = json.loads((Path(__file__).resolve().parents[2] / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
    assert appdata.APP_ID == conf["identifier"]
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert appdata.default_root() == tmp_path / conf["identifier"] / "data"
    assert appdata.default_root() != tmp_path / conf["productName"]
