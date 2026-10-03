"""수집 원천 4곳 — 내 소속 홈페이지 찾기(homepages) · 학사 공지 게시판 찾기(k2web_discover) · 켜고 끄기 · ③·④ 수집 흐름."""
import json
from datetime import date, datetime

import pytest

from bachelor import config as C
from bachelor import homepages, pipeline, service, sources_admin, store
from bachelor.register import register
from bachelor.sources import k2web_discover as kd
from bachelor.sources.base import FormatChanged, NeedsProfile, NotListed

from test_register_notify import P3, cand

DIRECTORY = {"updatedAt": "2026-09-29T10:00:00", "colleges": [
    {"name": "AI융합대학", "homepage": "https://cvg.jnu.ac.kr", "departments": [
        {"name": "인공지능학부", "homepage": "https://aisw.jnu.ac.kr"},
        {"name": "빅데이터융합학과", "homepage": None}]},
    {"name": "공학대학(여수)", "homepage": "https://eng-ys.jnu.ac.kr", "departments": [
        {"name": "전자통신전기공학부", "homepage": "https://ece-ys.jnu.ac.kr"}]},
    {"name": "공과대학", "homepage": "https://eng.jnu.ac.kr", "departments": [
        {"name": "전자컴퓨터공학부", "homepage": "https://ece.jnu.ac.kr"},
        {"name": "기계공학부", "homepage": "https://me.jnu.ac.kr"}]},
]}


@pytest.fixture()
def directory():
    C.LOCAL_DIRECTORY.parent.mkdir(parents=True, exist_ok=True)
    C.LOCAL_DIRECTORY.write_text(json.dumps(DIRECTORY, ensure_ascii=False), encoding="utf-8")
    homepages._cache.update(path=None, mtime=None, data=None)
    yield
    C.LOCAL_DIRECTORY.unlink(missing_ok=True)
    homepages._cache.update(path=None, mtime=None, data=None)


# ── 내 소속 → 홈페이지 ─────────────────────────────────────

def test_resolve_college_and_dept(directory):
    r = homepages.resolve("college", P3)
    assert r == {"status": "ok", "target": "AI융합대학", "homepage": "https://cvg.jnu.ac.kr", "listedAs": "AI융합대학"}
    r = homepages.resolve("dept", P3)
    assert r["status"] == "ok" and r["homepage"] == "https://aisw.jnu.ac.kr"
    # 괄호가 붙은 목록 이름 ('공학대학(여수)') · 학과/학부 꼬리가 다른 이름
    assert homepages.resolve("college", {"college": "공학대학"})["homepage"] == "https://eng-ys.jnu.ac.kr"
    r = homepages.resolve("dept", {"college": "공과대학", "department": "전자컴퓨터공학과"})
    assert r["homepage"] == "https://ece.jnu.ac.kr" and r["listedAs"] == "전자컴퓨터공학부"
    # 학과 이름이 목록에 없으면 전공 이름으로
    r = homepages.resolve("dept", {"college": "공과대학", "department": "기계공학부군", "major": "기계공학전공"})
    assert r["homepage"] == "https://me.jnu.ac.kr"


def test_resolve_stays_in_same_college(directory):
    # 단과대학을 찾았으면 그 안에서만 — 여수 공학대학의 '기계공학과'가 광주 공과대학 '기계공학부'로 가지 않는다
    r = homepages.resolve("dept", {"college": "공학대학", "department": "기계공학과"})
    assert r["status"] == "not_found"
    # 단과대학이 목록에 없으면('직할학부') 전체에서 찾는다
    r = homepages.resolve("dept", {"college": "직할학부", "department": "기계공학과"})
    assert r["homepage"] == "https://me.jnu.ac.kr"
    # 학부 자체가 단과대학급('공학대학(여수)' 처럼 목록에 단과대학으로만 있는 이름)
    r = homepages.resolve("dept", {"college": "직할학부", "department": "공과대학"})
    assert r["homepage"] == "https://eng.jnu.ac.kr"


