"""시험 목록 · 계획 등록 · 진도 · 캘린더 (F5-R03·R05·R23·R30~R37)."""
from datetime import date

import pytest

from exams import service, store

from conftest import TODAY, add_exam, courses, make_eclass  # noqa: E402

MIDTERM = """1. 일정: 10월 23일 금요일 오후 2시부터 3시까지
2. 위치: 공7-223
4. 시험 범위: 3~7주차"""


def plan_for(con, exam_id, **options):
    # 요구사항정의서 5절 예시의 입력으로 고정한다(복습 2일 · 쪽당 2.5분) — 기본값이 바뀌어도 이 시험들은 규칙을 본다
    o = {"totalPages": 120, "reviewDays": 2, "pageMinutes": 2.5, **options}
    if "difficulty" in options and "pageMinutes" not in options:
        o.pop("pageMinutes")
    return service.create_plan(con, exam_id, o, TODAY, courses)


# ---------------------------------------------------------------- 공지 동기화 (F5-R01~R03)

def test_sync_creates_and_is_idempotent(db):
    make_eclass([("74261", "2026-10-10 09:00", "중간고사 안내", MIDTERM)])
    first = service.sync_notices(db, TODAY, get_courses=courses)
    assert (first["new"], first["updated"]) == (1, 0)
    again = service.sync_notices(db, TODAY, get_courses=courses)
    assert (again["new"], again["updated"]) == (0, 0)

    row = store.exam_rows(db)[0]
    assert row["date"] == "2026-10-23" and row["time"] == "14:00" and row["place"] == "공7-223"
    assert store.jload(row["scope_weeks"], []) == [3, 4, 5, 6, 7]
    assert row["source"] == "notice" and row["status"] == "confirmed"
    assert row["id"].startswith("ex:74261:")


def test_sync_detects_postponement_and_notifies(db):
    make_eclass([("74261", "2026-10-10 09:00", "중간고사 안내", "일시: 10월 23일 오후 2시")])
    service.sync_notices(db, TODAY, get_courses=courses)
    make_eclass([("74261", "2026-10-14 09:00", "중간고사 연기 안내", "일시: 10월 30일 오후 2시")])
    sent = []
    out = service.sync_notices(db, TODAY, notify=sent.append, get_courses=courses)

    assert out["updated"] == 1 and len(out["postponed"]) == 1
    assert out["postponed"][0]["from"] == "2026-10-23" and out["postponed"][0]["to"] == "2026-10-30"
    assert len(store.exam_rows(db)) == 1             # 같은 시험이다 (새 줄이 생기지 않는다)
    row = store.exam_rows(db)[0]
    assert row["date"] == "2026-10-30"
    assert store.jload(row["changed"], {})["from"] == "2026-10-23"
    assert len(store.jload(row["evidence"], [])) == 2          # 근거는 쌓인다
    assert sent and sent[0]["kind"] == "exam" and "바뀌었습니다" in sent[0]["title"]


def test_sync_does_not_overwrite_user_edits(db):
    make_eclass([("74261", "2026-10-10 09:00", "중간고사 안내", "일시: 10월 23일 오후 2시")])
    service.sync_notices(db, TODAY, get_courses=courses)
    eid = store.exam_rows(db)[0]["id"]
    service.patch_exam(db, eid, {"date": "2026-10-24", "place": "내가 고친 곳"}, courses, TODAY)

    make_eclass([("74261", "2026-10-14 09:00", "중간고사 연기", "일시: 10월 30일 오후 2시")])
    out = service.sync_notices(db, TODAY, get_courses=courses)
    assert out["updated"] == 0
    row = store.exam_rows(db)[0]
    assert (row["date"], row["place"]) == ("2026-10-24", "내가 고친 곳")


