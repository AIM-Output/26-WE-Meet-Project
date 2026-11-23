"""서비스 — 목록 묶음·정렬, 관심사 없을 때, 담기 → 캘린더, 등급 뒤집기·진행 상태(두 축 분리), 예전 초안 데이터 지우기, 이력, 타일·브리핑."""
import pytest
from conftest import TODAY, add_notice

from activity import service, store

OPEN = "신청기간 : 2026. 10. 1. ~ 2026. 10. 20.(화) 18:00\n제출서류 : 참가신청서 1부, 재학증명서 1부\n신청방법 : 이메일 접수"


def seed(con):
    add_notice(con, "www:1", "[공모전] 2026 AI 아이디어 경진대회 참가팀 모집", OPEN)                       # 내 관심사 (태그 제목)
    add_notice(con, "www:2", "[모집공고] 청년 정책 포럼 참가자 모집", "주제: 데이터와 청년\n" + OPEN)      # 관련 있음 (태그 본문)
    add_notice(con, "www:3", "[대학생활] 교내 합창단 단원 모집", OPEN)                                    # 관심 밖
    add_notice(con, "www:4", "[공모전] 지난 AI 경진대회", OPEN.replace("10. 20.(화)", "10. 2.(목)"))      # 마감
    add_notice(con, "www:5", "2026 AIM챌린지 본선 진출팀 발표", "")                                       # 결과 발표


def test_groups_and_counts(profile):
    with store.connect() as con:
        seed(con)
        ov = service.overview(con, profile, TODAY)
    order = [(i["id"], i["grade"], i["status"]) for i in ov["items"]]
    assert order[:3] == [("www:1", "match", "open"), ("www:2", "related", "open"), ("www:3", "other", "open")]
    assert {i["id"]: i["status"] for i in ov["items"]}["www:4"] == "expired"
    assert {i["id"]: i["status"] for i in ov["items"]}["www:5"] == "result"
    c = ov["counts"]
    assert (c["match"], c["related"], c["other"], c["open"], c["closed"]) == (1, 1, 1, 3, 2)
    assert ov["interests"]["set"] and ov["items"][0]["chips"] == ["AI·SW", "공모전·경진대회"]
    assert ov["items"][0]["categoryLabel"] == "공모전·경진대회"


def test_no_interests_lists_everything_ungraded(profile):
    profile["interests"] = None
    with store.connect() as con:
        seed(con)
        ov = service.overview(con, profile, TODAY)
    assert not ov["interests"]["set"]
    assert all(i["grade"] is None for i in ov["items"])
    assert [i["status"] for i in ov["items"]][:3] == ["open"] * 3


def test_dedupe_by_title_key(profile):
    with store.connect() as con:
        add_notice(con, "www:10", "[모집공고] 2026 SW 해커톤 참가자 모집", OPEN)
        from activity.collect import build_info
        from activity.extract import title_key
        from scholarship.textutil import content_hash
        row = {"id": "aisw:99", "source": "sojoong", "source_name": "SW중심대학", "unit_key": None,
               "title": "2026 SW 해커톤 참가자 모집", "url": "https://x.invalid", "posted_at": "2026-10-06", "writer": None,
               "category": None, "body": OPEN, "attach_text": "", "attachments": [], "image_only": False,
               "content_hash": content_hash("a"), "title_key": title_key("2026 SW 해커톤 참가자 모집")}
        row["dup_of"] = store.find_dup(con, row["title_key"], row["id"])
        row["info"] = build_info(row, None)
        row["extract_ver"] = 1
        store.upsert_notice(con, row)
        ids = [i["id"] for i in service.evaluate(con, profile, TODAY)]
        assert ids.count("www:10") == 1 and "aisw:99" not in ids
        assert service.detail(con, "www:10", profile, TODAY)["alsoPostedAt"][0]["id"] == "aisw:99"


