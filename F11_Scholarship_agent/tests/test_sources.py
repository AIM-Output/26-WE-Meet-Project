"""수집기 파서 — 2026-10-09 실측 HTML 구조를 줄인 조각으로 (학교 사이트에 접속하지 않는다)."""
from scholarship.sources import aspx, catalog, coss, coursemos, k2web
from scholarship.sources.base import Post


class FakeHttp:
    def __init__(self, pages):
        self.pages = pages
        self.count = 0

    def _find(self, url):
        for k, v in self.pages.items():
            if k in url:
                return v
        return "<html></html>"

    def soup(self, url, **kw):
        from bs4 import BeautifulSoup
        self.count += 1
        return BeautifulSoup(self._find(url), "lxml")

    def get(self, url, **kw):
        class R:
            pass
        r = R()
        r.text = self._find(url)
        r.url = url
        return r


JNU_LIST = """<table class="board_list"><tr><td><span class="label">공지</span></td>
<td class="title"><a href="board.aspx?boardID=5&bbsMode=view&page=1&key=70601&cate=8">[장학안내] 2026 장학금 안내</a></td>
<td>학생과</td><td>2026-10-08</td><td>12</td></tr></table>"""


def test_aspx_list():
    cfg = {"base": "https://www.jnu.ac.kr", "listPath": "/WebApp/web/HOM/COM/Board/board.aspx",
           "params": {"boardID": "5", "cate": "8"}, "pageParam": "page", "idParam": "key"}
    posts = aspx.list_posts(cfg, FakeHttp({"page=1": JNU_LIST}), 1)
    assert posts[0].native_id == "70601" and posts[0].writer == "학생과" and posts[0].posted_at == "2026-10-08"
    assert posts[0].pinned


K2_LIST = """<table class="board-table"><tbody>
<tr class="notice"><td class="td-num">공지</td><td class="td-subject"><a href="/bbs/aisw/64/937224/artclView.do">[장학] 운해장학재단 장학생 선발</a></td>
<td class="td-write">학부사무실</td><td class="td-date">2025.12.03</td></tr></tbody></table>"""


def test_k2web_list_and_discover():
    cfg = {"base": "https://aisw.jnu.ac.kr", "site": "aisw", "board": "64", "category": "237"}
    p = k2web.list_posts(cfg, FakeHttp({"artclList.do": K2_LIST}), 1)[0]
    assert p.native_id == "937224" and p.category == "장학" and p.pinned and p.posted_at == "2025-12-03"
    home = '<a href="/aisw/1234/subview.do">공지사항</a><a href="/aisw/9/subview.do">학생회</a>'
    menu = '<a href="/bbs/aisw/64/1/artclView.do">x</a>'
    lst = """<a href="#" onclick="jf_searchArtcl('bbsOpenWrdSeq', '236');">학사</a>
             <a href="#" onclick="jf_searchArtcl('bbsOpenWrdSeq', '237');">장학</a>"""
    http = FakeHttp({"1234/subview.do": menu, "artclList.do": lst, "aisw.jnu.ac.kr": home})
    d = k2web.discover("https://aisw.jnu.ac.kr", http)
    assert (d["site"], d["board"], d["category"], d["filter"]) == ("aisw", "64", "237", "all")


COSS_LIST = """<table class="basicBoard"><tbody><tr><td>
<a href="javascript:movePageView(4117);"><span class="boardCat-wrap"><span>학생지원</span></span><strong class="cutText">근로장학생 모집</strong></a>
<input id="b_link_4117" value="0"></td><td class="mobileNone">2026.09.30</td></tr></tbody></table>"""


def test_coss_list():
    p = coss.list_posts({"base": "https://aicoss.kr", "listPath": "/www/notice/"}, FakeHttp({"notice": COSS_LIST}), 1)[0]
    assert p.native_id == "4117" and p.url.endswith("/www/notice/view/4117") and p.category == "학생지원"


CM_LIST = """<ul data-role="table"><li class="tbody"><span class="title a_l"><a href="/ko/division/notice/view/10402?p=1">[장학] 국가장학금 신청</a></span>
<span class="name">담당자</span><time datetime="2026-05-21T13:59:32+09:00"></time></li></ul>"""


def test_coursemos_list_and_detail():
    cfg = {"base": "https://ile.jnu.ac.kr", "paths": ["/ko/division/notice"]}
    p = coursemos.list_posts(cfg, FakeHttp({"division/notice": CM_LIST}), 1)[0]
    assert p.native_id == "ko-division-notice-10402" and p.posted_at == "2026-05-21" and p.url.endswith("/view/10402")
    detail = "<html><title>[장학] 국가장학금 신청 - 전남대학교 교육혁신본부</title><article>신청기간: 2026. 5. 21. ~ 6. 22.</article></html>"
    p = coursemos.fetch_detail(Post("x", "", "https://ile.jnu.ac.kr/ko/division/notice/view/10402"), cfg, FakeHttp({"view": detail}))
    assert p.title == "[장학] 국가장학금 신청" and "신청기간" in p.body


def test_coursemos_login_wall_keeps_list_title():
    """학습지원 공지(/ko/learning/notice) 상세는 로그인 화면이다(2026-10-10 실측) — <title> 의 '공지사항'으로 덮지 않는다."""
    cfg = {"base": "https://ile.jnu.ac.kr", "paths": ["/ko/learning/notice"]}
    wall = "<html><title>공지사항 - 전남대학교 교육혁신본부</title><h3>공지사항</h3><h1>회원로그인이 필요합니다.</h1></html>"
    p = Post("ko-learning-notice-11058", "[HAI-UP] 생성형 AI 활용 특강", "https://ile.jnu.ac.kr/ko/learning/notice/view/11058")
    p = coursemos.fetch_detail(p, cfg, FakeHttp({"view": wall}))
    assert p.title == "[HAI-UP] 생성형 AI 활용 특강" and p.body == "" and p.extra["login"]


CATALOG ="""<div id="contents"><h3 class="ctype">학부</h3><p class="ctype">장학기본성적: 직전 학기 평균평점이 2.5 이상</p>
<h4 class="ctype">우수 장학금</h4><table><thead><tr><th>장학금명</th><th>수혜자격</th><th>지급액</th></tr></thead>
<tbody><tr><td>진리장학금</td><td>▷ 성적이 우수하고 품행이 단정한 자</td><td>진리장학1:등록금 전액<br/>진리장학2:수업료2 전액</td></tr></tbody></table>
<h3 class="ctype">대학원</h3><h4 class="ctype">우수 장학금</h4><table><thead><tr><th>장학금명</th><th>수혜자격</th><th>지급액</th></tr></thead>
<tbody><tr><td>대학원 진리장학금</td><td>대학원생</td><td>x</td></tr></tbody></table></div>"""


def test_catalog_parse_skips_graduate():
    items = catalog.parse(CATALOG, "https://www.jnu.ac.kr/x")
    assert [i["title"] for i in items] == ["진리장학금"]
    assert items[0]["section"] == "우수 장학금" and "진리장학2" in items[0]["amount"]
