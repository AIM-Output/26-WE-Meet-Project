"""등록(병합·변경·삭제·사용자 값 보존) → 읽기 모델(상태·내 해당·캘린더) → 알림(배달·놓침·중복 없음)."""
from datetime import date, datetime, timedelta

from bachelor import notify, service
from bachelor.audience import applies_to_me
from bachelor.models import Audience, Candidate
from bachelor.register import register

P3 = {"grade": 3, "enrollment": "재학", "college": "AI융합대학", "department": "인공지능학부"}


def cand(title, start, end=None, *, type_="tuition", conf=0.95, aud=None, post=None, st=None, et=None):
    return Candidate(title=title, start=start, end=end, start_time=st, end_time=et, type=type_,
                     audience=aud or Audience(), evidence=[{"field": "start", "quote": f"{title} {start}"}],
                     confidence=conf, semester="2026-2", url="https://x", post_id=post)


def one(con, title, profile=P3):
    return next(e for e in service.list_events(con, profile) if e["title"] == title)


def test_register_merge_change_remove(db):
    d = date(2026, 10, 1)
    st = register(db, "jnu_calendar", [cand("제2학기 최종 등록", d, date(2026, 10, 2)),
                                       cand("제2학기 개강", date(2026, 9, 1), type_="vacation")],
                  snapshot_since=date(2026, 1, 1))
    assert st["new"] == 2
    # 공지에서 같은 일정(정규화 제목 + 시작일) → 같은 events 에 붙는다
    register(db, "jnu_notice", [cand("2026학년도 제2학기 최종 등록 공고", d, date(2026, 10, 2), conf=0.8, post="70363",
                                     st="09:00", et="16:00")], post_id="70363")
    e = one(db, "제2학기 최종 등록")
    assert [s["key"] for s in e["sources"]] == ["jnu_calendar", "jnu_notice"]        # 표가 대표
    assert e["start"] == "2026-10-01T09:00" and e["end"] == "2026-10-02T16:00"        # 시각은 공지에서 빌려 온다
    assert e["status"] == "auto" and e["onCalendar"] and e["appliesToMe"] is True

    # 사용자가 숨긴 뒤 재수집 — 숨김 유지 (F1-R24)
    service.update_event(db, e["id"], {"status": "hidden", "memo": "메모"})
    # 날짜가 바뀐 재수집 → 변경됨 + 알림 1건 (F1-R23)
    st = register(db, "jnu_calendar", [cand("제2학기 최종 등록", date(2026, 10, 5), date(2026, 10, 6))],
                  snapshot_since=date(2026, 1, 1))
    assert st["changed"] == 1 and st["removed"] == 1                                  # 개강 행이 표에서 사라짐
    e = one(db, "제2학기 최종 등록")
    assert e["status"] == "hidden" and e["memo"] == "메모"
    assert e["changed"]["before"]["start"] == "2026-10-01"
    n = db.execute("SELECT * FROM notifications WHERE kind = 'change'").fetchall()
    assert len(n) == 1 and "10/1 ~ 10/2 → 10/5 ~ 10/6" in n[0]["body"]
    assert one(db, "제2학기 개강")["removed"] is True                                 # 지우지 않고 '원문 삭제됨'


def test_review_approve_with_edited_dates(db):
    register(db, "jnu_notice", [cand("복수전공 신청", date(2026, 11, 9), conf=0.62, post="1")], post_id="1")
    e = one(db, "복수전공 신청")
    assert e["status"] == "review" and not e["onCalendar"]
    service.update_event(db, e["id"], {"status": "approved", "dates": {
        "start_date": "2026-11-10", "start_time": "09:00", "end_date": "2026-11-13", "end_time": "18:00"}})
    e = one(db, "복수전공 신청")
    assert e["status"] == "approved" and e["onCalendar"] and e["start"] == "2026-11-10T09:00" and e["userEdited"]
    # 원문을 다시 읽어 항목이 사라져도 사용자가 손댄 일정은 남는다
    register(db, "jnu_notice", [], post_id="1")
    assert one(db, "복수전공 신청")["removed"] is True