def test_sync_does_not_resurrect_deleted(db):
    make_eclass([("74261", "2026-10-10 09:00", "중간고사 안내", "일시: 10월 23일 오후 2시")])
    service.sync_notices(db, TODAY, get_courses=courses)
    eid = store.exam_rows(db)[0]["id"]
    service.delete_exam(db, eid)
    assert store.exam_rows(db) == []

    out = service.sync_notices(db, TODAY, get_courses=courses)
    assert out["new"] == 0 and store.exam_rows(db) == []


def test_manual_exam_wins_over_notice(db):
    """같은 과목·같은 날짜면 수기를 우선한다 (F5 8절)."""
    add_exam(db, when="2026-10-23", etype="quiz")
    make_eclass([("74261", "2026-10-10 09:00", "퀴즈 안내", "일시: 10월 23일 오후 2시 퀴즈")])
    out = service.sync_notices(db, TODAY, get_courses=courses)
    assert out["new"] == 0
    assert [r["source"] for r in store.exam_rows(db)] == ["manual"]


def test_review_status_shows_in_overview(db):
    make_eclass([("74261", "2026-10-10 09:00", "수업 안내", "10월 23일: 기획서 발표")])
    service.sync_notices(db, TODAY, get_courses=courses)
    o = service.overview(db, courses, today=TODAY)
    assert o["counts"]["review"] == 1
    assert o["review"][0]["needsReview"] is True
    assert o["review"][0]["evidence"][0]["quote"]


# ---------------------------------------------------------------- 시험 추가·수정 (F5-R03)

def test_add_exam(db):
    e = add_exam(db, when="2026-10-23", etype="midterm", time="14:00", place="공7-223")
    assert e["type"] == "midterm" and e["dday"] == 10 and e["ddayLabel"] == "D-10"
    assert e["source"] == "manual" and e["edited"] is True
    assert e["course"] == "소프트웨어공학론" and e["color"] == "#d97706"
    assert e["weekday"] == "금"


def test_add_exam_rejects_duplicate(db):
    add_exam(db, when="2026-10-23")
    with pytest.raises(service.Conflict):
        add_exam(db, when="2026-10-23")
    add_exam(db, when="2026-10-23", etype="quiz")    # 유형이 다르면 같은 날 가능


@pytest.mark.parametrize("body", [
    {"type": "midterm"},                             # 날짜가 없다
    {"courseId": "74261", "type": "midterm", "date": "10/23"},
    {"courseId": "없는과목", "type": "midterm", "date": "2026-10-23"},
    {"courseId": "74261", "type": "시험", "date": "2026-10-23"},
    {"courseId": "74261", "date": "2026-10-23", "time": "2시"},
    {"courseId": "74261", "date": "2026-10-23", "time": "14:00", "endTime": "13:00"},
    {"courseId": "74261", "date": "2026-10-23", "scopeWeeks": [99]},
    {"courseId": "74261", "date": "2026-10-23", "몰라": 1},
])
def test_add_exam_validation(db, body):
    with pytest.raises((service.Invalid, service.Conflict)):
        service.add_exam(db, body, courses, today=TODAY)


def test_patch_exam_confirms_review(db):
    make_eclass([("74261", "2026-10-10 09:00", "수업 안내", "10월 23일: 기획서 발표")])
    service.sync_notices(db, TODAY, get_courses=courses)
    eid = store.exam_rows(db)[0]["id"]
    out = service.patch_exam(db, eid, {"time": "15:00"}, courses, TODAY)
    assert out["status"] == "confirmed" and out["needsReview"] is False
    assert out["time"] == "15:00" and out["edited"] is True


def test_patch_exam_cannot_change_course(db):
    e = add_exam(db)
    with pytest.raises(service.Invalid):
        service.patch_exam(db, e["id"], {"courseId": "74245"}, courses, TODAY)


# ---------------------------------------------------------------- 미리보기 · 등록 (F5-R30·R31)