def test_regroup_splits_titles_that_differ_in_brackets(profile):
    """2026-11-19 — 예전 제목 키(괄호 안을 다 지움)로 묶인 다른 글을 한 번 다시 묶는다. 같은 글은 계속 묶이고,
    담아 둔 글은 숨지 않으며, 묶음에서 풀린 글은 '새 관심 기회' 알림으로 쏟아지지 않게 알린 것으로 친다."""
    from activity import config as C
    titles = {"www:21": "[학사안내]2026학년도 동계 계절학기 타 대학교(충북대) 교류수학 추천 안내",
              "www:22": "[학사안내]2026학년도 동계 계절학기 타 대학교(서울대) 교류수학 추천 안내",
              "www:23": "[취업정보][현대그린푸드]2026 신입사원채용(~10.25.(일)까지)",
              "www:24": "[취업정보][iM증권]2026 신입사원 채용(~11.8.(일)까지)",
              "www:25": "[공모전]2026 AI 활용 영상 콘텐츠 경진대회 참가자 모집(~11/13까지)",
              "ile:25": "2026 AI 활용 영상 콘텐츠 경진대회 참가자 모집(~11/13까지)"}
    with store.connect() as con:
        for i, (nid, t) in enumerate(titles.items()):
            add_notice(con, nid, t, OPEN, source="ile" if nid.startswith("ile") else "jnu_notice")
            con.execute("UPDATE notices SET first_seen = ?, title_key = 'old' WHERE id = ?", (f"2026-10-0{i + 1}T09:00:00", nid))
        # 예전 판의 묶음 — 서로 다른 대학·회사가 하나로 접혀 있었다. www:24 는 사용자가 담아 둔 글
        con.execute("UPDATE notices SET dup_of = 'www:21' WHERE id = 'www:22'")
        con.execute("UPDATE notices SET dup_of = 'www:23' WHERE id = 'www:24'")
        con.execute("UPDATE notices SET dup_of = 'www:25' WHERE id = 'ile:25'")
        store.put_state(con, "www:24", progress="saved")
        store.set_meta(con, "title_key_ver", "1")
    store._initialized.clear()                                   # 앱을 새 판으로 다시 띄운 것처럼
    with store.connect() as con:
        dups = {r["id"]: r["dup_of"] for r in con.execute("SELECT id, dup_of FROM notices")}
        alerted = {r["notice_id"] for r in con.execute("SELECT notice_id FROM user_state WHERE alerted_at IS NOT NULL")}
        assert store.get_meta(con, "title_key_ver") == str(C.TITLE_KEY_VERSION)
        ids = [i["id"] for i in service.evaluate(con, profile, TODAY)]
    assert dups == {"www:21": None, "www:22": None, "www:23": None, "www:24": None, "www:25": None, "ile:25": "www:25"}
    assert {"www:22", "www:24"} <= set(ids) and "ile:25" not in ids
    assert alerted == {"www:22", "www:24"}


def test_save_adds_deadline_to_calendar_and_unsave_removes(profile, cal):
    with store.connect() as con:
        seed(con)
        service.patch(con, "www:1", {"saved": True}, profile, add_event=cal.add, remove_event=cal.remove)
        d = service.detail(con, "www:1", profile, TODAY)
        assert d["saved"] and d["progress"] == "saved" and d["onCalendar"]
        ev = next(iter(cal.events.values()))
        assert ev["origin"] == "act:www:1" and ev["start"] == "2026-10-20T18:00:00" and "[신청 마감]" in ev["title"]
        service.patch(con, "www:1", {"saved": False}, profile, add_event=cal.add, remove_event=cal.remove)
        d = service.detail(con, "www:1", profile, TODAY)
        assert not d["saved"] and not d["onCalendar"] and cal.removed == [ev["id"]]
        # 마감을 못 읽은 공지는 담기만 된다 (F12 8절)
        add_notice(con, "www:9", "[모집공고] AI 스터디 모집", "상시 모집합니다")
        service.patch(con, "www:9", {"saved": True}, profile, add_event=cal.add)
        assert service.detail(con, "www:9", profile, TODAY)["saved"] and len(cal.events) == 0


def test_flip_grade_and_skip_are_separate(profile):
    with store.connect() as con:
        seed(con)
        service.patch(con, "www:3", {"grade": "match"})
        d = service.detail(con, "www:3", profile, TODAY)
        assert d["grade"] == "match" and d["flipped"] and d["systemGrade"] == "other"
        assert d["reasons"][0].startswith("내가 '내 관심사'")
        service.patch(con, "www:3", {"progress": "applied"})
        service.patch(con, "www:3", {"grade": None})                    # 되돌리기 — 진행 상태는 그대로
        d = service.detail(con, "www:3", profile, TODAY)
        assert d["grade"] == "other" and d["progressLabel"] == "지원함"
        service.patch(con, "www:2", {"progress": "skipped"})            # 관심 없음 → 목록에서 빠지고 이력에
        assert "www:2" not in [i["id"] for i in service.evaluate(con, profile, TODAY)]
        h = service.history(con)["semesters"][0]
        assert h["applied"] == 1 and {i["progress"] for i in h["items"]} == {"applied", "skipped"}