def test_reextract_drops_untouched_stale_items(db):
    register(db, "jnu_notice", [cand("우리 대학교에서는", date(2026, 8, 18), conf=0.7, post="9")], post_id="9")
    register(db, "jnu_notice", [cand("제2학기 추가 등록", date(2026, 9, 9), post="9")], post_id="9")
    titles = [e["title"] for e in service.list_events(db, P3)]
    assert titles == ["제2학기 추가 등록"]


def test_new_since_last_run(db):
    from bachelor import store
    register(db, "jnu_calendar", [cand("제2학기 개강", date(2026, 9, 1), type_="vacation")])
    db.execute("UPDATE events SET first_seen = '2000-01-01T00:00:00'")
    assert one(db, "제2학기 개강")["isNew"] is False              # 수집 기록이 없으면 신규 없음
    store.set_meta(db, "last_run_started", "2000-01-02T00:00:00")  # 이번 수집 시작 — 아래 등록은 이 뒤
    register(db, "jnu_notice", [cand("복수전공 신청", date(2026, 11, 9), post="3"),
                                cand("부전공 신청", date(2026, 11, 10), conf=0.6, post="3")], post_id="3")
    assert one(db, "제2학기 개강")["isNew"] is False
    assert one(db, "복수전공 신청")["isNew"] is True and one(db, "부전공 신청")["isNew"] is True
    # 대시보드 '신규 일정' 은 바로 등록된 것만 — 확인 필요는 reviewCount 에서 센다
    new_auto = [e["title"] for e in service.list_events(db, P3) if e["isNew"] and e["status"] in ("auto", "approved")]
    assert new_auto == ["복수전공 신청"]
    # 대시보드 '신규 일정'·'확인 필요' 는 지난 일정을 세지 않는다 (/academic 과 같은 기준)
    items = service.list_events(db, P3)
    assert service.review_count(items, date(2026, 11, 10)) == 1 and service.review_count(items, date(2026, 11, 11)) == 0
    last_day = service.last_day
    assert last_day({"start": "2026-10-01", "end": "2026-10-03", "allDay": True}) == date(2026, 10, 2)
    assert last_day({"start": "2026-10-01T09:00", "end": "2026-10-02T00:00", "allDay": False}) == date(2026, 10, 1)


def test_applies_to_me():
    assert applies_to_me(Audience(), None) is True
    assert applies_to_me(Audience(grades=[1]), None) is None
    assert applies_to_me(Audience(grades=[1]), P3) is False
    assert applies_to_me(Audience(grades=[3]), P3) is True
    assert applies_to_me(Audience(colleges=["공과대학"]), P3) is False
    assert applies_to_me(Audience(colleges=["AI융합대학"]), P3) is True
    assert applies_to_me(Audience(roles=["faculty"]), None) is False
    assert applies_to_me(Audience(roles=["graduate"]), P3) is False
    assert applies_to_me(Audience(enrollment=["휴학"]), P3) is False
    assert applies_to_me(Audience(departments=["인공지능학부"]), {"grade": 2}) is None


def test_calendar_only_mine(db):
    register(db, "jnu_calendar", [
        cand("제2학기 수강신청 (3학년)", date(2026, 8, 10), type_="course_reg", aud=Audience(grades=[3])),
        cand("제2학기 수강신청 (1학년)", date(2026, 8, 12), type_="course_reg", aud=Audience(grades=[1])),
        cand("제2학기 성적제출 마감", date(2027, 1, 4), type_="grade", aud=Audience(roles=["faculty"]))])
    ids = {e["title"] for e in service.calendar_events(db, P3)}
    assert ids == {"제2학기 수강신청 (3학년)"}
    assert service.calendar_events(db, None) == []                   # 프로필 없음 → 조건 있는 일정은 판단 불가
    # 해당 없음이어도 '내 캘린더에 담기' (F1-R25)
    e = one(db, "제2학기 수강신청 (1학년)")
    service.update_event(db, e["id"], {"pinned": True})
    assert {e["title"] for e in service.calendar_events(db, P3)} == {"제2학기 수강신청 (3학년)", "제2학기 수강신청 (1학년)"}


