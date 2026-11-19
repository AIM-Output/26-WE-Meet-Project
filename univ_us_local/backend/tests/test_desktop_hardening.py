"""desktop.py 견고화 — backend.log 회전 · 미리 bind 한 포트 · stdin 닫힘 때 자식 정리를 먼저."""
import io
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import desktop  # noqa: E402


def test_rotate_moves_big_log_aside(tmp_path):
    log = tmp_path / "backend.log"
    log.write_bytes(b"x" * 11)
    desktop._rotate(log, limit=10)
    assert not log.exists() and (tmp_path / "backend.log.1").read_bytes() == b"x" * 11
    log.write_bytes(b"y" * 5)
    desktop._rotate(log, limit=10)                       # 작으면 그대로
    assert log.read_bytes() == b"y" * 5


def test_bound_socket_keeps_port_reserved():
    s = desktop._bound_socket()
    try:
        port = s.getsockname()[1]
        other = socket.socket()
        try:
            other.bind(("127.0.0.1", port))
            raise AssertionError("포트가 비어 있었다 — 다른 프로세스가 가로챌 수 있다")
        except OSError:
            pass
        finally:
            other.close()
    finally:
        s.close()


def test_stdin_close_kills_children_before_exit(monkeypatch):
    order = []

    class Server:
        def __setattr__(self, k, v):
            order.append(k)

    monkeypatch.setattr(desktop.osenv, "kill_children", lambda: order.append("kill"), raising=False)
    desktop._exit_with_stdin(Server(), io.BytesIO(b""))
    assert order == ["kill", "should_exit"]
