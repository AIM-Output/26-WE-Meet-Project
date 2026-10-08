"""우선순위 설정 — 안전계수 · 유형별 기본 소요시간 · 취침 시각 (F7-R05 · S08 · 6절 '설정').

data/settings.json 에는 **기본값과 다른 값만** 둔다. 그래야 나중에 기본값을 고치면(Q1·Q2 '시범 사용 후') 손대지 않은
사용자에게 새 기본값이 그대로 간다 — F5 난이도 설정에서 모달이 세 값을 다 저장해 옛 기본값이 굳었던 일이 있었다.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from typing import Any, Optional

from . import config as C

_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")


class Invalid(Exception):
    pass


def _read() -> dict:
    try:
        raw = json.loads(C.SETTINGS_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def _write(data: dict) -> None:
    """원자적 쓰기 — 쓰다가 꺼져도 반쯤 쓴 파일이 남지 않게."""
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
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


def bed_minutes(value: str) -> int:
    """'24:00' → 1440 · '23:30' → 1410 · '01:30' → 1530(다음 날 새벽). 받을 수 없는 값이면 Invalid."""
    m = _TIME.match(str(value or "").strip())
    if not m:
        raise Invalid("취침 시각은 HH:MM 모양이어야 합니다 (예: 24:00, 01:30)")
    hh, mm = int(m.group(1)), int(m.group(2))
    if mm >= 60 or hh > 24 or (hh == 24 and mm):
        raise Invalid(f"취침 시각이 올바르지 않습니다: {value}")
    total = hh * 60 + mm
    earliest = bed_minutes_raw(C.BED_EARLIEST)
    latest = bed_minutes_raw(C.BED_LATEST_AFTER_MIDNIGHT)
    if total < 12 * 60:                         # 정오 이전 = 자정 넘긴 새벽
        if total > latest:
            raise Invalid(f"취침 시각은 {C.BED_EARLIEST} ~ 다음 날 {C.BED_LATEST_AFTER_MIDNIGHT} 사이로 넣어 주세요")
        return total + 24 * 60
    if total < earliest:
        raise Invalid(f"취침 시각은 {C.BED_EARLIEST} ~ 다음 날 {C.BED_LATEST_AFTER_MIDNIGHT} 사이로 넣어 주세요")
    return total


def bed_minutes_raw(value: str) -> int:
    hh, mm = value.split(":")
    return int(hh) * 60 + int(mm)


def _norm_bed(value: Any) -> str:
    total = bed_minutes(value)
    if total == 24 * 60:
        return "24:00"
    hh, mm = divmod(total % (24 * 60), 60)
    return f"{hh:02d}:{mm:02d}"


def _num(value: Any, name: str, lo: float, hi: float) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise Invalid(f"{name} 는 숫자여야 합니다")
    if not lo <= v <= hi:
        raise Invalid(f"{name} 는 {lo:g} ~ {hi:g} 사이여야 합니다")
    return round(v, 2)


def same(a: Any, b: Any) -> bool:
    """설정값이 같은가 — 소수 둘째 자리까지. 동영상 기본 50분(0.8333…시간)을 화면 칸이 0.83 으로 보이고 그대로 저장해도 기본값이다."""
    return abs(float(a) - float(b)) < 0.005


def load() -> dict:
    """기본값 위에 저장된 값을 얹는다. 저장된 값이 깨져 있으면 그 칸만 기본값으로 (화면이 죽지 않게)."""
    out = C.default_settings()
    raw = _read()
    try:
        if "safetyFactor" in raw:
            out["safetyFactor"] = _num(raw["safetyFactor"], "안전계수", *C.SAFETY_RANGE)
    except Invalid:
        pass
    for k, v in (raw.get("defaultHours") or {}).items():
        if k in C.KINDS:
            try:
                out["defaultHours"][k] = _num(v, f"{C.KINDS[k]['label']} 기본 시간", *C.DEFAULT_HOURS_RANGE)
            except Invalid:
                pass
    if "bedTime" in raw:
        try:
            out["bedTime"] = _norm_bed(raw["bedTime"])
        except Invalid:
            pass
    return out


def view() -> dict:
    """GET /api/settings/priority — 지금 값 + 기본값 + 고친 칸 + 유형 이름·범위 (설정 모달이 그대로 그린다)."""
    cur, base = load(), C.default_settings()
    changed = ["safetyFactor"] if not same(cur["safetyFactor"], base["safetyFactor"]) else []
    changed += ["bedTime"] if cur["bedTime"] != base["bedTime"] else []
    changed += [f"defaultHours.{k}" for k in C.KIND_ORDER if not same(cur["defaultHours"][k], base["defaultHours"][k])]
    return {
        **cur, "defaults": base, "changed": changed,
        "kinds": [{"key": k, "label": C.KINDS[k]["label"]} for k in C.KIND_ORDER],
        "limits": {"safetyFactor": list(C.SAFETY_RANGE), "defaultHours": list(C.DEFAULT_HOURS_RANGE),
                   "bedTime": [C.BED_EARLIEST, C.BED_LATEST_AFTER_MIDNIGHT]},
    }


def save(patch: dict, reset: bool = False) -> dict:
    """PATCH /api/settings/priority {safetyFactor?, defaultHours?: {kind: h}, bedTime?} · reset=True 면 전부 기본값으로.
    null 을 주면 그 칸을 기본값으로 되돌린다. 기본값과 같은 값은 저장하지 않는다."""
    if not isinstance(patch, dict):
        raise Invalid("설정은 {safetyFactor, defaultHours, bedTime} 모양이어야 합니다")
    unknown = set(patch) - {"safetyFactor", "defaultHours", "bedTime"}
    if unknown:
        raise Invalid(f"모르는 설정입니다: {', '.join(sorted(unknown))}")
    base = C.default_settings()
    cur: dict[str, Any] = {} if reset else _read()
    cur = {k: v for k, v in cur.items() if k in ("safetyFactor", "defaultHours", "bedTime")}

    if "safetyFactor" in patch:
        v = patch["safetyFactor"]
        cur["safetyFactor"] = None if v is None else _num(v, "안전계수", *C.SAFETY_RANGE)
    if "defaultHours" in patch:
        dh = patch["defaultHours"]
        if dh is None:
            cur["defaultHours"] = {}
        elif not isinstance(dh, dict):
            raise Invalid("defaultHours 는 {assignment, quiz, video, project: 시간} 모양이어야 합니다")
        else:
            merged = dict(cur.get("defaultHours") or {})
            for k, v in dh.items():
                if k not in C.KINDS:
                    raise Invalid(f"모르는 과제 유형입니다: {k}")
                merged[k] = None if v is None else _num(v, f"{C.KINDS[k]['label']} 기본 시간", *C.DEFAULT_HOURS_RANGE)
            cur["defaultHours"] = merged
    if "bedTime" in patch:
        v = patch["bedTime"]
        cur["bedTime"] = None if v is None else _norm_bed(v)

    # 기본값과 같은 값 · 지운 값(None)은 빼고 저장
    out: dict[str, Any] = {}
    if cur.get("safetyFactor") is not None and not same(cur["safetyFactor"], base["safetyFactor"]):
        out["safetyFactor"] = cur["safetyFactor"]
    dh = {k: v for k, v in (cur.get("defaultHours") or {}).items()
          if k in C.KINDS and v is not None and not same(v, base["defaultHours"][k])}
    if dh:
        out["defaultHours"] = dh
    if cur.get("bedTime") is not None and cur["bedTime"] != base["bedTime"]:
        out["bedTime"] = cur["bedTime"]
    _write(out)
    return view()


def stored() -> Optional[dict]:
    """명령줄 표시용 — 파일에 실제로 적힌 값."""
    return _read() or None
