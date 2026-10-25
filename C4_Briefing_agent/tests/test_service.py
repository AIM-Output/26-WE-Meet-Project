"""만들기 규칙 — 예정 시각 · 정시/놓침 · 하루 한 번 · 수집 기다리기 · 다시 만들기 · 꺼짐 · 소급 없음 · 보관 · 알림 1건 (F10 4절 · 9절)."""
from datetime import datetime, timedelta

import pytest
from conftest import NOW, FakeSources

from briefing import service


def test_before_scheduled_time_no_card():
    f = FakeSources()
    t = service.ensure_today(f.src, NOW - timedelta(minutes=30))
    assert t["state"] == "before" and t["briefing"] is None
    assert f.calls == 0                                     # 재료도 읽지 않는다


def test_scheduled_once_a_day_with_one_notification():
    f = FakeSources()
    t = service.ensure_today(f.src, NOW)
    b = t["briefing"]
    assert t["state"] == "ready" and t["created"]
    assert b["source"] == "scheduled" and not b["missed"] and b["date"] == "2026-10-26"
    assert b["generatedAt"] == "2026-10-26T08:00:00" and b["scheduledFor"] == "08:00"
    assert b["counts"]["deadlines"] == 8 and b["headline"] is None   # LLM 없음 — 그 줄만 빠진다
    assert len(f.notified) == 1
    nid, title, body, href, fire_at, missed = f.notified[0]
    assert nid == "briefing:2026-10-26" and title == "오늘 브리핑이 도착했습니다" and href == "/"
    assert body == b["summary"] and fire_at == NOW and missed is False

    calls = f.calls
    t2 = service.ensure_today(f.src, NOW + timedelta(hours=3))
    assert not t2["created"] and t2["briefing"]["generatedAt"] == b["generatedAt"]   # 스냅샷 그대로 (F10-R04)
    assert f.calls == calls and len(f.notified) == 1


def test_catchup_when_pc_was_off():
    """F10-R02 · D2 — 예정 시각에서 60분 넘게 지나 켜면 그 시점 기준으로 만들고 '놓친 브리핑'."""
    f = FakeSources()
    b = service.ensure_today(f.src, datetime(2026, 10, 26, 10, 24))["briefing"]
    assert b["source"] == "catchup" and b["missed"] and b["generatedAt"].endswith("10:24:00")
    assert f.notified[0][1] == "놓친 브리핑 — 10:24 기준으로 만들었습니다" and f.notified[0][5] is True
    assert service.ensure_today(f.src, datetime(2026, 10, 26, 8, 59) + timedelta(hours=3))["briefing"]["source"] == "catchup"


def test_within_an_hour_is_still_scheduled():
    f = FakeSources()
    assert service.ensure_today(f.src, NOW + timedelta(minutes=55))["briefing"]["source"] == "scheduled"


def test_waits_for_collection_up_to_five_minutes():
    """9절 — 수집이 돌고 있으면 끝날 때까지(최대 5분) 기다렸다가 만든다."""
    f = FakeSources(busy=["e클래스"])
    t = service.ensure_today(f.src, NOW)
    assert t["state"] == "pending" and t["waitingFor"] == ["e클래스"] and t["briefing"] is None
    assert service.ensure_today(f.src, NOW + timedelta(minutes=3))["state"] == "pending"
    t = service.ensure_today(f.src, NOW + timedelta(minutes=5))
    assert t["state"] == "ready" and t["briefing"]["source"] == "scheduled"


def test_generates_as_soon_as_collection_ends():
    f = FakeSources(busy=["학사일정"])
    assert service.ensure_today(f.src, NOW)["state"] == "pending"
    f.busy_names.clear()
    t = service.ensure_today(f.src, NOW + timedelta(minutes=2))
    assert t["state"] == "ready" and t["briefing"]["generatedAt"].endswith("08:02:00")


def test_regenerate_overwrites_but_remembers_missed():
    """F10-R24 다시 만들기 — 지금 기준으로 덮어쓴다. 처음에 놓친 브리핑이었다는 것은 남고, 알림은 새로 남기지 않는다."""
    f = FakeSources()
    service.ensure_today(f.src, datetime(2026, 10, 26, 10, 24))
    f.ing["priority"]["items"] = f.ing["priority"]["items"][:1]
    b = service.regenerate(f.src, datetime(2026, 10, 26, 11, 0))
    assert b["source"] == "manual" and b["firstSource"] == "catchup" and b["missed"]
    assert b["generatedAt"].endswith("11:00:00") and b["firstGeneratedAt"].endswith("10:24:00")
    assert b["counts"]["priority"] == 1
    assert len(f.notified) == 1
    assert service.get("2026-10-26")["generatedAt"].endswith("11:00:00")