def test_preview_does_not_save(db):
    e = add_exam(db)
    out = service.preview(db, e["id"], {"totalPages": 120}, TODAY, courses)
    # 기본값: 마무리 복습 하루(시험 전날) · 보통 쪽당 1.5분 (2026-10-02) → 학습일 9일
    assert out["state"] == "draft" and out["studyDays"] == 9 and out["reviewDayDates"] == ["2026-10-22"]
    assert out["pageMinutes"] == 1.5
    assert store.plan_rows(db) == []                 # 미리보기는 저장하지 않는다 (F5 D3)


def test_create_plan_makes_blocks_only_on_study_calendar(db):
    """학습 블록은 공부 캘린더에만 — 전체 캘린더(/api/events)에는 시험만 들어간다 (2026-10-01)."""
    e = add_exam(db, time="14:00")
    out = plan_for(db, e["id"])
    assert out["plan"]["state"] == "active"
    assert "공부 캘린더에 넣었습니다" in out["message"]

    evs = service.calendar_events(db, None, None, courses, TODAY)
    assert [x["extendedProps"]["kind"] for x in evs] == ["exam"]
    assert evs[0]["start"] == "2026-10-23T14:00:00"
    assert evs[0]["extendedProps"]["color"] == "#9F2F2D" and evs[0]["editable"] is False

    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)
    blocks = [b for d in cal["days"] for b in d["blocks"]]
    assert len(blocks) == 10                         # 학습 8일 + 복습 2일
    assert sum(b["pages"] for b in blocks) == 120


def test_exam_without_time_is_all_day(db):
    add_exam(db)
    evs = service.calendar_events(db, None, None, courses, TODAY)
    ev = evs[0]
    assert ev["allDay"] is True
    assert ev["start"] == "2026-10-23" and ev["end"] == "2026-10-24"   # end 는 exclusive (C1-R14)
    assert ev["extendedProps"]["timeUnknown"] is True


def test_create_plan_replaces_previous(db):
    e = add_exam(db)
    first = plan_for(db, e["id"])
    second = plan_for(db, e["id"], difficulty="hard")
    assert first["plan"]["planId"] != second["plan"]["planId"]
    assert [p["state"] for p in store.plan_rows(db)] == ["active", "canceled"]
    assert len(store.days(db, first["plan"]["planId"])) == 0            # 미완료 블록은 치운다
    assert store.active_plan(db, e["id"])["id"] == second["plan"]["planId"]


def test_create_plan_keeps_done_blocks_when_replacing(db):
    e = add_exam(db)
    first = plan_for(db, e["id"])
    pid = first["plan"]["planId"]
    service.patch_day(db, pid, TODAY.isoformat(), {"done": True}, TODAY, courses)

    second = plan_for(db, e["id"])
    days = store.days(db, second["plan"]["planId"])
    assert [d["date"] for d in days if d["done"]] == [TODAY.isoformat()]
    assert sum(d["pages"] for d in days) == 120      # 완료분을 포함해 총 분량이 유지된다
    assert len(store.days(db, pid)) == 1             # 옛 계획에는 완료한 하루만 남는다


def test_plan_needs_something_to_register(db):
    e = add_exam(db, when=TODAY.isoformat())         # 시험이 오늘 — 나눌 날이 없다
    with pytest.raises(service.Conflict):
        plan_for(db, e["id"])


# ---------------------------------------------------------------- 진도 · 재조정 (F5-R32~R35)

def test_done_check_updates_progress(db):
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    out = service.patch_day(db, pid, "2026-10-13", {"done": True}, TODAY, courses)
    pr = out["plan"]["progress"]
    assert pr["donePages"] == 15 and pr["percent"] == 13
    assert out["day"]["done"] is True and out["day"]["doneAt"]
    assert out["plan"]["behind"] is False


