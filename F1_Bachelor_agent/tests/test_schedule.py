"""예약 수집 — 하루 한 번(08:00), 놓치면 따라잡기, 전부 실패면 5·15·45분 재시도, 신규 '전체 확인'."""
import json
from datetime import date, datetime

import pytest

from bachelor import config as C
from bachelor import schedule, service, store
from bachelor.register import register

from test_register_notify import P3, cand


def _last(started: str, code: int, by: str = "schedule") -> dict:
    return {"started_at": started, "exit_code": code, "by": by}


def test_slots():
    assert schedule.latest_slot(datetime(2026, 10, 1, 9, 30)) == datetime(2026, 10, 1, 8, 0)
    assert schedule.latest_slot(datetime(2026, 10, 1, 7, 59)) == datetime(2026, 9, 30, 8, 0)    # 08시 전이면 어제 것
    assert schedule.next_slot(datetime(2026, 10, 1, 9, 0)) == datetime(2026, 10, 2, 8, 0)


def test_decide_once_a_day():
    now = datetime(2026, 10, 1, 8, 2)
    assert schedule.decide(now, {})["by"] == "schedule"
    assert schedule.decide(datetime(2026, 10, 1, 13, 0), {})["by"] == "catchup"                  # 켜지는 대로 따라잡기
    # 오늘 08시 이후 성공(버튼 수집 포함)했으면 건너뜀 · 일부 실패(1)도 한 것으로 · 전부 실패(4)·어제 것은 다시
    assert schedule.decide(now, _last("2026-10-01T08:00:30", 0))["run"] is False
    assert schedule.decide(now, _last("2026-10-01T08:00:30", 1, "button"))["run"] is False
    assert schedule.decide(now, _last("2026-10-01T08:00:30", 4))["run"] is True
    assert schedule.decide(now, _last("2026-09-30T20:00:00", 0))["run"] is True


@pytest.fixture()
def no_last_run():
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    C.LAST_RUN_FILE.unlink(missing_ok=True)
    yield
    C.LAST_RUN_FILE.unlink(missing_ok=True)
    C.RETRY_FILE.unlink(missing_ok=True)


def test_tick_retries_on_network_failure(no_last_run, monkeypatch):
    calls, waits = [], []
    codes = iter([4, 4, 0])
    monkeypatch.setattr(schedule, "_wait_until", lambda when, slot: waits.append(schedule.pending_retry()) or "ok")
    code = schedule.tick(run=lambda by: calls.append(by) or next(codes))
    assert code == 0 and calls[1:] == ["retry", "retry"] and calls[0] in ("schedule", "catchup")
    assert [w["attempt"] for w in waits] == [2, 3]                                      # 대시보드가 '재시도 대기'로 본다
    assert schedule.pending_retry() is None


def test_tick_gives_up_after_three_retries_or_when_someone_succeeds(no_last_run, monkeypatch):
    calls = []
    monkeypatch.setattr(schedule, "_wait_until", lambda when, slot: "ok")
    assert schedule.tick(run=lambda by: calls.append(by) or 4) == 4
    assert len(calls) == 4                                                               # 첫 실행 + 재시도 3회
    calls.clear()
    monkeypatch.setattr(schedule, "_wait_until", lambda when, slot: "succeeded")         # 그 사이 '지금 수집' 성공
    assert schedule.tick(run=lambda by: calls.append(by) or 4) == 0 and len(calls) == 1


def test_tick_skips_when_done_today(no_last_run):
    now = datetime.now()
    slot = schedule.latest_slot(now)
    C.LAST_RUN_FILE.write_text(json.dumps(_last(slot.isoformat(timespec="seconds"), 0)), encoding="utf-8")
    calls = []
    assert schedule.tick(run=lambda by: calls.append(by) or 0) == 0 and calls == []
    assert schedule.tick(force=True, run=lambda by: calls.append(by) or 0) == 0 and len(calls) == 1


def test_ack_new_moves_items_back(db):
    register(db, "jnu_calendar", [cand("제2학기 개강", date(2026, 9, 1), type_="vacation")])
    db.execute("UPDATE events SET first_seen = '2000-01-01T00:00:00'")
    store.set_meta(db, "last_run_started", "2000-01-01T00:00:00")
    assert [e["isNew"] for e in service.list_events(db, P3)] == [True]
    service.ack_new(db)
    assert [e["isNew"] for e in service.list_events(db, P3)] == [False]                # 날짜순 목록으로
    store.set_meta(db, "last_run_started", "2999-01-01T00:00:00")                       # 다음 수집이 오면 그 뒤 것만 신규
    assert [e["isNew"] for e in service.list_events(db, P3)] == [False]
