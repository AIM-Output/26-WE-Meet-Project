"""브리핑 설정 — 켜기/끄기 · 시각 · 보관 기간 (F10-R06 · R07 · R22, 화면 /settings/notifications).

meta.settings 에는 **기본값과 다른 값만** 둔다(F7 설정과 같은 이유 — 나중에 기본값을 고치면 손대지 않은 사람에게 그대로 간다).
알림 기본 시각(F1)·과제 마감 알림(F6)은 각 기능이 자기 자리에 저장한다 — 여기서는 브리핑 칸만 다룬다.
"""
from __future__ import annotations

import re
import sqlite3
from typing import Any, Optional

from . import config as C
from . import store

_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


class Invalid(Exception):
    pass


def norm_time(value: Any) -> str:
    m = _TIME.match(str(value or "").strip())
    if not m:
        raise Invalid("브리핑 시각은 HH:MM 모양이어야 합니다 (예: 08:00)")
    hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        raise Invalid(f"브리핑 시각이 올바르지 않습니다: {value}")
    return f"{hh:02d}:{mm:02d}"


def _saved(con: sqlite3.Connection) -> dict:
    raw = store.loads(store.get_meta(con, "settings"), {})
    return raw if isinstance(raw, dict) else {}


def load(con: sqlite3.Connection) -> dict:
    """지금 설정 — 저장된 값이 깨졌으면 그 칸만 기본값으로."""
    out = C.default_settings()
    for k, v in _saved(con).items():
        try:
            if k == "enabled":
                out[k] = bool(v)
            elif k == "time":
                out[k] = norm_time(v)
            elif k == "keepDays" and int(v) in C.KEEP_DAYS_CHOICES:
                out[k] = int(v)
        except (Invalid, TypeError, ValueError):
            continue
    return out


def view(con: sqlite3.Connection) -> dict:
    s = load(con)
    d = C.default_settings()
    return {**s, "defaults": d, "changed": [k for k in d if s[k] != d[k]],
            "keepDaysChoices": list(C.KEEP_DAYS_CHOICES), "llm": C.llm_configured()}


def save(con: sqlite3.Connection, patch: Optional[dict], reset: bool = False) -> dict:
    """{enabled?, time?, keepDays?} — null 은 그 칸을 기본값으로. reset 이면 전부 기본값."""
    patch = patch or {}
    cur = {} if reset else _saved(con)
    for k, v in patch.items():
        if k not in ("enabled", "time", "keepDays"):
            raise Invalid(f"모르는 설정입니다: {k}")
        if v is None:
            cur.pop(k, None)
            continue
        if k == "enabled":
            if not isinstance(v, bool):
                raise Invalid("enabled 는 true/false 여야 합니다")
            cur[k] = v
        elif k == "time":
            cur[k] = norm_time(v)
        else:
            try:
                n = int(v)
            except (TypeError, ValueError):
                raise Invalid("보관 기간은 숫자(일)여야 합니다")
            if n not in C.KEEP_DAYS_CHOICES:
                raise Invalid(f"보관 기간은 {' · '.join(map(str, C.KEEP_DAYS_CHOICES))}일 중 하나여야 합니다")
            cur[k] = n
    d = C.default_settings()
    cur = {k: v for k, v in cur.items() if d.get(k) != v}
    store.set_meta(con, "settings", store.dumps(cur) if cur else None)
    store.touch(con)
    return view(con)
