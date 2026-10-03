"""예약 수집 — 하루 한 번(SCHEDULE_AT, 기본 08:00) + 놓치면 켜지는 대로 + 네트워크 오류면 5·15·45분 뒤 재시도.
e클래스(F6_Eclass_agent/eclass/runner.py tick)와 같은 규칙이다.

    python -m bachelor tick [--force] [--log FILE]      작업 스케줄러가 부른다(run-scheduled.cmd)

작업 스케줄러는 매일 08:00 + 로그인할 때(2분 지연) + 놓친 시각은 켜지는 대로(StartWhenAvailable) tick 을 부른다.
tick 은 '가장 최근 08:00 이후 성공한 수집'(대시보드 버튼 포함)이 있으면 아무것도 하지 않는다 → 하루 한 번만 돈다.
원천이 전부 실패하면(코드 4 — 대개 인터넷 연결) 5 → 15 → 45분 뒤 다시 돈다(최대 3회). 기다리는 동안 잠금을 잡지 않으므로
그 사이 '지금 수집'이 성공하면 남은 재시도는 그만두고, 다음 날 08:00 이 오면 그 주기에 맡긴다.
일부 원천만 실패(코드 1)하면 재시도하지 않는다 — 형식 변경처럼 다시 해도 안 되는 실패라 화면에 빨갛게 보인다.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional

from . import config as C

OK_CODES = (0, 1)                 # 1 = 일부 원천 실패 — 그래도 그날 수집은 한 것으로 본다


def _at() -> tuple[int, int]:
    try:
        h, m = (int(x) for x in C.SCHEDULE_AT.split(":"))
        return h, m
    except ValueError:
        return 8, 0


def latest_slot(now: datetime) -> datetime:
    """now 이전(같으면 포함)의 가장 최근 예약 시각."""
    h, m = _at()
    slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return slot if slot <= now else slot - timedelta(days=1)


def next_slot(now: datetime) -> datetime:
    return latest_slot(now) + timedelta(days=1)


def last_run() -> dict:
    try:
        d = json.loads(C.LAST_RUN_FILE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def ran_ok_since(slot: datetime, last: Optional[dict] = None) -> Optional[dict]:
    last = last_run() if last is None else last
    if (last.get("started_at") or "") >= slot.isoformat(timespec="seconds") and last.get("exit_code") in OK_CODES:
        return last
    return None


def decide(now: datetime, last: Optional[dict] = None) -> dict:
    """이번 tick 에서 돌릴까 → {run, slot, by(schedule|catchup), reason}"""
    slot = latest_slot(now)
    done = ran_ok_since(slot, last)
    if done:
        return {"run": False, "slot": slot, "by": None,
                "reason": f"{slot:%m/%d %H:%M} 수집은 이미 했습니다 ({(done.get('started_at') or '')[11:16]} {done.get('by', '')})"}
    late = now - slot > timedelta(minutes=C.CATCHUP_AFTER_MIN)
    return {"run": True, "slot": slot, "by": "catchup" if late else "schedule",
            "reason": f"{slot:%m/%d %H:%M} 수집 {'따라잡기' if late else '정각 실행'}"}


# ── 재시도 대기 표시 (대시보드가 '재시도 대기 10:05' 로 보여 준다) ──

def set_retry(attempt: int, when: datetime, slot: datetime) -> None:
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    C.RETRY_FILE.write_text(json.dumps({"pid": os.getpid(), "attempt": attempt, "next_at": when.isoformat(timespec="seconds"),
                                        "slot": slot.isoformat(timespec="seconds")}), encoding="utf-8")


def clear_retry() -> None:
    C.RETRY_FILE.unlink(missing_ok=True)


def pending_retry(alive=None) -> Optional[dict]:
    """재시도를 기다리는 tick 이 살아 있으면 {attempt, next_at}. alive = pid 확인 함수(runner 가 넘긴다)."""
    try:
        d = json.loads(C.RETRY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict):
        return None
    if alive is not None and not (isinstance(d.get("pid"), int) and alive(d["pid"])):
        return None
    return {"attempt": d.get("attempt"), "next_at": d.get("next_at")}


def _wait_until(when: datetime, slot: datetime) -> str:
    """재시도 시각까지 기다린다 → 'ok' | 'succeeded'(그 사이 다른 수집이 성공) | 'next_slot'(다음 날 주기가 옴).
    절전으로 멈췄다 깨어나도 벽시계로 판단한다(30초마다 확인)."""
    while True:
        now = datetime.now()
        if latest_slot(now) > slot:
            return "next_slot"
        if ran_ok_since(slot):
            return "succeeded"
        if now >= when:
            return "ok"
        time.sleep(min(30.0, max(1.0, (when - now).total_seconds())))


def tick(force: bool = False, run=None) -> int:
    """작업 스케줄러 진입점. run = 수집 함수(by=…) — 테스트가 바꿔 끼운다."""
    if run is None:
        from .pipeline import run as pipeline_run
        run = lambda by: pipeline_run(by=by)   # noqa: E731
    now = datetime.now()
    d = decide(now)
    print(f"-- 예약 확인 {now:%Y-%m-%d %H:%M} · 매일 {C.SCHEDULE_AT} · {d['reason']}")
    if not d["run"] and not force:
        return 0
    slot: datetime = d["slot"]
    code = run(d["by"] or "schedule")
    attempt = 1
    try:
        while code == 4 and attempt <= len(C.RETRY_WAITS_MIN):
            wait = C.RETRY_WAITS_MIN[attempt - 1]
            when = datetime.now() + timedelta(minutes=wait)
            set_retry(attempt + 1, when, slot)
            print(f"-- 수집 실패(인터넷 연결 확인) → {wait}분 뒤({when:%H:%M}) 다시 시도합니다 ({attempt}/{len(C.RETRY_WAITS_MIN)})")
            why = _wait_until(when, slot)
            clear_retry()
            if why != "ok":
                print("-- 재시도 그만둠: " + ("그 사이 다른 수집이 성공했습니다" if why == "succeeded" else "다음 예약 시각이 됐습니다"))
                return 0 if why == "succeeded" else code
            attempt += 1
            code = run("retry")
        if code == 3:
            print("-- 다른 수집이 진행 중이라 넘깁니다")
            return 0
    finally:
        clear_retry()
    return code
