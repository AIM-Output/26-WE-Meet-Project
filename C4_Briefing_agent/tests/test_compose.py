"""재료 → 섹션 (F10 5절 템플릿 · 섹션 규칙 · 각 기능이 브리핑에 싣기로 한 것)."""
from datetime import datetime, timedelta

from conftest import NOW, deadline, ev, ingredients

from briefing import compose


def _sec(built, key):
    return next((s for s in built["sections"] if s["key"] == key), None)


def _texts(built, key):
    return [it["text"] for it in _sec(built, key)["items"]]


def test_section_order_and_counts():
    b = compose.build(ingredients(), NOW, NOW - timedelta(hours=24))
    assert [s["key"] for s in b["sections"]] == ["attention", "classes", "events", "deadlines", "priority", "alerts"]
    assert b["counts"] == {"attention": 2, "classes": 3, "events": 6, "deadlines": 8, "priority": 3, "alerts": 3, "total": 25}
    assert b["summary"] == "주의 2 · 수업 3 · 일정 6 · 마감 8 · 먼저 할 것 3 · 새 알림 3"
    assert not b["empty"]


def test_attention_risky_course_and_overdue_on_top():
    """F3-R35 위험·초과 과목은 브리핑 상단 · F7 놓친 마감."""
    b = compose.build(ingredients(), NOW)
    items = _sec(b, "attention")["items"]
    assert items[0]["text"] == "컴퓨터네트워크 출결 위험"
    assert items[0]["sub"] == "한 번 더 결석하면 한도를 넘습니다"
    assert items[0]["href"] == "/attendance?course=c-net"
    assert items[1]["text"] == "놓친 마감 1건 · 미제출"


def test_classes_sorted_with_room_and_canceled():
    """F10-R10 시간 순 · 강의실 · 휴강 표시."""
    b = compose.build(ingredients(), NOW)
    items = _sec(b, "classes")["items"]
    assert [i["text"] for i in items] == ["09:00 컴퓨터네트워크", "13:00 운영체제", "15:00 소프트웨어공학론"]
    assert items[0]["sub"] == "공6-105 · 출결 위험" and items[0]["tone"] == "danger"
    assert items[1]["sub"] == "공7-223"
    assert items[2]["sub"] == "휴강" and items[2]["tone"] == "muted"
    assert items[1]["href"] == "/?view=week&event=cl:os:2026-10-26"


def test_events_today_only_all_day_first():
    """F10-R11 — 내 일정·할 일·학사(그날)·시험·F8 블록·F5 오늘 공부. 끝낸 할 일·어제 일정·수업·마감은 빠진다."""
    b = compose.build(ingredients(), NOW)
    assert _texts(b, "events") == [
        "종일 보고서 양식 출력", "종일 중간고사 기간", "오늘 공부 · 컴퓨터네트워크 22쪽 (40분)",
        "10:30 운영체제 중간고사", "11:00 품질 보고서", "19:00 스터디 모임",
    ]
    items = _sec(b, "events")["items"]
    assert items[0]["tag"] == "할 일" and items[0]["href"] == "/?event=13"
    assert items[1]["href"] == "/academic?event=ac:mid"
    assert items[3]["href"] == "/exams?exam=ex:os-mid" and items[3]["sub"] == "공7-101"
    assert items[4]["tag"] == "학습 블록" and items[4]["href"] == "/?event=pb:7"


def test_deadlines_d3_all_sources_nearest_first():
    """F10-R12 D-3 — 과제(제출 완료·지난 것·D-7 제외, 자정 마감은 전날) + 학사(알림 켜진 것 · 긴 기간은 끝나는 날) + 시험 + 장학 + 대외활동."""
    b = compose.build(ingredients(), NOW)
    assert _texts(b, "deadlines") == [
        "오늘 23:59 퀴즈 2회",
        "내일 24:00 3주차 실습",
        "D-1 지역인재 장학금",
        "D-2 컴퓨터네트워크 중간고사",
        "D-2 수강 철회",
        "D-2 일반휴학 (등록) 마감",
        "10/29(목) 18:00 품질 보고서",
        "D-3 SW 공모전",
    ]
    items = _sec(b, "deadlines")["items"]
    assert [i["tag"] for i in items] == ["과제", "과제", "장학", "시험", "학사", "학사", "과제", "대외활동"]
    assert items[0]["tone"] == "danger" and items[0]["sub"] == "컴퓨터네트워크 · 퀴즈"
    assert items[2]["href"] == "/scholarships?item=sch1"
    assert items[7]["href"] == "/opportunities?item=act1"