def test_behind_is_measured_against_yesterday(db):
    """지연 = 어제까지의 계획 분량 − 완료 분량 (F5 5절)."""
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    later = date(2026, 10, 16)                       # 10/13·14·15 을 안 했다
    p = store.plan(db, pid)
    view = service.plan_view(p, store.days(db, pid), store.exam(db, e["id"]), later)
    assert view["behind"] is True
    assert view["progress"]["behindPages"] == 45
    assert view["progress"]["behindDays"] == 3
    assert "3일 밀렸습니다" in view["behindMessage"] and "하루" in view["behindMessage"]


def test_rebalance_previews_only(db):
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    service.patch_day(db, pid, "2026-10-13", {"done": True}, TODAY, courses)
    later = date(2026, 10, 16)
    out = service.rebalance(db, pid, None, later, courses)

    assert out["state"] == "draft"
    assert out["carried"]["pages"] == 15
    assert out["totals"]["pages"] == 120             # 완료 15 + 남은 105
    assert out["dailyPages"] == 21                   # ceil(105 / 5) — 10/16~10/20
    assert out["rebalanceOf"]["planId"] == pid
    # 캘린더는 그대로다 (F5 5절 — 제안만 한다)
    assert [d["pages"] for d in store.days(db, pid)][:2] == [15, 15]


def test_move_block_to_an_excluded_day(db):
    """제외일로 뒀던 날에 결국 하기로 했다 — 그 날로 옮긴다 (F5-R32)."""
    e = add_exam(db)
    pid = plan_for(db, e["id"], excludedDates=["2026-10-15"])["plan"]["planId"]
    out = service.patch_day(db, pid, "2026-10-14", {"date": "2026-10-15"}, TODAY, courses)
    dates = [d["date"] for d in out["plan"]["days"]]
    assert "2026-10-14" not in dates and dates.count("2026-10-15") == 1
    moved = [d for d in out["plan"]["days"] if d["date"] == "2026-10-15"][0]
    assert moved["moved"] is True
    assert out["plan"]["progress"]["plannedPages"] == 120        # 분량은 그대로다


def test_move_block_onto_a_busy_day_merges(db):
    """이미 분량이 있는 날로 옮기면 그 날에 합친다 — 블록이 사라지거나 둘이 되지 않는다."""
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    out = service.patch_day(db, pid, "2026-10-14", {"date": "2026-10-19"}, TODAY, courses)
    days = {d["date"]: d for d in out["plan"]["days"]}
    assert "2026-10-14" not in days
    assert days["2026-10-19"]["pages"] == 30 and days["2026-10-19"]["moved"] is True
    assert out["plan"]["progress"]["plannedPages"] == 120


def test_move_block_rejects_done_or_late_dates(db):
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    service.patch_day(db, pid, "2026-10-15", {"done": True}, TODAY, courses)
    with pytest.raises(service.Conflict):
        service.patch_day(db, pid, "2026-10-14", {"date": "2026-10-15"}, TODAY, courses)
    with pytest.raises(service.Invalid):
        service.patch_day(db, pid, "2026-10-14", {"date": "2026-10-25"}, TODAY, courses)


def test_plan_closes_when_all_done(db):
    e = add_exam(db, when="2026-10-16")
    pid = plan_for(db, e["id"], totalPages=10)["plan"]["planId"]
    for d in store.days(db, pid):
        out = service.patch_day(db, pid, d["date"], {"done": True}, TODAY, courses)
    assert out["plan"]["state"] == "done"
    assert out["plan"]["progress"]["percent"] == 100


def test_cancel_keeps_done_blocks(db):
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    service.patch_day(db, pid, "2026-10-13", {"done": True}, TODAY, courses)
    out = service.cancel_plan(db, pid, TODAY)
    assert out["blocksRemoved"] == 9 and out["blocksKept"] == 1

    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)
    blocks = [b for d in cal["days"] for b in d["blocks"]]
    assert len(blocks) == 1 and blocks[0]["done"] is True       # 해 놓은 공부는 공부 캘린더에 남는다
    with pytest.raises(service.Conflict):
        service.cancel_plan(db, pid, TODAY)


