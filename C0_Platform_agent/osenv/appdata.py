"""앱 데이터 폴더 — 데스크톱 앱은 설치 폴더(Program Files · .app 안)에 쓰지 않고 사용자 데이터 폴더에 쓴다.

    default_root()          <OS 사용자 데이터 폴더>/kr.univus.desktop/data
                              Windows %LOCALAPPDATA%\\kr.univus.desktop\\data · 맥 ~/Library/Application Support/kr.univus.desktop/data
    apply(root)             기능마다 DATA/STATE 환경변수를 root 아래로 맞춘다 (이미 정해져 있으면 그대로)
    migrate(src, root)      다른 데이터 폴더(src, 같은 모양)의 data/·state/ 를 root 로 복사 (명령줄: python -m osenv copy-data)

root 아래는 기능 폴더와 **같은 모양**으로 둔다 — <root>/F6_Eclass_agent/data, <root>/C3_Login_agent/state …
F6 가 manifest 에 'data\\<과목>\\…' 처럼 기능 폴더 기준 상대경로를 적고 F3·F4·F5 가 F6_DATA_DIR 의 부모 기준으로 읽기 때문에,
폴더 이름(data)과 깊이를 지키면 그 규칙이 그대로 산다. 개발 모드는 같은 모양으로 desktop/.dev-data 를 쓴다.

왜 앱 식별자(kr.univus.desktop) 폴더인가: Windows 설치 파일(NSIS, 현재 사용자 설치)은 프로그램을 %LOCALAPPDATA%\\<제품 이름>
(= UnivUs)에 깐다. 데이터를 거기 두면 프로그램 파일과 성적·로그인 세션이 한 폴더에 섞이고, 제거할 때 '앱 데이터 삭제'를
골라도 지워지지 않는다(그 체크박스는 %LOCALAPPDATA%\\<식별자> 를 지운다). 식별자 폴더에는 앱 창(WebView2)의 프로필도 있다.
**APP_ID 는 desktop/src-tauri/tauri.conf.json 의 identifier 와 같아야 한다.**
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable, Optional

APP_ID = "kr.univus.desktop"                              # = tauri.conf.json identifier

# 기능 폴더 → (DATA 환경변수, STATE 환경변수). 각 기능 config.py 가 읽는 이름 그대로.
LAYOUT: dict[str, tuple[Optional[str], Optional[str]]] = {
    "C1_Calendar_agent": ("C1_DATA_DIR", None),
    "C2_Profile_agent": ("C2_DATA_DIR", "C2_STATE_DIR"),
    "C3_Login_agent": (None, "C3_STATE_DIR"),
    "F1_Bachelor_agent": ("F1_DATA_DIR", "F1_STATE_DIR"),
    "F2_Graduation_agent": ("F2_DATA_DIR", "F2_STATE_DIR"),
    "F3_Attendance_agent": ("F3_DATA_DIR", "F3_STATE_DIR"),
    "F4_Textbook_agent": ("F4_DATA_DIR", None),
    "F5_Test_agent": ("F5_DATA_DIR", None),
    "F6_Eclass_agent": ("F6_DATA_DIR", "F6_STATE_DIR"),
    "F7_Task_agent": ("F7_DATA_DIR", None),
    "F8_Plan_agent": ("F8_DATA_DIR", None),
}
BROWSERS = "pw-browsers"                                   # Playwright Chromium (첫 실행 때 내려받는다)


def default_root() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return base / APP_ID / "data"


def apply(root: str | os.PathLike, env: Optional[dict] = None) -> dict[str, str]:
    """root 아래 자리를 환경변수로 정한다 — 기능 config 를 import 하기 **전에** 불러야 한다. 정한 것만 돌려준다."""
    env = os.environ if env is None else env
    root = Path(root)
    out: dict[str, str] = {}
    for folder, (data_var, state_var) in LAYOUT.items():
        for var, sub in ((data_var, "data"), (state_var, "state")):
            if var and not env.get(var):
                env[var] = out[var] = str(root / folder / sub)
    if not env.get("PLAYWRIGHT_BROWSERS_PATH"):
        env["PLAYWRIGHT_BROWSERS_PATH"] = out["PLAYWRIGHT_BROWSERS_PATH"] = str(root / BROWSERS)
    env.setdefault("UNIVUS_DATA_ROOT", str(root))
    return out


def migrate(src: str | os.PathLike, root: str | os.PathLike, log: Callable[[str], None] = print) -> list[str]:
    """src(앱 데이터 폴더 등, 같은 모양)의 data/·state/ 를 root 로 복사. 이미 있는 폴더는 건드리지 않는다(덮어쓰지 않음).
    하드링크가 아니라 복사인 이유: SQLite(WAL)를 앱과 개발 모드가 같이 열면 깨질 수 있다. 원본은 남긴다."""
    src, root = Path(src), Path(root)
    skip = ("*.lock",)                                     # 실행 중 잠금은 옮기지 않는다
    done: list[str] = []
    for folder, (data_var, state_var) in LAYOUT.items():
        for var, sub in ((data_var, "data"), (state_var, "state")):
            a, b = src / folder / sub, root / folder / sub
            if not var or not a.is_dir():
                continue
            if not any(f.is_file() and not f.match(skip[0]) for f in a.rglob("*")):
                continue                                   # 옮길 것이 없다
            if b.exists() and any(b.iterdir()):
                log(f"건너뜀 (이미 있음): {b}")
                continue
            shutil.copytree(a, b, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*skip))
            done.append(f"{folder}/{sub}")
            log(f"복사: {a} → {b}")
    return done
