"""서비스 — 목록 묶음·정렬, 관심사 없을 때, 담기 → 캘린더, 등급 뒤집기·진행 상태(두 축 분리), 초안, 이력, 타일·브리핑."""
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
        from scholarship.textutil import content_hash, norm_title
        row = {"id": "aisw:99", "source": "sojoong", "source_name": "SW중심대학", "unit_key": None,
               "title": "2026 SW 해커톤 참가자 모집", "url": "https://x.invalid", "posted_at": "2026-10-06", "writer": None,
               "category": None, "body": OPEN, "attach_text": "", "attachments": [], "image_only": False,
               "content_hash": content_hash("a"), "title_key": norm_title("2026 SW 해커톤 참가자 모집")}
        row["dup_of"] = store.find_dup(con, row["title_key"], row["id"])
        row["info"] = build_info(row, None)
        row["extract_ver"] = 1
        store.upsert_notice(con, row)
        ids = [i["id"] for i in service.evaluate(con, profile, TODAY)]
        assert ids.count("www:10") == 1 and "aisw:99" not in ids
        assert service.detail(con, "www:10", profile, TODAY)["alsoPostedAt"][0]["id"] == "aisw:99"


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


def test_draft_template_no_invention(profile, cal):
    with store.connect() as con:
        seed(con)
        service.put_materials(con, {"careerGoal": "AI 엔지니어", "activities": "", "skills": "파이썬", "highlights": ""})
        d = service.make_draft(con, "www:1", profile, add_event=cal.add)
    body = d["draft"]["body"]
    assert "{{이름}}" in body and "{{학번}}" in body and "{{연락처}}" in body
    assert "## 3. 참가 동기" in body and "## 4. 아이디어·준비 계획" in body                 # 공모전 문단 제목
    assert "AI 엔지니어" in body and "파이썬을(를) 살려" in body
    assert "{{이 활동과 이어지는 내 경험을 적어 주세요}}" in body                            # 활동 재료가 없으면 빈칸
    assert "평소 AI·SW·공모전·경진대회에 관심을" in body                                    # 내가 고른 관심사만
    assert "- [ ] 재학증명서 1부" in body and "제출은 시스템이 하지 않습니다" in body
    assert d["progress"] == "draft" and d["draft"]["generatedBy"] == "template" and d["onCalendar"]


def test_basic_info_from_scholarship_and_in_draft(profile):
    """2026-10-25 — 초안 재료의 기본 정보(이름·학번·소속·학년·연락처 + 작성일). 비면 장학 재료의 기본 정보 → 프로필 소속·학년.
    LLM 프롬프트에는 이름·학번·연락처를 넣지 않는다."""
    from datetime import date
    from activity import draft as drafting
    sch = {"name": "테스트학생", "studentId": "2099000001", "department": "", "grade": "", "phone": "010-0000-0000", "email": ""}
    prompts = []

    def fake_llm(system, user):
        prompts.append(system + user)
        return "### 참가 동기\n저는 {{이름}}입니다.\n\n### 아이디어·준비 계획\n준비하겠습니다."
    with store.connect() as con:
        seed(con)
        m = service.materials(con, profile, lambda: None, lambda: sch)
        assert m["basic"]["name"] == "테스트학생" and m["basicFrom"] == "scholarship"
        assert m["basic"]["department"].endswith("인공지능학부") and m["basic"]["grade"] == "3"
        service.put_materials(con, {"careerGoal": "AI 엔지니어", "basic": {**sch, "email": "me@example.com"}})
        mats = service.materials(con, profile)
        d = service.detail(con, "www:1", profile, TODAY)
    body, by = drafting.build(d, profile, mats, llm=fake_llm, today=date(2026, 10, 25))
    assert by == "llm"
    for line in ("- 이름: 테스트학생", "- 학번: 2099000001", "- 연락처: 010-0000-0000", "- 이메일: me@example.com",
                 "- 작성일: 2026. 10. 25.", "3학년 · 재학"):
        assert line in body, line
    assert "저는 테스트학생입니다." in body and "{{이름}}" not in body
    assert prompts and all("테스트학생" not in p and "2099000001" not in p and "010-0000" not in p for p in prompts)


def test_rental_draft_headings(profile):
    with store.connect() as con:
        add_notice(con, "aicoss:1", "인공지능혁신융합대학사업단 실험실습 기자재 대여 안내(2026년 2학기)",
                   "대여 품목 : 노트북, 태블릿\n신청기간 : 2026. 10. 1. ~ 2026. 10. 30.", source="aicoss", unit_key="aicoss")
        service.put_materials(con, {"careerGoal": "", "activities": "", "skills": "", "highlights": ""})
        body = service.make_draft(con, "aicoss:1", profile)["draft"]["body"]
    assert "## 3. 사용 목적" in body and "## 4. 사용 계획 (품목·기간·장소)" in body
    assert "- 사용 기간: {{시작일 ~ 반납일}}" in body


def test_borrow_previous_draft(profile):
    with store.connect() as con:
        seed(con)
        service.put_materials(con, {"careerGoal": "AI 엔지니어"})
        service.make_draft(con, "www:1", profile)
        d = service.make_draft(con, "www:2", profile, borrow_from="www:1")
    assert d["draft"]["generatedBy"] == "borrowed" and d["draft"]["borrowed"][0]["from"] == "www:1"
    assert "초안에서 가져옴" in d["draft"]["body"]


def test_materials_fallback_order(profile):
    with store.connect() as con:
        m = service.materials(con, profile, lambda: {"careerGoal": "장학 재료의 진로", "activities": "튜터링"})
        assert not m["exists"] and m["from"] == "scholarship" and m["careerGoal"] == "장학 재료의 진로"
        profile["draftContext"] = {"careerGoal": "프로필의 진로"}
        m = service.materials(con, profile, lambda: None)
        assert m["from"] == "profile" and m["careerGoal"] == "프로필의 진로"
        service.put_materials(con, {"careerGoal": "내 재료"})
        assert service.materials(con, profile)["exists"]
        service.delete_materials(con)
        assert not service.materials(con, None)["exists"]


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
        ids = [i["id"] for i in service.evaluate(con, profile, TODAY)]
    assert "www:50" not in ids and "www:51" in ids
