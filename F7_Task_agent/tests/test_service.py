"""화면·연동 묶음 — /api/priority 응답 · 상위 3건(F7-R32·R33) · 상태 타일 · 명령줄 원천이 없을 때."""
from datetime import timedelta

from conftest import NOW, example_items, item, spec
from tasks import service, sources


def test_overview_groups_and_totals():
    items = example_items() + [item("dl:9", "2주차 실습", "2026-09-23T23:59:00"),
                               item("dl:10", "마감 없는 과제", None),
                               item("dl:11", "제출한 것", "2026-09-26T10:00:00", submitted=True)]
    ov = service.overview(items, NOW, spec())
    g = {x["key"]: x for x in ov["groups"]}
    assert [x["key"] for x in ov["groups"]] == ["overdue", "now", "week", "later", "nodue"]
    assert (g["overdue"]["count"], g["now"]["count"], g["week"]["count"], g["later"]["count"], g["nodue"]["count"]) \
        == (1, 1, 3, 1, 1)
    assert g["now"]["totalHours"] == 0.5
    assert g["week"]["totalHours"] == 3 + 50 + 5
    assert g["later"]["collapsed"] is True and g["now"]["collapsed"] is False
    assert ov["counts"]["open"] == 7
    assert ov["today"]["needHours"] == 0.5
    assert ov["items"][0]["id"] == "dl:9"                 # 놓친 마감이 맨 위


def test_top_three_skips_overdue_and_nodue():
    items = example_items() + [item("dl:9", "놓친 것", "2026-09-24T10:00:00"), item("dl:10", "마감 없음", None)]
    ov = service.overview(items, NOW, spec())
    assert [t["title"] for t in ov["top"]] == ["퀴즈 2회", "실습 과제", "팀 프로젝트 보고서"]
    assert set(ov["top"][0]) >= {"id", "title", "courseShort", "reason", "estimatedHours", "group"}


def test_course_filter():
    ov = service.overview(example_items(), NOW, spec(), course="캡스톤디자인")
    assert [r["id"] for r in ov["items"]] == ["dl:3", "dl:5"]
    ov = service.overview(example_items(), NOW, spec(), course="c-운영체제")      # 과목 id 로도
    assert [r["id"] for r in ov["items"]] == ["dl:2"]


def test_overview_today_uses_events_and_study():
    events = [{"title": "운영체제", "start": "2026-09-25T15:00:00", "end": "2026-09-25T16:15:00", "allDay": False,
               "extendedProps": {"kind": "class", "state": "scheduled"}}]
    ov = service.overview(example_items(), NOW, spec(), events=events, study_minutes=45)
    t = ov["today"]
    assert t["untilBedHours"] == 10 and t["busyHours"] == 1.25 and t["studyHours"] == 0.75 and t["leftHours"] == 8


def test_over_when_now_group_exceeds_today():
    items = [item("a", "보고서", (NOW + timedelta(hours=9)).isoformat(), est=6),
             item("b", "실습", (NOW + timedelta(hours=10)).isoformat(), est=5)]
    ov = service.overview(items, NOW, spec())
    assert ov["today"]["needHours"] == 11 and ov["today"]["leftHours"] == 10 and ov["today"]["over"] is True


def test_brief_for_morning_briefing():
    b = service.brief(example_items(), NOW, spec())
    assert [x["title"] for x in b["items"]] == ["퀴즈 2회", "실습 과제", "팀 프로젝트 보고서"]
    assert b["totalHours"] == 53.5 and b["totalText"] == "53시간 30분"
    assert b["text"] == "1) 퀴즈 2회 (30분) · 2) 실습 과제 (3시간) · 3) 팀 프로젝트 보고서 (50시간)"
    assert service.brief([], NOW) == {**service.brief([], NOW), "items": [], "text": "", "totalText": ""}


def test_status_summary_counts():
    items = example_items() + [item("dl:9", "오래 전", (NOW - timedelta(days=20)).isoformat()),
                               item("dl:10", "그제", (NOW - timedelta(days=2)).isoformat())]
    s = service.status_summary(items, NOW, spec())
    assert s["available"] is True
    assert (s["now"], s["week"], s["later"], s["overdue"]) == (1, 3, 1, 1)     # 2주 넘게 지난 것은 숫자에서 뺀다
    assert s["nowHours"] == 0.5 and len(s["top"]) == 3


def test_sources_missing_folders_are_reported_not_raised():
    sources.problems.clear()
    assert sources.assignments() == []
    assert sources.events("2026-10-01", "2026-10-02") == []
    assert sources.study_minutes() == 0.0
    assert any("F6" in p for p in sources.problems)
