"""서비스 — 목록 정렬·접기, 판정 뒤집기·진행 상태(두 축 분리), 예전 초안 데이터 지우기, 캘린더·할 일, 이력, 알림."""
from datetime import datetime

import pytest
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
        assert service.detail(con, "www:2", profile, TODAY)["progressLabel"] == "신청 예정"
        service.patch(con, "www:2", {"verdict": None})                   # 되돌리기 — 진행 상태는 유지
        d = service.detail(con, "www:2", profile, TODAY)
        assert d["verdict"] == "ineligible" and d["progress"] == "approved"
        service.patch(con, "www:1", {"progress": "skipped"})              # 관심 없음 → 목록에서 빠지고 이력에
        ids = [i["id"] for i in service.overview(con, profile, TODAY)["items"]]
        assert "www:1" not in ids
        assert service.history(con)["semesters"][0]["items"]


def test_old_draft_data_removed_on_upgrade(profile):
    """2026-11-19 신청서 초안 폐기 — 예전 DB 의 초안 표·초안 재료(이름·학번·연락처)를 앱을 새 판으로 처음 열 때 지우고,
    '초안 대기'는 '신청 예정'으로 옮긴다(마감 D-3·D-1 알림을 이어서 받는다). 지운 자리는 0 으로 덮여 파일에 남지 않는다."""
    from scholarship import config as C
    with store.connect() as con:
        seed(con)
        con.execute("CREATE TABLE drafts (notice_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        con.execute("INSERT INTO drafts VALUES ('www:1', '# [신청서 초안] 학번 2099000001')")
        store.set_meta(con, "materials", '{"basic": {"name": "테스트학생", "studentId": "2099000002"}}')
        store.put_state(con, "www:1", progress="draft")
    store._initialized.clear()                                   # 앱을 새 판으로 다시 띄운 것처럼
    with store.connect() as con:
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name = 'drafts'").fetchone() is None
        assert store.get_meta(con, "materials") is None
        assert not store.drop_drafts(con)                        # 두 번째부터는 지울 것이 없다
        d = service.detail(con, "www:1", profile, TODAY)
    assert d["progress"] == "approved" and d["progressLabel"] == "신청 예정"
    assert not {"draft", "hasDraft", "draftStale", "otherDrafts"} & set(d)
    raw = C.DB_PATH.read_bytes()
    assert b"2099000001" not in raw and b"2099000002" not in raw


def test_progress_draft_is_gone(profile):
    with store.connect() as con:
        seed(con)
        with pytest.raises(service.Invalid):
            service.patch(con, "www:1", {"progress": "draft"})
        assert "llm" not in service.overview(con, profile, TODAY)


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


def test_lock_does_not_steal_lock_being_created(monkeypatch):
    """다른 실행이 막 잠금 파일을 만든(아직 비어 있는) 순간에 덮어써 둘 다 수집하지 않는다 (O_EXCL)."""
    from scholarship import collect, config as C
    C.STATE_DIR.mkdir(parents=True, exist_ok=True)
    C.LOCK_FILE.write_text("", encoding="utf-8")               # 상대가 O_EXCL 로 만들고 아직 pid 를 쓰기 전
    peer = '{"pid": 424242, "started_at": "x"}'
    monkeypatch.setattr(collect.time, "sleep", lambda s: C.LOCK_FILE.write_text(peer, encoding="utf-8"))
    monkeypatch.setattr(C, "pid_alive", lambda pid: pid == 424242)
    try:
        assert collect._lock() is False
        assert C.LOCK_FILE.read_text(encoding="utf-8") == peer
    finally:
        C.LOCK_FILE.unlink(missing_ok=True)