def test_long_period_becomes_two_markers(db):
    register(db, "jnu_notice", [cand("일반휴학 (등록)", date(2026, 8, 18), date(2026, 10, 28), type_="registration", post="7"),
                                cand("등록금 납부", date(2026, 8, 24), date(2026, 8, 28), post="7")], post_id="7")
    cal = {e["id"].split("#")[-1] if "#" in e["id"] else "bar": e for e in service.calendar_events(db, P3)}
    assert cal["start"]["title"] == "일반휴학 (등록) 시작" and cal["start"]["start"] == "2026-08-18"
    assert cal["end"]["title"] == "일반휴학 (등록) 마감" and cal["end"]["start"] == "2026-10-28"
    assert cal["end"]["extendedProps"]["refId"] == cal["start"]["extendedProps"]["refId"]
    assert cal["bar"]["title"] == "등록금 납부" and cal["bar"]["end"] == "2026-08-29"      # 짧은 기간은 막대 그대로


def test_notifications(db):
    s = date(2026, 10, 10)
    register(db, "jnu_calendar", [cand("등록금 납부", s, s + timedelta(days=2))])
    db.execute("UPDATE events SET first_seen = '2000-01-01T00:00:00'")
    now = datetime(2026, 10, 9, 9, 30)                                # D-1 09:00 에서 30분 뒤
    assert notify.deliver_due(db, P3, now) == 3                       # D-7 · D-3 · D-1
    rows = {r["title"][:3]: r for r in db.execute("SELECT * FROM notifications")}
    assert rows["D-7"]["missed"] == 1 and rows["D-3"]["missed"] == 1 and rows["D-1"]["missed"] == 0
    assert notify.deliver_due(db, P3, now) == 0                       # 다시 불러도 중복 없음
    later = datetime(2026, 10, 11, 9, 0)
    assert notify.deliver_due(db, P3, later) == 1                     # 종료 전날 '내일 마감'
    assert any(r["title"].startswith("내일 마감") for r in db.execute("SELECT title FROM notifications"))

    res = notify.list_notifications(db, P3)
    assert res["unread"] == 4
    notify.mark_read(db, res["items"][0]["id"])
    assert notify.list_notifications(db, P3)["unread"] == 3
    assert notify.mark_all_read(db) == 3


def test_notifications_not_before_first_seen(db):
    s = date(2026, 10, 10)
    register(db, "jnu_calendar", [cand("수강 정정", s, type_="course_reg", st="10:00")])
    db.execute("UPDATE events SET first_seen = '2026-10-08T12:00:00'")   # D-2 에 처음 봄
    assert notify.deliver_due(db, P3, datetime(2026, 10, 10, 9, 45)) == 2   # D-1 + 30분 전 (D-7·D-3 은 만들지 않음)
    titles = sorted(r["title"] for r in db.execute("SELECT title FROM notifications"))
    assert titles == ["30분 후 시작 · 수강 정정", "D-1 · 수강 정정"]


def test_reminder_toggle_and_type_defaults(db):
    register(db, "jnu_calendar", [cand("추석연휴 (휴업)", date(2026, 9, 24), type_="holiday"),
                                  cand("중간고사", date(2026, 10, 19), date(2026, 10, 23), type_="exam")])
    hol, exam = one(db, "추석연휴 (휴업)"), one(db, "중간고사")
    assert [r["code"] for r in hol["reminders"] if r["enabled"]] == []
    assert [r["code"] for r in exam["reminders"] if r["enabled"]] == ["d7", "d1"]
    service.update_event(db, exam["id"], {"reminders": {"d3": True, "d7": False}})
    assert [r["code"] for r in one(db, "중간고사")["reminders"] if r["enabled"]] == ["d3", "d1"]
