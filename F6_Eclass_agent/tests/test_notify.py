"""마감 알림 (F6-D2 · R40~R44) · 변경·신규·실패 알림."""
from datetime import datetime

from conftest import NOW, FakePush, assign, write_data

from eclass import notify, reconcile, service


def test_fire_times_rules():
    due = datetime(2026, 10, 1, 23, 59)
    got = {c: (t, title) for c, t, title in notify.fire_times(due, "보고서", ["d3", "d1", "d0"])}
    assert got["d3"][0] == datetime(2026, 9, 28, 9, 0)
    assert got["d1"][0] == datetime(2026, 9, 30, 9, 0)
    assert got["d0"] == (datetime(2026, 10, 1, 9, 0), "오늘 23:59 마감 · 보고서")
    early = {c: t for c, t, _ in notify.fire_times(datetime(2026, 10, 1, 7, 30), "퀴즈", ["d0"])}
    assert early["d0"] == datetime(2026, 10, 1, 4, 30)          # 09:00 이전 마감 → 3시간 전 (R41)
    nine = {c: t for c, t, _ in notify.fire_times(datetime(2026, 10, 1, 9, 0), "x", ["d0"])}
    assert nine["d0"] == datetime(2026, 10, 1, 6, 0)            # 정각 09:00 마감도 '이미 지난 시각'이 되지 않게
    # '10월 4일 자정까지' = 10/5 00:00 (실측) → 10/4 이 마감일
    mid = {c: (t, title) for c, t, title in notify.fire_times(datetime(2026, 10, 5, 0, 0), "JIRA", ["d3", "d1", "d0"])}
    assert mid["d3"][0] == datetime(2026, 10, 1, 9, 0) and mid["d1"][0] == datetime(2026, 10, 3, 9, 0)
    assert mid["d0"] == (datetime(2026, 10, 4, 9, 0), "오늘 자정 마감 · JIRA")


def _setup(db, *items, when=datetime(2026, 9, 20, 12, 0)):
    write_data(list(items), stamp=str(when))
    reconcile.apply(db, now=when)


def test_reminders_delivered_once_and_gated(db):
    _setup(db, assign(1, "2026-10-01 23:59"), assign(2, "2026-09-29 23:59", submitted="제출 완료"))
    p = FakePush()
    assert notify._deliver_reminders(db, p, NOW) == 1           # 9/28 09:00 의 D-3 만 (제출한 과제는 없음, R44)
    (nid, row), = p.rows.items()
    assert nid == "dl:1:d3:202609280900" and row["title"] == "D-3 · 과제1" and row["href"] == "/?event=dl:1"
    assert row["missed"] is True                                # 3시간 늦게 배달 → 놓친 알림
    assert notify._deliver_reminders(db, p, NOW) == 0           # 같은 알림을 다시 만들지 않는다
    service.patch(db, "dl:1", user_done=True)
    assert notify._deliver_reminders(db, p, datetime(2026, 9, 30, 9, 1)) == 0   # 내가 체크함 → 남은 알림 취소


def test_no_flood_for_items_seen_late(db):
    """처음 본 때보다 앞선 알림 시점은 만들지 않는다 — D-1 에 처음 보면 D-3 은 건너뛴다."""
    _setup(db, assign(1, "2026-10-01 23:59"), when=datetime(2026, 9, 30, 8, 0))
    p = FakePush()
    assert notify._deliver_reminders(db, p, datetime(2026, 9, 30, 9, 5)) == 1
    assert list(p.rows) == ["dl:1:d1:202609300900"]
    assert p.rows["dl:1:d1:202609300900"]["missed"] is False


def test_past_due_gets_nothing(db):
    _setup(db, assign(1, "2026-09-25 23:59"))
    assert notify._deliver_reminders(db, FakePush(), NOW) == 0