def test_resolve_missing(directory):
    assert homepages.resolve("college", None)["status"] == "needs_profile"
    assert homepages.resolve("dept", {"college": "AI융합대학"})["status"] == "needs_profile"
    # 홈페이지 칸이 비어 있는 학과 · 목록에 없는 단과대학
    assert homepages.resolve("dept", {"college": "AI융합대학", "department": "빅데이터융합학과"})["status"] == "not_found"
    assert homepages.resolve("college", {"college": "우주대학"}) == {
        "status": "not_found", "target": "우주대학", "homepage": None, "listedAs": None}
    assert homepages.summary()["source"] == "local" and homepages.summary()["departments"] == 5


# ── 홈페이지 → 학사 공지 게시판 ─────────────────────────────

HOME = """<html><body><nav>
<a href="/aisw/3301/subview.do">학부소개</a>
<a href="/aisw/3310/subview.do">인공지능학부</a>
<a href="/aisw/3320/subview.do">대학원 공지</a>
<a href="/aisw/3330/subview.do">공지사항</a>
<a href="/aisw/3331/subview.do">학사공지</a>
<a href="/aisw/3332/subview.do">취업 공지</a>
<a href="https://www.jnu.ac.kr/jnu/1/subview.do">학사공지</a>
</nav><a href="/bbs/aisw/99/artclList.do">더보기</a></body></html>"""
MENU = """<form action="/bbs/aisw/64/artclList.do"></form><a href="/bbs/aisw/64/1234/artclView.do">글</a>
<a href="/bbs/aisw/64/1235/artclView.do">글</a><a href="/bbs/aisw/7/artclList.do">배너</a>"""
LIST = """<ul class="tabs">
<li><a href="#" onclick="jf_searchArtcl('bbsOpenWrdSeq', ''); return false;">전체</a></li>
<li><a href="#" onclick="jf_searchArtcl('bbsOpenWrdSeq', '235'); return false;">일반</a></li>
<li><a href="#" onclick="jf_searchArtcl('bbsOpenWrdSeq', '236'); return false;"> 학사 </a></li>
<li><a href="#" onclick="jf_searchArtcl('bbsOpenWrdSeq', '237'); return false;">대학원 학사</a></li>
</ul><table class="board-table"></table>"""


def test_menu_scoring():
    got = [(s, t) for s, _i, t, _u in kd.menu_candidates(HOME, "https://aisw.jnu.ac.kr/aisw/index.do")]
    # '인공지능학부' 는 공지가 아니다 · 대학원/취업 공지와 다른 사이트 링크는 뺀다 · 학사공지가 먼저
    assert got == [(30, "학사공지"), (10, "공지사항")]
    assert kd.board_ref(MENU) == ("aisw", "64")
    assert kd.more_links(HOME) == [("aisw", "99")]


def test_pick_category():
    tabs = kd.categories(LIST)
    assert [t["label"] for t in tabs] == ["일반", "학사", "대학원 학사"]       # 값이 빈 '전체' 는 말머리가 아니다
    assert kd.pick_category(tabs)["value"] == "236"
    assert kd.pick_category([{"param": "bbsClSeq", "value": "9", "label": "학사일정"}])["value"] == "9"
    assert kd.pick_category([{"param": "bbsClSeq", "value": "9", "label": "대학원학사"}]) is None
    assert kd.pick_category([]) is None


class _Resp:
    def __init__(self, url, text):
        self.url, self.text = url, text


class FakeHttp:
    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url):
        self.calls.append(url)
        if url not in self.pages:
            raise AssertionError(f"예상 못 한 요청: {url}")
        final, text = self.pages[url]
        return _Resp(final, text)


def test_discover():
    http = FakeHttp({
        "https://aisw.jnu.ac.kr": ("https://aisw.jnu.ac.kr/aisw/index.do", HOME),
        "https://aisw.jnu.ac.kr/aisw/3331/subview.do": ("https://aisw.jnu.ac.kr/aisw/3331/subview.do", MENU),
        "https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do": ("https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do", LIST),
    })
    d = kd.discover("https://aisw.jnu.ac.kr", http)
    assert (d["site"], d["board"], d["boardLabel"], d["category"], d["categoryParam"]) == \
        ("aisw", "64", "학사공지", "236", "bbsOpenWrdSeq")
    assert len(http.calls) == 3