def test_close_past_plan(db):
    """시험일이 지나면 계획을 닫고, 안 한 블록은 캘린더에서 사라진다 (F5 8절)."""
    e = add_exam(db, when="2026-10-16")
    pid = plan_for(db, e["id"], totalPages=10)["plan"]["planId"]
    service.patch_day(db, pid, "2026-10-13", {"done": True}, TODAY, courses)
    assert service.close_past(db, date(2026, 10, 20)) == 1
    assert store.plan(db, pid)["state"] == "done"

    later = date(2026, 10, 20)
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, later)
    blocks = [b for d in cal["days"] for b in d["blocks"]]
    assert [b["done"] for b in blocks] == [True]
    assert len(store.days(db, pid)) == 3             # 못 한 것은 진도 화면에 기록으로 남는다


def test_delete_exam_removes_plan(db):
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    service.delete_exam(db, e["id"])
    assert store.exam_rows(db) == [] and store.plan(db, pid) is None
    assert service.calendar_events(db, None, None, courses, TODAY) == []
    assert service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)["days"] == []


# ---------------------------------------------------------------- 여러 시험 (2026-10-07 — 합산 상한 없음)

def test_heavy_day_with_other_plans_is_not_flagged(db):
    """같은 날 다른 과목 계획이 많아도 경고하지 않는다 — 합산 상한(F5-R23)은 하루 기준과 함께 없앴다."""
    a = add_exam(db, when="2026-10-23", course="74261")
    b = add_exam(db, when="2026-10-24", course="74245")
    plan_for(db, a["id"], totalPages=600, pageMinutes=4)
    out = service.preview(db, b["id"], {"totalPages": 600, "difficulty": "hard", "reviewDays": 2,
                                        "pageMinutes": 4}, TODAY, courses)
    assert out["verdict"] == "ok" and "overlap" not in out


# ---------------------------------------------------------------- 오늘 · 상태 · 범위

def test_today_block_and_status(db):
    e = add_exam(db, time="14:00")
    plan_for(db, e["id"])
    block = service.today_block(db, TODAY, service.course_map(courses))
    assert block["totalPages"] == 15
    assert "소프트웨어공학론 15쪽" in block["text"]
    assert block["nextExam"]["ddayLabel"] == "D-10"

    st = service.status_summary(db, courses, TODAY)
    assert st["available"] and st["upcoming"] == 1 and st["activePlans"] == 1
    assert st["todayPages"] == 15 and st["behind"] == 0


def test_behind_alerts_go_to_notification_center(db):
    e = add_exam(db)
    plan_for(db, e["id"])
    sent = []
    alerts = service.behind_alerts(db, date(2026, 10, 16), sent.append, courses)
    assert len(alerts) == 1 and alerts[0]["kind"] == "exam"
    assert "밀렸습니다" in alerts[0]["body"]
    assert alerts[0]["href"].endswith("step=progress")
    assert sent == alerts


def test_scope_fills_pages_from_materials(db, materials):
    """범위 안 F4 자료의 쪽수가 기본 분량이 된다 (F5-R10)."""
    e = add_exam(db, scopeWeeks=[1, 2, 3])
    out = service.preview(db, e["id"], None, TODAY, courses)
    assert out["totalPages"] == 120                  # 30 + 40 + 50 (중복·없는 파일 제외)
    assert out["scope"]["pages"] == 120
    o = service.default_options(db, store.exam(db, e["id"]), TODAY)
    assert o["unit"] == "pages" and o["totalPages"] == 120


def test_scope_without_materials_asks_for_input(db):
    e = add_exam(db)
    with pytest.raises(service.Invalid) as err:
        service.preview(db, e["id"], None, TODAY, courses)
    assert "쪽수" in str(err.value)
    out = service.preview(db, e["id"], {"unit": "minutes", "totalMinutes": 300}, TODAY, courses)
    assert out["verdict"] == "ok" and out["totalPages"] == 0


