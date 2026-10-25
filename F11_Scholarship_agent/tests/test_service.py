"""서비스 — 목록 정렬·접기, 판정 뒤집기·진행 상태(두 축 분리), 초안, 캘린더·할 일, 이력, 알림."""
from datetime import datetime

from conftest import TODAY, add_notice

from scholarship import notify, service, store

FULL = ("1. 지원자격: 본교 2학년 이상 재학생\n2. 성적기준: 직전학기 평점 3.0/4.5 이상, 직전학기 12학점 이상 이수\n"
        "3. 신청기간: 2026. 10. 1.(수) ~ 2026. 10. 20.(월) 18:00\n4. 제출서류: 장학금 신청서 1부, 재학증명서 1부\n"
        "5. 신청방법: 이메일 접수 (scholar@example.invalid)\n")


def seed(con):
    add_notice(con, "www:1", "[장학안내] [(재)좋은장학재단] 장학생 선발", FULL)                       # 해당
    add_notice(con, "www:2", "[장학안내] [(재)포항시장학회] 장학생 선발", FULL + "본인 또는 부모가 포항시에 주소를 둔 자\n")  # 비해당
    add_notice(con, "www:3", "[장학안내] 2026 장학생 모집", "")                                       # 확인 필요(조건 못 읽음)
    add_notice(con, "www:4", "[장학안내] 지난 장학 선발", FULL.replace("10. 20.(월)", "9. 1.(화)"))    # 마감


def test_overview_order_and_counts(profile):
    with store.connect() as con:
        seed(con)
        ov = service.overview(con, profile, TODAY)
    verdicts = [i["verdict"] for i in ov["items"]]
    assert verdicts == ["eligible", "needs_review", "ineligible", "expired"]
    assert ov["counts"]["eligible"] == 1 and ov["counts"]["review"] == 1


def test_flip_and_progress_are_separate(profile):
    with store.connect() as con:
        seed(con)
        service.patch(con, "www:2", {"verdict": "eligible", "reason": "부모님 주소가 포항"})
        d = service.detail(con, "www:2", profile, TODAY)
        assert d["verdict"] == "eligible" and d["flipped"] and d["systemVerdict"] == "ineligible"
        assert any(r["status"] == "fail" for r in d["reasons"])          # 근거 목록은 그대로
        service.patch(con, "www:2", {"progress": "approved"})
        assert service.detail(con, "www:2", profile, TODAY)["progressLabel"] == "승인·제출 예정"
        service.patch(con, "www:2", {"verdict": None})                   # 되돌리기 — 진행 상태는 유지
        d = service.detail(con, "www:2", profile, TODAY)
        assert d["verdict"] == "ineligible" and d["progress"] == "approved"
        service.patch(con, "www:1", {"progress": "skipped"})              # 관심 없음 → 목록에서 빠지고 이력에
        ids = [i["id"] for i in service.overview(con, profile, TODAY)["items"]]
        assert "www:1" not in ids
        assert service.history(con)["semesters"][0]["items"]


def test_draft_needs_no_invention(profile):
    with store.connect() as con:
        seed(con)
        service.put_materials(con, {"careerGoal": "임베디드 AI 분야 대학원 진학", "activities": "", "hardship": "", "highlights": ""})
        d = service.make_draft(con, "www:1", profile)
    body = d["draft"]["body"]
    assert "{{이름}}" in body and "{{학번}}" in body
    assert "임베디드 AI 분야 대학원 진학" in body
    assert "{{이 목표를 위해 해 온 구체적인 활동 경험을 적어 주세요}}" in body     # 활동 재료가 없으면 빈칸
    assert "- [ ] 장학금 신청서 1부" in body
    assert "제출은 시스템이 하지 않습니다" in body
    assert d["progress"] == "draft" and d["draft"]["generatedBy"] == "template"


def test_borrow_marks_source(profile):
    with store.connect() as con:
        seed(con)
        service.put_materials(con, {"careerGoal": "보안 연구", "activities": "학과 튜터링", "hardship": "", "highlights": ""})
        service.make_draft(con, "www:1", profile)
        d = service.make_draft(con, "www:3", profile, borrow_from="www:1")
    assert d["draft"]["borrowed"][0]["from"] == "www:1"
    assert "초안에서 가져옴" in d["draft"]["body"] and "학과 튜터링" in d["draft"]["body"]


def test_draft_stale_when_notice_changes(profile):
    with store.connect() as con:
        seed(con)
        service.put_materials(con, {})
        service.make_draft(con, "www:1", profile)
        add_notice(con, "www:1", "[장학안내] [(재)좋은장학재단] 장학생 선발", FULL + "\n(수정) 마감 연장")
        assert service.detail(con, "www:1", profile, TODAY)["draftStale"]


def test_calendar_and_todo_callbacks(profile):
    made = []

    def add_event(ev):
        made.append(ev)
        return {"id": str(len(made)), **ev}

    with store.connect() as con:
        seed(con)
        service.add_calendar(con, "www:1", profile, add_event)
        service.add_todo(con, "www:1", 1, profile, add_event, today=TODAY)
        d = service.detail(con, "www:1", profile, TODAY)
    assert made[0]["start"].startswith("2026-10-20T18:00") and made[0]["origin"] == "sch:www:1"
    assert made[1]["is_todo"] and made[1]["start"] == "2026-10-19" and "재학증명서" in made[1]["title"]
    assert d["onCalendar"] and d["state"]["todos"] == {"1": "2"}


def test_notify_baseline_new_and_deadline(profile):
    pushed = []

    def push(nid, ref, title, body, href):
        pushed.append((nid, title, href))

    with store.connect() as con:
        seed(con)
        assert notify.deliver(con, profile, push, datetime(2026, 10, 9, 10)) == 0     # 기준선 전 — 알리지 않는다
        store.set_meta(con, "baseline_at", "2026-01-01T00:00:00")
        notify.deliver(con, profile, push, datetime(2026, 10, 9, 10))
        titles = [t for _, t, _ in pushed]
        assert any("[해당]" in t for t in titles) and any("[확인 필요]" in t for t in titles)
        assert not any("포항" in t for t in titles)                                  # 비해당은 알리지 않는다
        n = len(pushed)
        notify.deliver(con, profile, push, datetime(2026, 10, 9, 10))
        assert len(pushed) == n                                                         # 같은 공지 두 번 X
        service.patch(con, "www:1", {"progress": "approved"})
        notify.deliver(con, profile, push, datetime(2026, 10, 17, 9, 30))               # 10-20 마감 → D-3
        assert any("D-3" in t for _, t, _ in pushed[n:])
        assert pushed[-1][2].startswith("/scholarships?item=")


def test_sources_rows_and_toggle(profile):
    with store.connect() as con:
        rows = {r["key"]: r for r in service.source_rows(con, profile)}
        assert rows["my_dept"]["target"]["homepage"].startswith("https://aisw.jnu.ac.kr")
        service.set_source(con, "greenbio", True)
        rows = {r["key"]: r for r in service.source_rows(con, profile)}
        assert rows["greenbio"]["enabled"] and rows["greenbio"]["userSet"]
        service.set_source(con, "greenbio", None)
        assert not {r["key"]: r for r in service.source_rows(con, profile)}["greenbio"]["enabled"]


def test_status_and_brief(profile):
    with store.connect() as con:
        seed(con)
        st = service.status_summary(con, profile, TODAY)
        assert st["eligible"] == 1 and st["review"] == 1
        assert service.brief(con, profile, days=30, today=TODAY)