def test_discover_falls_back_to_more_link():
    http = FakeHttp({
        "https://x.jnu.ac.kr": ("https://x.jnu.ac.kr/x/index.do", '<a href="/bbs/x/5/artclList.do">더보기</a>'),
        "https://x.jnu.ac.kr/bbs/x/5/artclList.do": ("https://x.jnu.ac.kr/bbs/x/5/artclList.do", "<table></table>"),
    })
    d = kd.discover("https://x.jnu.ac.kr", http)
    assert (d["board"], d["boardLabel"], d["category"]) == ("5", "첫 화면 공지", None)
    with pytest.raises(FormatChanged):
        kd.discover("https://y.jnu.ac.kr", FakeHttp({"https://y.jnu.ac.kr": ("https://y.jnu.ac.kr/", "<p>빈 화면</p>")}))


# ── 켜고 끄기 ────────────────────────────────────────────

def test_seed_has_four_sources_and_drops_old_ones(db):
    assert [r["key"] for r in store.list_sources(db)] == ["jnu_calendar", "jnu_notice", "my_dept", "my_college"]
    db.execute("INSERT INTO sources(key, name, kind, config, priority, builtin, enabled, created_at) "
               "VALUES ('aisw_haksa', '옛 학과 게시판', 'k2web', '{}', 3, 0, 1, '2026-01-01')")
    register(db, "aisw_haksa", [cand("옛 게시판 일정", date(2026, 10, 1), post="1")], post_id="1")
    store.seed_sources(db)
    assert store.get_source(db, "aisw_haksa") is None
    assert service.list_events(db, P3) == []                        # 그 원천의 일정은 보이지 않는다


def test_disable_hides_and_enable_restores(db):
    register(db, "jnu_calendar", [cand("제2학기 최종 등록", date(2026, 10, 1))], snapshot_since=date(2026, 1, 1))
    register(db, "my_dept", [cand("제2학기 최종 등록", date(2026, 10, 1), post="5"),
                             cand("학부 졸업논문 제출", date(2026, 11, 20), post="5")], post_id="5")
    titles = lambda: sorted(e["title"] for e in service.list_events(db, P3))  # noqa: E731
    assert titles() == ["제2학기 최종 등록", "학부 졸업논문 제출"]

    sources_admin.set_enabled(db, "my_dept", False)
    assert titles() == ["제2학기 최종 등록"]                             # 학교 표에도 있는 일정은 남는다
    e = service.list_events(db, P3)[0]
    assert [s["key"] for s in e["sources"]] == ["jnu_calendar"]
    rows = {r["key"]: r for r in sources_admin.list_rows(db, P3)}
    assert rows["my_dept"]["enabled"] is False and rows["my_dept"]["items"] == 2    # 지우지 않았다

    sources_admin.set_enabled(db, "my_dept", True)
    assert titles() == ["제2학기 최종 등록", "학부 졸업논문 제출"]
    with pytest.raises(service.NotFound):
        sources_admin.set_enabled(db, "nope", True)


def test_override_only_for_profile_boards(db, directory):
    with pytest.raises(service.Invalid):
        sources_admin.set_override(db, "jnu_notice", "https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do")
    with pytest.raises(service.Invalid):
        sources_admin.set_override(db, "my_dept", "https://aisw.jnu.ac.kr/aisw/3331/subview.do")
    sources_admin.set_override(db, "my_dept", " https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do?bbsOpenWrdSeq=236 ")
    row = sources_admin.get_row(db, "my_dept", P3)
    assert row["overrideUrl"] == "https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do?bbsOpenWrdSeq=236"
    assert row["board"]["via"] == "manual" and row["resolve"] == "ok"
    sources_admin.set_override(db, "my_dept", None)
    row = sources_admin.get_row(db, "my_dept", P3)
    assert row["overrideUrl"] is None and row["board"] is None and row["homepage"] == "https://aisw.jnu.ac.kr"
    row = sources_admin.get_row(db, "my_college", None)
    assert row["resolve"] == "needs_profile" and row["target"] is None