def test_plan_stale_when_scope_changes(db, materials):
    e = add_exam(db, scopeWeeks=[1, 2])
    plan_for(db, e["id"], totalPages=0)              # 자료에서 채운다 (30 + 40)
    out = service.patch_exam(db, e["id"], {"scopeWeeks": [1, 2, 3]}, courses, TODAY)
    assert out["planStale"] and "범위" in out["planStale"]["message"]


def test_semester_filter(db):
    add_exam(db, when="2026-10-23")
    add_exam(db, when="2026-04-20", etype="final")
    o = service.overview(db, courses, today=TODAY)
    assert o["semester"]["id"] == "2026-2"
    assert [e["date"] for e in o["exams"]] == ["2026-10-23"]
    assert o["semesters"] == ["2026-2", "2026-1"]
    o1 = service.overview(db, courses, "2026-1", TODAY)
    assert [e["date"] for e in o1["past"]] == ["2026-04-20"]
    with pytest.raises(service.Invalid):
        service.overview(db, courses, "2026학년도", TODAY)


def test_overview_picks_up_new_notices_by_itself(db):
    """새 시험 공지가 올라오면 아무 것도 누르지 않아도 목록에 들어온다 (F5-R01 · ensure_sync)."""
    assert service.overview(db, courses, today=TODAY)["counts"]["total"] == 0
    make_eclass([("74261", "2026-10-10 09:00", "중간고사 안내", MIDTERM)])
    o = service.overview(db, courses, today=TODAY)
    assert [e["date"] for e in o["exams"]] == ["2026-10-23"]


def test_ensure_sync_skips_when_notices_unchanged(db):
    make_eclass([("74261", "2026-10-10 09:00", "중간고사 안내", MIDTERM)])
    assert service.ensure_sync(db, TODAY, get_courses=courses)["new"] == 1
    assert service.ensure_sync(db, TODAY, get_courses=courses) is None      # 도장이 같으면 읽지 않는다


def test_preview_matches_what_registering_will_do(db):
    """등록된 계획이 있으면 미리보기도 완료분을 뺀다 — 본 표와 등록 결과가 같아야 한다."""
    e = add_exam(db)
    pid = plan_for(db, e["id"])["plan"]["planId"]
    service.patch_day(db, pid, TODAY.isoformat(), {"done": True}, TODAY, courses)

    shown = service.preview(db, e["id"], {"totalPages": 120}, TODAY, courses)
    assert shown["carried"]["pages"] == 15
    assert shown["totals"]["pages"] == 120

    registered = service.create_plan(db, e["id"], {"totalPages": 120}, TODAY, courses)["plan"]
    assert [(d["date"], d["pages"]) for d in registered["days"]] == [
        (d["date"], d["pages"]) for d in shown["days"] if d["kind"] != "excluded"
    ]



# ---------------------------------------------------------------- 2026-10-02 수정

def test_difficulty_settings_change_page_minutes(db):
    """난이도 시간 설정 — 기본 1·1.5·2분, 사용자가 바꾸면 그 값으로 계산한다."""
    assert [d["pageMinutes"] for d in service.difficulty_view(db)] == [1.0, 1.5, 2.0]
    e = add_exam(db)
    assert service.preview(db, e["id"], {"totalPages": 90}, TODAY, courses)["pageMinutes"] == 1.5
    service.set_difficulty_minutes(db, {"normal": 2.5, "hard": 5})
    assert service.preview(db, e["id"], {"totalPages": 90}, TODAY, courses)["pageMinutes"] == 2.5
    assert service.preview(db, e["id"], {"totalPages": 90, "difficulty": "hard"}, TODAY, courses)["pageMinutes"] == 5
    service.set_difficulty_minutes(db, {"normal": None})                       # 기본값으로
    assert [d["pageMinutes"] for d in service.difficulty_view(db)] == [1.0, 1.5, 5.0]


