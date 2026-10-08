"""사이드카가 표준입력 파이프(앱 종료 감지)를 읽는 동안에도 자식 python 이 멈추지 않고 뜨는가 — desktop._detach_stdin.

Windows 에서 다른 스레드가 동기 파이프를 읽고 있으면, 그 핸들을 물려받은 자식이 시작하며 멈췄다
(수집기·가져오기·Chromium 내려받기, 2026-10-08). 부모를 Tauri 처럼 stdin=PIPE 로 띄워 재현한다.
"""
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

PARENT = r"""
import subprocess, sys, threading
sys.path.insert(0, sys.argv[1])
sys.argv = sys.argv[:1]
import desktop
pipe = desktop._detach_stdin()
threading.Thread(target=lambda: pipe.read(1), daemon=True).start()   # 사이드카처럼 파이프를 읽으며 기다린다
out = subprocess.run([sys.executable, "-c", "import sys; print('child-ok', sys.stdin.read() == '')"],
                     capture_output=True, text=True, timeout=20)
print(out.stdout.strip())
"""


def test_child_starts_while_parent_reads_stdin():
    p = subprocess.Popen([sys.executable, "-c", PARENT, str(BACKEND)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    try:
        out, err = p.communicate(timeout=40)                 # 표준입력은 열어 둔 채 — 앱이 떠 있는 동안처럼
    finally:
        if p.poll() is None:
            p.kill()
    assert p.returncode == 0, err
    assert "child-ok True" in out                            # 자식은 NUL 을 받았다 (부모의 파이프가 아니다)