def test_old_draft_data_removed_on_upgrade(profile, cal):
    """2026-11-19 신청서 초안 폐기 — 예전 DB 의 초안 표·초안 재료를 지우고, '초안 대기'·'제출 예정'은 '담음'으로 옮긴다.
    담아 둔 글의 마감이 지나면 '지원하셨나요?'를 묻는다(예전엔 제출 예정만)."""
    from activity import config as C
    with store.connect() as con:
        seed(con)
        con.execute("CREATE TABLE drafts (notice_id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        con.execute("INSERT INTO drafts VALUES ('www:1', '# [신청서 초안] 학번 2099000003')")
        store.set_meta(con, "materials", '{"basic": {"name": "테스트학생", "phone": "010-0000-0004"}}')
        store.put_state(con, "www:1", progress="draft", progress_at="2026-10-05T10:00:00")
        store.put_state(con, "www:4", progress="approved", progress_at="2026-10-01T10:00:00")
    store._initialized.clear()                                   # 앱을 새 판으로 다시 띄운 것처럼
    with store.connect() as con:
        assert con.execute("SELECT 1 FROM sqlite_master WHERE name = 'drafts'").fetchone() is None
        assert store.get_meta(con, "materials") is None
        d1, d4 = service.detail(con, "www:1", profile, TODAY), service.detail(con, "www:4", profile, TODAY)
    assert (d1["progress"], d1["saved"], d1["state"]["savedAt"]) == ("saved", True, "2026-10-05T10:00:00")
    assert not {"draft", "hasDraft", "draftStale", "otherDrafts"} & set(d1)
    assert d4["progress"] == "saved" and d4["askApplied"]               # www:4 는 10-02 마감 — 지원했는지 묻는다
    assert not d1["askApplied"]                                          # 아직 마감 전
    raw = C.DB_PATH.read_bytes()
    assert b"2099000003" not in raw and b"010-0000-0004" not in raw


def test_progress_draft_and_approved_are_gone(profile):
    with store.connect() as con:
        seed(con)
        for p in ("draft", "approved"):
            with pytest.raises(service.Invalid):
                service.patch(con, "www:1", {"progress": p})


def test_semester_rental_stays_open(profile):
    """이번 학기 대여 안내는 신청 기간을 못 읽어도 학기 내내 모집 중 — 다른 글은 45일이 지나면 지난 공지 (2026-11-19)."""
    with store.connect() as con:
        add_notice(con, "aicoss:2", "인공지능혁신융합대학사업단 실험실습 기자재 대여 안내(2026년 2학기)", "대여 품목 : 노트북",
                   source="aicoss", posted="2026-08-19")
        add_notice(con, "nccoss:1", "차세대통신 혁신융합대학사업단 2026학년도 1학기 교육·실습기자재 대여안내", "",
                   source="nccoss", posted="2026-03-05")
        add_notice(con, "www:60", "[모집공고] 2026 여름 AI 캠프 참가자 모집", "", posted="2026-08-19")
        st = {i["id"]: i["status"] for i in service.evaluate(con, profile, TODAY)}
    assert st == {"aicoss:2": "open", "nccoss:1": "stale", "www:60": "stale"}


def test_status_and_brief(profile, cal):
    with store.connect() as con:
        seed(con)
        add_notice(con, "www:6", "[모집공고] AI 캠프 참가자 모집", OPEN.replace("10. 20.(화)", "10. 12.(일)"))
        service.patch(con, "www:6", {"saved": True}, profile, add_event=cal.add)
        st = service.status_summary(con, profile, TODAY)
        assert st["interestsSet"] and st["match"] == 2 and st["saved"] == 1 and st["soon"] == 1
        assert st["next"]["id"] == "www:6"
        assert [b["id"] for b in service.brief(con, profile, today=TODAY)] == ["www:6"]


def test_academic_rows_hidden_even_if_stored(profile):
    with store.connect() as con:
        add_notice(con, "www:50", "2026학년도 2학기 학부 재학생 미등록자 고지서 출력", "등록금 납부 안내")
        add_notice(con, "www:51", "[모집공고] 2026 AI 해커톤 참가자 모집", OPEN)
        # 2026-11-19 — 작성 부서로는 빼지 않는다: 학사과 글이어도 대여는 보이고, 교무과 포상 공개검증은 말머리로 숨는다
        add_notice(con, "www:52", "[학사안내] 2026학년도 2학기 강의실 대관 신청 안내", OPEN, writer="학사과")
        add_notice(con, "www:53", "[직원표창공개]2027년도 2월말 퇴직교원 정부포상 및 장관표창 대상자 공개검증", "", writer="교무과")
        ids = [i["id"] for i in service.evaluate(con, profile, TODAY)]
    assert "www:50" not in ids and "www:51" in ids
    assert "www:52" in ids and "www:53" not in ids