@pytest.mark.parametrize("body", [{}, {"medium": 2}, {"easy": "빨리"}, {"hard": 0}, {"hard": 99}])
def test_difficulty_settings_validation(db, body):
    with pytest.raises(service.Invalid):
        service.set_difficulty_minutes(db, body)


def test_uncheck_reopens_plan_closed_by_completion(db):
    """블록이 하나뿐인 계획을 체크하면 '다 끝남'으로 닫힌다 — 체크를 풀면 다시 열려야 한다(실제로 안 풀리던 것)."""
    e = add_exam(db)
    pid = plan_for(db, e["id"], totalPages=30, studyDates=["2026-10-20"], reviewDays=0)["plan"]["planId"]
    out = service.patch_day(db, pid, "2026-10-20", {"done": True}, TODAY, courses)
    assert out["plan"]["state"] == "done"
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)
    assert [b["editable"] for d in cal["days"] for b in d["blocks"]] == [True]     # 끝난 계획도 체크를 풀 수 있다
    out = service.patch_day(db, pid, "2026-10-20", {"done": False}, TODAY, courses)
    assert out["plan"]["state"] == "active" and out["day"]["done"] is False


def test_past_exam_plan_is_not_reopened(db):
    e = add_exam(db, when="2026-10-16")
    pid = plan_for(db, e["id"], totalPages=10)["plan"]["planId"]
    service.patch_day(db, pid, "2026-10-13", {"done": True}, TODAY, courses)
    later = date(2026, 10, 20)
    service.close_past(db, later)
    out = service.patch_day(db, pid, "2026-10-13", {"done": False}, later, courses)
    assert out["plan"]["state"] == "done"                                        # 시험이 지난 계획은 닫힌 채로


def test_delete_block_even_when_done_and_last_removes_plan(db):
    e = add_exam(db)
    pid = plan_for(db, e["id"], totalPages=30, studyDates=["2026-10-19", "2026-10-20"], reviewDays=0)["plan"]["planId"]
    service.patch_day(db, pid, "2026-10-19", {"done": True}, TODAY, courses)
    out = service.delete_day(db, pid, "2026-10-19")                            # 완료한 블록도 지운다
    assert out["planRemoved"] is False and out["blocksLeft"] == 1
    out = service.delete_day(db, pid, "2026-10-20")
    assert out["planRemoved"] is True and store.plan(db, pid) is None
    cal = service.study_calendar(db, "2026-10-01", "2026-10-31", courses, TODAY)
    assert [b for d in cal["days"] for b in d["blocks"]] == []                 # 시험 날짜는 남고 공부 블록은 없다
    with pytest.raises(service.NotFound):
        service.delete_day(db, pid, "2026-10-20")


def test_new_plan_defaults_follow_difficulty_settings(db):
    """계획 만들기 화면의 기본 옵션도 '난이도 시간 설정' 값을 따른다(고정 2분을 실어 보내면 설정이 안 먹는다)."""
    e = add_exam(db)
    service.set_difficulty_minutes(db, {"normal": 2.5})
    opts = service.default_options(db, store.exam(db, e["id"]), TODAY)
    assert opts["pageMinutes"] is None and opts["reviewDays"] == 1
    assert opts["studyDays"] == 3                                   # 학습일 기본 3일 (2026-10-02)
    out = service.preview(db, e["id"], {**opts, "totalPages": 90}, TODAY, courses)
    assert out["pageMinutes"] == 2.5
    assert out["studyDays"] == 3 and out["studyDates"] == ["2026-10-19", "2026-10-20", "2026-10-21"]


def test_difficulty_same_as_default_is_not_stored(db):
    """기본값과 같은 값은 저장하지 않는다 — 기본값이 바뀌면 따라간다 (2026-10-02)."""
    service.set_difficulty_minutes(db, {"easy": 1.0, "normal": 2.5, "hard": 2.0})
    assert store.jload(store.get_meta(db, "difficulty_minutes"), {}) == {"normal": 2.5}
