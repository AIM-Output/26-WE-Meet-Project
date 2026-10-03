"""주기 — 정각 기준 N시간 단위 실행 시각과 '이번 주기를 돌려야 하나' 판정 (F6-D1 · R10 · R11 · R18). 계산만 한다.

    4시간 → 00·04·08·12·16·20시        2시간 → 00·02·…·22시        6시간 → 00·06·12·18시        12시간 → 00·12시

작업 스케줄러는 이 시각마다 + 로그인할 때 + 놓쳤으면 켜지는 대로(StartWhenAvailable) `python -m eclass tick` 을 부른다.
tick 은 가장 최근 정각(slot) 이후에 이미 돈 실행이 있으면 아무것도 하지 않는다 → 로그인 트리거와 따라잡기가 겹쳐도
**한 번만** 돈다. 밀린 여러 주기를 몰아서 돌리지 않는다(최근 한 주기만, 미결 Q4 결정).
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from . import config as C


def slot_hours(interval: int) -> list[int]:
    interval = interval if interval in C.INTERVAL_CHOICES else C.DEFAULT_INTERVAL_HOURS
    return list(range(0, 24, interval))


def latest_slot(now: datetime, interval: int) -> datetime:
    """now 이전(같으면 포함)의 가장 최근 정각."""
    hours = slot_hours(interval)
    h = max(x for x in hours if x <= now.hour)
    return now.replace(hour=h, minute=0, second=0, microsecond=0)


def next_slot(now: datetime, interval: int) -> datetime:
    """now 다음 정각. 주기(2·4·6·12)가 24 의 약수라 가장 최근 정각 + 주기 = 다음 정각(자정을 넘으면 다음 날 00시)."""
    interval = interval if interval in C.INTERVAL_CHOICES else C.DEFAULT_INTERVAL_HOURS
    return latest_slot(now, interval) + timedelta(hours=interval)


def ran_since(runs: list[dict], since: datetime) -> Optional[dict]:
    """since 이후에 시작한 실행(건너뜀 제외)이 있으면 가장 최근 것."""
    key = since.isoformat(timespec="seconds")
    for r in runs:                                   # 최신 먼저
        if r.get("exit_code") == C.EXIT_BUSY:
            continue
        if (r.get("started_at") or "") >= key:
            return r
        break
    return None


def decide(now: datetime, interval: int, runs: list[dict]) -> dict:
    """이번 tick 에서 돌릴까. {run, slot, source('schedule'|'catchup'), reason}"""
    slot = latest_slot(now, interval)
    done = ran_since(runs, slot)
    if done:
        return {"run": False, "slot": slot, "source": None,
                "reason": f"이번 주기({slot:%H:%M})는 이미 실행했습니다 ({(done.get('started_at') or '')[11:16]} {done.get('source', '')})"}
    late = now - slot > timedelta(minutes=C.CATCHUP_AFTER_MIN)
    return {"run": True, "slot": slot, "source": "catchup" if late else "schedule",
            "reason": f"{slot:%H:%M} 주기 {'따라잡기' if late else '정각 실행'}"}
