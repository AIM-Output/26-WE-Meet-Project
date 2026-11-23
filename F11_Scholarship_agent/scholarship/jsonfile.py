"""설정 JSON(directory/*.json) 읽기 — 파일이 바뀌면 다시 읽되, 바뀌었는지(파일 시각)는 RECHECK_SEC 에 한 번만 본다. 표준 라이브러리만.

예전에는 원천·관심사 사전을 찾을 때마다 파일 시각을 봤다 — 대외활동 목록 한 번(공지 570건)에 3만 5천 번, Windows 에서
6초가 걸렸다(2026-11-23 실측, 장학·대외활동 모두 이 모듈을 쓴다). 파일을 고치면 늦어도 RECHECK_SEC 뒤에는 새 내용을 읽는다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Optional

RECHECK_SEC = 2.0


class JsonFile:
    """JsonFile(lambda: C.SOURCES_FILE).get() → 읽은 JSON (같은 내용이면 같은 객체 — 고쳐 쓰지 말 것).
    경로는 부를 때마다 함수로 받는다(설정·테스트가 바꿀 수 있게). prepare(data) 를 주면 다시 읽을 때 한 번만 불러
    그 결과를 .extra() 로 돌려준다(정규식 컴파일처럼 내용에서 만드는 것)."""

    def __init__(self, path: Callable[[], Path], prepare: Optional[Callable[[Any], Any]] = None) -> None:
        self._path = path
        self._prepare = prepare
        self._state: Optional[tuple] = None          # (경로, 파일 시각, 내용, prepare 결과) — 통째로 바꿔 끼운다(스레드 안전)
        self._checked = 0.0

    def get(self) -> Any:
        return self._load()[2]

    def extra(self) -> Any:
        return self._load()[3]

    def _load(self) -> tuple:
        path, st, now = self._path(), self._state, time.monotonic()
        if st is not None and st[0] == path and now - self._checked < RECHECK_SEC:
            return st
        mtime = path.stat().st_mtime
        if st is None or st[0] != path or st[1] != mtime:
            data = json.loads(path.read_text(encoding="utf-8"))
            st = self._state = (path, mtime, data, self._prepare(data) if self._prepare else None)
        self._checked = now
        return st