def test_off_means_no_card_but_manual_still_works():
    """F10-R06 — 끄면 카드 없음(state=off). /briefing 에서 손으로 만든 것은 보인다."""
    f = FakeSources()
    service.save_settings({"enabled": False})
    t = service.ensure_today(f.src, NOW + timedelta(hours=1))
    assert t["state"] == "off" and t["briefing"] is None and f.calls == 0
    service.regenerate(f.src, NOW + timedelta(hours=2))
    t = service.ensure_today(f.src, NOW + timedelta(hours=3))
    assert t["state"] == "off" and t["briefing"]["source"] == "manual"
    assert f.notified == []


def test_custom_time():
    f = FakeSources()
    service.save_settings({"time": "07:00"})
    t = service.ensure_today(f.src, datetime(2026, 10, 26, 7, 0))
    assert t["state"] == "ready" and t["briefing"]["scheduledFor"] == "07:00"


def test_no_retroactive_briefings():
    """F10-R03 · 9절 '여러 날 만에 접속' — 오늘 것만 만든다."""
    f = FakeSources()
    service.ensure_today(f.src, NOW)
    service.ensure_today(f.src, datetime(2026, 10, 29, 9, 30))
    assert [i["date"] for i in service.history()["items"]] == ["2026-10-29", "2026-10-26"]
    with pytest.raises(service.NotFound):
        service.get("2026-10-27")


def test_keep_days_prunes_old():
    f = FakeSources()
    service.ensure_today(f.src, datetime(2026, 10, 1, 8, 0))
    service.ensure_today(f.src, datetime(2026, 10, 20, 8, 0))
    service.save_settings({"keepDays": 7}, today=datetime(2026, 10, 26).date())
    service.ensure_today(f.src, NOW)
    assert [i["date"] for i in service.history()["items"]] == ["2026-10-26", "2026-10-20"]
    service.save_settings({"keepDays": 14}, today=datetime(2026, 11, 5).date())
    assert [i["date"] for i in service.history()["items"]] == ["2026-10-26"]


def test_missing_ingredient_becomes_gap():
    """9절 — 시간표 데이터가 없으면 있는 섹션만. 못 읽은 재료는 gaps 로 적는다."""
    f = FakeSources(fail=("classes",))
    b = service.ensure_today(f.src, NOW)["briefing"]
    assert b["gaps"] == ["F3 출결(수업)"]
    assert "classes" not in [s["key"] for s in b["sections"]] and b["counts"]["deadlines"] == 8


def test_alerts_since_previous_briefing():
    """새 알림은 지난 브리핑 이후 것만 — 어제 저녁 브리핑을 다시 만들었다면 그 뒤의 알림만."""
    f = FakeSources()
    service.regenerate(f.src, datetime(2026, 10, 25, 21, 0))
    b = service.ensure_today(f.src, NOW)["briefing"]
    alerts = next(s for s in b["sections"] if s["key"] == "alerts")
    assert [i["text"] for i in alerts["items"]] == ["새 장학 1건", "새 과제 2건"]


def test_headline_from_chat():
    f = FakeSources()
    f.src.headline_chat = lambda s, u: "퀴즈 마감이 오늘이라 가장 급합니다."
    b = service.ensure_today(f.src, NOW)["briefing"]
    assert b["headline"] == "퀴즈 마감이 오늘이라 가장 급합니다." and b["promptVersion"]


def test_empty_day():
    f = FakeSources(ing={})
    b = service.ensure_today(f.src, NOW)["briefing"]
    assert b["empty"] and b["emptyText"] == "오늘은 일정이 없습니다" and b["sections"] == []
    assert f.notified[0][2] == "오늘은 일정이 없습니다"


def test_status_block():
    f = FakeSources()
    s = service.status(f.src, NOW - timedelta(hours=1))
    assert s["state"] == "before" and s["today"] is None and s["time"] == "08:00"
    s = service.status(f.src, NOW)
    assert s["state"] == "ready" and s["today"]["summary"].startswith("주의 2") and s["updatedAt"]
