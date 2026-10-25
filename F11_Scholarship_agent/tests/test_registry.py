"""원천 목록 — 프로필 소속으로 '내 장학 원천'이 정해지는지 (학교 전체 · 캠퍼스 · 관련 사업단 · 내 소속)."""
from scholarship import registry as R


def keyed(rows):
    return {r["key"]: r for r in rows}


def test_every_source_is_well_formed():
    keys = set()
    for s in R.sources():
        assert s["key"] not in keys
        keys.add(s["key"])
        assert s["group"] in R.load()["groups"]
        assert s["kind"] in ("jnu_board", "aspx_board", "k2web", "coss", "coss_apply", "coursemos", "kboard", "xe", "events",
                             "catalog", "relay", "profile_board")
        if s["kind"] == "k2web":
            assert s["site"] and s["board"]
        assert (s.get("audience") or {}).get("scope") in ("all", "campus", "related", "mine")


def test_ai_student_gets_ai_projects():
    rows = keyed(R.resolve({"college": "AI융합대학", "department": "인공지능학부"}))
    assert rows["jnu_scholarship"]["enabled"] and rows["jnu_catalog"]["enabled"]
    for k in ("aicoss", "nccoss", "nccoss_apply", "sojoong", "aisw_sec", "futurecar"):
        assert rows[k]["enabled"] and rows[k]["relevance"]["level"] == "related", k
    assert not rows["greenbio"]["enabled"] and rows["greenbio"]["relevance"]["level"] == "open"   # 켤 수 있음
    assert not rows["rise_jn"]["enabled"]                                                         # 여수캠퍼스 대상


def test_other_departments():
    rows = keyed(R.resolve({"college": "공과대학", "department": "신소재공학부"}))
    assert rows["battery"]["enabled"] and rows["semicon"]["enabled"] and rows["icee"]["enabled"]
    assert not rows["aicoss"]["enabled"]
    rows = keyed(R.resolve({"college": "농업생명과학대학", "department": "원예생명공학과"}))
    assert rows["greenbio"]["enabled"] and rows["basicsci"]["relevance"]["level"] == "related"
    rows = keyed(R.resolve({"college": "인문대학", "department": "사학과"}))
    assert rows["huss"]["enabled"] and not rows["battery"]["enabled"]
    rows = keyed(R.resolve({"college": "공학대학", "department": "의공학과"}))
    assert rows["rise_jn"]["enabled"] and rows["rise_jn"]["relevance"]["level"] == "campus"


def test_user_override_wins():
    rows = keyed(R.resolve({"college": "인문대학", "department": "사학과"}, {"battery": True, "jnu_notice": False}))
    assert rows["battery"]["enabled"] and rows["battery"]["userSet"]
    assert not rows["jnu_notice"]["enabled"]


def test_aicoss_reads_only_jnu_category():
    assert R.get("aicoss")["cate"] == "전남대학교"           # 7개 대학 연합 게시판 — 전남대 말머리만 (2026-10-25)
    assert R.get("aisw_sw") is None and R.get("sojoong")["base"] == "https://sojoong.kr"


def test_collectable_skips_relay():
    rows = R.collectable(R.resolve({"college": "AI융합대학", "department": "인공지능학부"}))
    assert all(r["kind"] != "relay" for r in rows)


def test_campus_and_fields():
    assert R.campus_of({"college": "수산해양대학"}) == "여수"
    assert R.campus_of({"college": "AI융합대학"}) == "광주"
    assert R.fields_of({"college": "사범대학", "department": "체육교육과"}) == ["예체능", "교육"]
    assert R.fields_of({"college": "자연과학대학", "department": "화학과"}) == ["자연과학"]


def test_unit_for_writer():
    assert R.unit_for("인문사회융합인재양성사업단")["key"] == "huss"
    assert R.unit_for("첨단산업인재양성부트캠프(미래")["key"] == "futurecar"        # 미래차는 자체 사이트 (2026-10-25)
    assert R.unit_for("첨단산업인재양성부트캠프(인공")["key"] == "bootcamp"
    assert R.unit_for("창업교육혁신선도대학사업단")["key"] == "cibi"
    assert R.unit_for("학생과") is None
    assert R.unit_for("총무과", "[이차전지특성화대학사업단] 이차전지융합전공 학부생 모집")["key"] == "battery"


def test_homepage_from_f1_directory():
    hp = R.homepage("dept", {"college": "AI융합대학", "department": "인공지능학부"})
    assert hp and hp["homepage"].startswith("https://aisw.jnu.ac.kr")
    assert R.homepage("college", {"college": "공과대학"})["homepage"].startswith("https://eng.jnu.ac.kr")
    assert R.homepage("dept", {"college": "공과대학", "department": "없는학과"}) is None