def test_settings_choose_codes(db):
    _setup(db, assign(1, "2026-10-01 23:59"), when=datetime(2026, 9, 20))
    notify.save_settings(db, ["d0"], now=datetime(2026, 9, 20))
    p = FakePush()
    assert notify._deliver_reminders(db, p, datetime(2026, 10, 1, 9, 30)) == 1
    assert list(p.rows)[0].endswith(":d0:202610010900")
    import pytest
    with pytest.raises(service.Invalid):
        notify.save_settings(db, ["d7"])


def test_due_change_and_new_bundle(db):
    _setup(db, assign(1, "2026-10-01 23:59"))
    write_data([assign(1, "2026-10-04 18:00"), assign(2, "2026-10-05 23:59", name="새 보고서"),
                assign(3, "2026-10-06 23:59", name="퀴즈 준비")], stamp="b")
    reconcile.apply(db, now=NOW)
    p = FakePush()
    assert notify._deliver_changes(db, p, NOW) == 2
    chg = p.rows["dl-chg:1:202610041800"]
    assert chg["kind"] == "change" and chg["title"] == "마감 연장 · 과제1" and "10/1(목) 23:59 → 10/4(일) 18:00" in chg["body"]
    new = p.rows["dl-new:2026-09-28"]
    assert new["title"] == "새 과제 2건" and new["body"] == "새 보고서, 퀴즈 준비"
    assert notify._deliver_changes(db, p, NOW) == 0             # 보낸 변경은 다시 보내지 않는다
    write_data([assign(1, "2026-10-04 18:00"), assign(2, "2026-10-05 23:59", name="새 보고서"),
                assign(3, "2026-10-06 23:59", name="퀴즈 준비"), assign(4, "2026-10-07 23:59", name="넷째")], stamp="c")
    reconcile.apply(db, now=NOW)
    notify._deliver_changes(db, p, NOW)
    assert p.rows["dl-new:2026-09-28"]["title"] == "새 과제 3건"   # 하루치 묶음을 고쳐 쓴다 (R42)


def _run(started, code, attempt=1, error=None):
    return {"started_at": started, "finished_at": started, "exit_code": code, "attempt": attempt, "error": error}


def test_failure_alerts(state):
    p = FakePush()
    ok = _run("2026-09-27T08:00:00", 0)
    runs = [_run("2026-09-28T08:00:00", 2, error="세션 만료"), _run("2026-09-28T04:00:00", 4), ok]
    assert notify._deliver_failures(p, runs) == 1
    assert p.rows["dl-sys:login:2026-09-28T04:00:00"]["title"] == "e클래스 로그인이 필요합니다"
    runs = [_run("2026-09-28T12:00:00", 2), *runs]
    assert notify._deliver_failures(p, runs) == 1               # 3회째 → 연속 실패 알림 1건 (R15)
    assert p.rows["dl-sys:streak:2026-09-28T04:00:00"]["title"] == "e클래스 수집이 3회 연속 실패했습니다"
    assert notify._deliver_failures(p, runs) == 0


def test_deliver_without_push_is_noop(db):
    assert notify.deliver(db, None) == 0


def test_new_bundle_skips_items_already_done_or_past(db):
    """지난 주차 동영상을 처음 들여오면(이미 시청·마감 지남) '새 과제'로 알리지 않는다."""
    _setup(db, assign(1, "2026-10-01 23:59"))
    write_data([assign(1, "2026-10-01 23:59"), assign(2, "2026-09-14 23:59", name="지난 것"),
                assign(3, "2026-10-08 23:59", submitted="제출 완료", name="낸 것"), assign(4, "2026-10-09 23:59", name="새 것")],
               stamp="b")
    reconcile.apply(db, now=NOW)
    p = FakePush()
    notify._deliver_changes(db, p, NOW)
    assert p.rows["dl-new:2026-09-28"]["title"] == "새 과제 1건" and p.rows["dl-new:2026-09-28"]["body"] == "새 것"


def test_when_text_midnight():
    assert notify._when(datetime(2026, 10, 5, 0, 0)) == "10/4(일) 24:00"
    assert notify._when(datetime(2026, 10, 4, 23, 59)) == "10/4(일) 23:59"