def test_priority_keeps_f7_order_with_reason_and_total():
    """F10-R13 — F7 상위 3건 그대로, 이유 한 줄과 함께."""
    b = compose.build(ingredients(), NOW)
    s = _sec(b, "priority")
    assert [i["text"] for i in s["items"]] == ["1) 퀴즈 2회", "2) 3주차 실습", "3) 품질 보고서"]
    assert s["items"][0]["sub"] == "컴퓨터네트워크 · 마감 15시간 전 · 30분 필요"
    assert s["footer"] == "합계 7시간 30분"


def test_alerts_skip_duplicates_and_old():
    """새 알림 — D-n 학사·과제별 마감 알림·브리핑 자신은 빼고(다른 섹션과 겹친다), 기준 시각 전 것도 뺀다."""
    b = compose.build(ingredients(), NOW, NOW - timedelta(hours=24))
    assert _texts(b, "alerts") == ["컴퓨터네트워크 결석 위험", "새 장학 1건", "새 과제 2건"]
    assert [i["tag"] for i in _sec(b, "alerts")["items"]] == ["출결", "장학", "과제"]
    b2 = compose.build(ingredients(), NOW)                       # 기준이 없으면 오래된 것도
    assert "오래된 공지" in _texts(b2, "alerts")


def test_all_empty_is_one_line():
    """F10-R16 — 전부 비었으면 '오늘은 일정이 없습니다' 만 (빈 섹션을 늘어놓지 않는다)."""
    b = compose.build({}, NOW)
    assert b["sections"] == [] and b["empty"]
    assert b["emptyText"] == "오늘은 일정이 없습니다" and b["summary"] == "오늘은 일정이 없습니다"


def test_empty_deadlines_keeps_one_line_others_hidden():
    """5절 섹션 규칙 — 마감 임박만 '사흘 안에 마감이 없습니다', 나머지 빈 섹션은 숨긴다."""
    b = compose.build({"events": [ev("1", "스터디", "2026-10-26T19:00:00")]}, NOW)
    assert [s["key"] for s in b["sections"]] == ["events", "deadlines"]
    d = _sec(b, "deadlines")
    assert d["items"] == [] and d["empty"] == "사흘 안에 마감이 없습니다"


def test_midnight_due_counts_as_previous_day():
    """F6 자정 규칙 — 10/30 00:00 마감은 10/29 마감(D-3), 10/31 00:00 은 D-4 라 빠진다."""
    ing = {"events": [deadline("dl:a", "A", "2026-10-30T00:00:00"), deadline("dl:b", "B", "2026-10-31T00:00:00")]}
    b = compose.build(ing, NOW)
    assert _texts(b, "deadlines") == ["10/29(목) 24:00 A"]


def test_lines_capped_but_count_kept():
    many = {"events": [deadline(f"dl:{i}", f"과제 {i}", "2026-10-27T23:59:00") for i in range(40)]}
    s = _sec(compose.build(many, NOW), "deadlines")
    assert s["count"] == 40 and len(s["items"]) == 30 and s["more"] == 10


def test_facts_numbers_and_titles_only():
    """LLM 에 넘기는 것은 숫자와 제목 수준 — 강의실·알림 본문은 없다 (10절 프라이버시)."""
    f = compose.facts(compose.build(ingredients(), NOW, NOW - timedelta(hours=24)))
    raw = str(f)
    assert f["counts"]["deadlines"] == 8
    assert "공7-223" not in raw and "한 번 더 결석하면 F" not in raw
    assert f["priority"] == ["1) 퀴즈 2회", "2) 3주차 실습", "3) 품질 보고서"]


def test_weekday_word():
    assert compose.day_word(datetime(2026, 10, 29).date(), NOW.date()) == "10/29(목)"
    assert compose.day_word(NOW.date(), NOW.date()) == "오늘"
