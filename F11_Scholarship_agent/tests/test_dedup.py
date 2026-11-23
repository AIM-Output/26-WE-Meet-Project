"""같은 글 묶기 (2026-11-19) — 제목 키는 말머리·공백·기호만 빼고 괄호 안(재단·대학·회차)은 남긴다 · 저장된 묶음 다시 짓기."""
from conftest import TODAY, add_notice

from scholarship import config as C
from scholarship import service, store
from scholarship.textutil import strip_board_category, title_key


def test_title_key_keeps_foundation_and_round():
    # 다른 장학 — 예전 키(괄호 안을 다 지움)로는 하나로 묶여 한쪽이 숨었다 (2026-11-19 실측)
    assert title_key("[장학안내][(재) 김해시미래인재장학재단] 2026년 장학생 선발 안내") != \
        title_key("[장학안내][(제)경주시장학회]2026년 장학생 선발 안내")
    assert title_key("[장학안내][(재) 인천인재평생교육진흥원] 2026년도 하반기 장학생 선발 안내") != \
        title_key("[장학안내][대구광역시 달서인재육성장학재단] 2026년도 하반기 장학생 선발안내")
    assert title_key("[장학안내][한국장학재단] 푸른등대 기부장학금 2026학년도 2학기 신규장학생 선발 안내") != \
        title_key("[장학안내][한국장학재단] 푸른등대 기부장학금(2차) 2026학년도 2학기 신규장학생 선발 안내")
    # 같은 글 — 게시판마다 말머리·띄어쓰기만 다르다
    assert title_key("[장학안내] 2026 OO장학재단 장학생 선발 안내") == title_key("[장학] 2026 OO장학재단 장학생 선발안내")
    assert title_key("[장학관련]2026 OO장학재단 장학생 선발 안내") == title_key("2026 OO 장학재단 장학생 선발 안내")
    assert strip_board_category("[장학안내][한국장학재단] 푸른등대") == "[한국장학재단] 푸른등대"      # 기관 괄호는 둔다


def test_regroup_on_new_version(profile):
    """예전 판으로 묶인 다른 장학을 앱이 새 판을 처음 열 때 한 번 다시 묶는다. 같은 글은 계속 묶이고,
    진행 상태가 있는 글은 숨지 않으며, 풀린 글은 새 공지 알림으로 쏟아지지 않게 알린 것으로 친다."""
    titles = {"www:1": "[장학안내][(재) 김해시미래인재장학재단] 2026년 장학생 선발 안내",
              "www:2": "[장학안내][(제)경주시장학회]2026년 장학생 선발 안내",
              "www:3": "[장학안내][한국장학재단] 푸른등대 기부장학금 2026학년도 2학기 신규장학생 선발 안내",
              "www:4": "[장학안내][한국장학재단] 푸른등대 기부장학금(2차) 2026학년도 2학기 신규장학생 선발 안내",
              "www:5": "[장학안내] 2026 OO장학재단 장학생 선발 안내",
              "aisw:5": "[장학] 2026 OO장학재단 장학생 선발 안내"}
    with store.connect() as con:
        for i, (nid, t) in enumerate(titles.items()):
            add_notice(con, nid, t, "신청기간 : 2026. 10. 1. ~ 2026. 10. 30.", source="my_dept" if nid.startswith("aisw") else "jnu_scholarship")
            con.execute("UPDATE notices SET first_seen = ?, title_key = 'old' WHERE id = ?", (f"2026-10-0{i + 1}T09:00:00", nid))
        # 예전 판의 묶음 — 다른 재단·다른 회차가 하나로 접혀 있었다. www:4(2차)는 사용자가 진행 상태를 남긴 글
        con.execute("UPDATE notices SET dup_of = 'www:1' WHERE id = 'www:2'")
        con.execute("UPDATE notices SET dup_of = 'www:3' WHERE id = 'www:4'")
        con.execute("UPDATE notices SET dup_of = 'www:5' WHERE id = 'aisw:5'")
        store.put_state(con, "www:4", progress="approved")
        store.set_meta(con, "title_key_ver", "1")
    store._initialized.clear()                                   # 앱을 새 판으로 다시 띄운 것처럼
    with store.connect() as con:
        dups = {r["id"]: r["dup_of"] for r in con.execute("SELECT id, dup_of FROM notices")}
        alerted = {r["notice_id"] for r in con.execute("SELECT notice_id FROM user_state WHERE alerted_at IS NOT NULL")}
        assert store.get_meta(con, "title_key_ver") == str(C.TITLE_KEY_VERSION)
        ids = [i["id"] for i in service.overview(con, profile, TODAY)["items"]]
    assert dups == {"www:1": None, "www:2": None, "www:3": None, "www:4": None, "www:5": None, "aisw:5": "www:5"}
    assert {"www:2", "www:4"} <= set(ids) and "aisw:5" not in ids
    assert alerted == {"www:2", "www:4"}