# ── ③·④ 수집 흐름 ────────────────────────────────────────

BOARD = {"base": "https://aisw.jnu.ac.kr", "site": "aisw", "board": "64", "boardLabel": "학사공지",
         "boardUrl": "https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do", "category": "236",
         "categoryParam": "bbsOpenWrdSeq", "categoryLabel": "학사", "discoveredAt": "2026-09-29T10:00:00"}


@pytest.fixture()
def flow(db, directory, monkeypatch):
    state = {"profile": dict(P3), "discover": 0, "boards": []}
    monkeypatch.setattr(pipeline, "load_local_profile", lambda: state["profile"])

    def discover(homepage, http):
        state["discover"] += 1
        site = homepage.split("//")[1].split(".")[0]
        return {**BOARD, "base": homepage, "site": site, "boardUrl": f"{homepage}/bbs/{site}/64/artclList.do",
                "discoveredAt": datetime.now().isoformat(timespec="seconds")}

    def run_board(cfg, http, dry_run, pages):
        state["boards"].append(cfg)
        with store.connect() as con:
            register(con, cfg["key"], [cand(f"{cfg['site']} 학사 일정", date(2026, 10, 7), post="1")], post_id="1")
        return {"count": 1}

    monkeypatch.setattr(pipeline.k2web_discover, "discover", discover)
    monkeypatch.setattr(pipeline, "run_board", run_board)
    return state


def _cfg(key):
    with store.connect() as con:
        return store.source_config(store.get_source(con, key))


def test_profile_board_flow(flow, db):
    pipeline.run_profile_board(_cfg("my_dept"), None, False, 1)
    cfg = flow["boards"][-1]
    assert cfg["kind"] == "k2web" and cfg["site"] == "aisw" and cfg["category"] == "236"
    assert cfg["audience"] == {"departments": ["인공지능학부"]}
    rt = _cfg("my_dept")["runtime"]
    assert rt["target"] == "인공지능학부" and rt["homepage"] == "https://aisw.jnu.ac.kr" and rt["via"] == "auto"
    assert store.source_names(db)["my_dept"] == "인공지능학부 공지"

    # 7일 안에 찾아 둔 게시판은 다시 찾지 않는다
    pipeline.run_profile_board(_cfg("my_dept"), None, False, 1)
    assert flow["discover"] == 1 and flow["boards"][-1]["board"] == "64"

    # 소속이 바뀌면 → '다시 받아야 함' → 다음 수집에서 새 게시판 · 이전 게시판 일정 정리
    flow["profile"] = {**P3, "college": "공과대학", "department": "기계공학부"}
    row = sources_admin.get_row(db, "my_dept", flow["profile"])
    assert row["stale"] is True and row["homepage"] == "https://me.jnu.ac.kr"
    pipeline.run_profile_board(_cfg("my_dept"), None, False, 1)
    titles = [e["title"] for e in service.list_events(db, flow["profile"])]
    assert titles == ["me 학사 일정"]
    assert sources_admin.get_row(db, "my_dept", flow["profile"])["stale"] is False


def test_profile_board_waits_or_uses_override(flow, db):
    flow["profile"] = {"grade": 2}
    with pytest.raises(NeedsProfile):
        pipeline.run_profile_board(_cfg("my_college"), None, False, 1)
    flow["profile"] = {"college": "우주대학"}
    with pytest.raises(NotListed):
        pipeline.run_profile_board(_cfg("my_college"), None, False, 1)
    # 직접 지정하면 목록에 없어도 읽는다 · 말머리도 주소에서
    sources_admin.set_override(db, "my_college", "https://space.jnu.ac.kr/bbs/space/3/artclList.do?bbsClSeq=4")
    db.commit()
    pipeline.run_profile_board(_cfg("my_college"), None, False, 1)
    cfg = flow["boards"][-1]
    assert (cfg["site"], cfg["board"], cfg["category"], cfg["categoryParam"]) == ("space", "3", "4", "bbsClSeq")
    assert flow["discover"] == 0
