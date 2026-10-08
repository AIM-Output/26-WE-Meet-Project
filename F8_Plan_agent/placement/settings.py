"""공강 배치 설정 — 낮 시간대 · 점심 · 여유 · 블록 길이 · 주말 · 기간 · 공부 채우기 (F8-S09 · 6절 AvailabilitySettings).

저녁 시간대(19:00~24:00)는 2026-10-07 부터 F5 시험 공부 계획 전용이라 여기 없다 — F5 의 /api/exams/settings 에 있다.

data/settings.json 에는 **기본값과 다른 값만** 둔다. 그래야 나중에 기본값을 고치면(Q1·Q2 '시범 사용 후') 손대지 않은
사용자에게 새 기본값이 그대로 간다 — F5 난이도 설정에서 옛 기본값이 굳었던 일을 되풀이하지 않는다(F7 설정과 같은 방식).
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, Optional

from . import config as C

_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")

LABELS = {
    "dayStart": "낮 시작", "dayEnd": "낮 끝",
    "lunchBreak": "점심 제외", "lunchStart": "점심 시작", "lunchEnd": "점심 끝",
    "bufferMinutes": "수업 앞뒤 여유", "minSlotMinutes": "최소 블록", "maxBlockMinutes": "최대 블록",
    "useWeekend": "주말 사용", "rangeDays": "배치 기간", "fillStudy": "남는 공강에 공부 블록",
}


class Invalid(Exception):
    pass


def minutes(value: Any, allow_24: bool = False) -> int:
    """'19:00' → 1140 · '24:00' → 1440(allow_24 일 때만). 받을 수 없는 값이면 Invalid."""
    m = _TIME.match(str(value or "").strip())
    if not m:
        raise Invalid(f"시각은 HH:MM 모양이어야 합니다: {value}")
    hh, mm = int(m.group(1)), int(m.group(2))
    if mm >= 60 or hh > 24 or (hh == 24 and (mm or not allow_24)):
        raise Invalid(f"시각이 올바르지 않습니다: {value}")
    return hh * 60 + mm


def hhmm(total: int) -> str:
    return f"{total // 60:02d}:{total % 60:02d}"


def _read() -> dict:
    try:
        raw = json.loads(C.SETTINGS_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    """원자적 쓰기 — 쓰다가 꺼져도 반쯤 쓴 파일이 남지 않게."""
    C.ensure_dirs()
    fd, tmp = tempfile.mkstemp(prefix=".settings.", suffix=".tmp", dir=str(C.DATA_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, C.SETTINGS_FILE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _one(key: str, value: Any) -> Any:
    """칸 하나를 검사해 정규화한 값을 돌려준다 (서로 얽힌 검사는 _check_pairs)."""
    if key in ("lunchBreak", "useWeekend", "fillStudy"):
        if not isinstance(value, bool):
            raise Invalid(f"{LABELS[key]} 는 켬/끔(true/false)이어야 합니다")
        return value
    if key in ("dayStart", "dayEnd", "lunchStart", "lunchEnd"):
        return hhmm(minutes(value))
    try:
        if isinstance(value, bool):
            raise ValueError
        f = float(value)
    except (TypeError, ValueError):
        raise Invalid(f"{LABELS[key]} 는 숫자여야 합니다")
    if f != int(f):
        raise Invalid(f"{LABELS[key]} 는 정수(분)여야 합니다")
    n = int(f)
    if key == "bufferMinutes" and n not in C.BUFFER_CHOICES:
        raise Invalid(f"수업 앞뒤 여유는 {', '.join(map(str, C.BUFFER_CHOICES))}분 중 하나여야 합니다")
    if key == "minSlotMinutes" and not C.MIN_SLOT_RANGE[0] <= n <= C.MIN_SLOT_RANGE[1]:
        raise Invalid(f"최소 블록은 {C.MIN_SLOT_RANGE[0]}~{C.MIN_SLOT_RANGE[1]}분이어야 합니다")
    if key == "maxBlockMinutes" and not C.MAX_BLOCK_RANGE[0] <= n <= C.MAX_BLOCK_RANGE[1]:
        raise Invalid(f"최대 블록은 {C.MAX_BLOCK_RANGE[0]}~{C.MAX_BLOCK_RANGE[1]}분이어야 합니다")
    if key == "rangeDays" and n not in C.RANGE_DAYS_CHOICES:
        raise Invalid(f"배치 기간은 {' · '.join(map(str, C.RANGE_DAYS_CHOICES))}일 중 하나여야 합니다")
    return n


def _check_pairs(s: dict) -> None:
    ds, de = minutes(s["dayStart"]), minutes(s["dayEnd"])
    if ds < minutes(C.DAY_EARLIEST):
        raise Invalid(f"낮 시작은 {C.DAY_EARLIEST} 이후여야 합니다")
    if de > minutes(C.DAY_LATEST):
        raise Invalid(f"낮 끝은 {C.DAY_LATEST} 까지입니다 — 그 뒤 저녁은 시험 공부 계획(F5) 몫입니다")
    if de - ds < s["minSlotMinutes"]:
        raise Invalid("낮 끝은 낮 시작보다 최소 블록 길이만큼 늦어야 합니다")
    if minutes(s["lunchEnd"]) <= minutes(s["lunchStart"]):
        raise Invalid("점심 끝은 점심 시작보다 늦어야 합니다")
    if s["maxBlockMinutes"] < s["minSlotMinutes"]:
        raise Invalid("최대 블록은 최소 블록보다 짧을 수 없습니다")


def load() -> dict:
    """기본값 위에 저장된 값을 얹는다. 저장된 값이 깨져 있으면 그 칸만 기본값으로 (화면이 죽지 않게).
    서로 얽힌 값(저녁 시작·끝 등)이 어긋나면 전부 기본값으로 — 계산이 엉뚱한 자리를 만들지 않게."""
    out = C.default_settings()
    for k, v in _read().items():
        if k in C.KEYS:
            try:
                out[k] = _one(k, v)
            except Invalid:
                pass
    try:
        _check_pairs(out)
    except Invalid:
        return C.default_settings()
    return out


def view() -> dict:
    """GET /api/settings/availability — 지금 값 + 기본값 + 고친 칸 + 고를 수 있는 값 (설정 화면이 그대로 그린다)."""
    cur, base = load(), C.default_settings()
    return {
        **cur, "defaults": base, "changed": [k for k in C.KEYS if cur[k] != base[k]],
        "choices": {"bufferMinutes": list(C.BUFFER_CHOICES), "rangeDays": list(C.RANGE_DAYS_CHOICES),
                    "minSlotMinutes": list(C.MIN_SLOT_RANGE), "maxBlockMinutes": list(C.MAX_BLOCK_RANGE),
                    "dayEarliest": C.DAY_EARLIEST, "dayLatest": C.DAY_LATEST},
    }


def merged(patch: Optional[dict]) -> dict:
    """저장하지 않고 설정 위에 patch 를 얹은 값 — 미리보기의 '이 설정이면?' 계산용. 검사는 저장과 같다."""
    if not patch:
        return load()
    out = load()
    out.update(_apply(dict(out), patch))
    _check_pairs(out)
    return out


def _apply(cur: dict, patch: dict) -> dict:
    if not isinstance(patch, dict):
        raise Invalid("설정은 {dayStart, dayEnd, …} 모양이어야 합니다")
    unknown = set(patch) - set(C.KEYS)
    if unknown:
        raise Invalid(f"모르는 설정입니다: {', '.join(sorted(unknown))}")
    base = C.default_settings()
    for k, v in patch.items():
        cur[k] = base[k] if v is None else _one(k, v)
    return cur


def save(patch: dict, reset: bool = False) -> dict:
    """PATCH /api/settings/availability {칸: 값} · null 은 그 칸을 기본값으로 · reset=True 면 전부 기본값으로.
    기본값과 같은 값은 저장하지 않는다."""
    base = C.default_settings()
    cur = base if reset else load()
    nxt = _apply(dict(cur), patch or {})
    _check_pairs(nxt)
    _write({k: nxt[k] for k in C.KEYS if nxt[k] != base[k]})
    return view()


def stored() -> Optional[dict]:
    """명령줄 표시용 — 파일에 실제로 적힌 값."""
    return _read() or None
