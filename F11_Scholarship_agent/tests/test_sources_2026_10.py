"""2026-10-25 사업단 재조사로 더한 수집기 — 실측 HTML 을 줄인 조각으로 (학교 사이트에 접속하지 않는다).

AICOSS 말머리 · 미래차 부트캠프(COSS 같은 CMS, 다른 경로) · 차세대통신 '프로그램 신청' · SW중심대학 sojoong.kr(KBoard) ·
창업보육센터 startup.jnu.ac.kr(XE) · CNU Events(events.jnu.ac.kr)
"""
from scholarship.sources import coss, coss_apply, events, kboard, xe
from scholarship.sources.base import Post


class FakeHttp:
    """URL 에 키 글자가 들어 있으면 그 HTML. 마지막 요청의 params 를 남긴다."""

    def __init__(self, pages):
        self.pages = pages
        self.last = None

    def _find(self, url):
        return next((v for k, v in self.pages.items() if k in url), "<html></html>")

    def soup(self, url, **kw):
        from bs4 import BeautifulSoup
        self.last = (url, kw.get("params"))
        return BeautifulSoup(self._find(url), "lxml")


COSS_LIST = """<table class="basicBoard"><tbody><tr><td class="mobileNone"><em class="boxIcon">Notice</em></td><td class="alignLeft">
<a href="javascript:movePageView(4125);"><span class="boardCat-wrap"><b class="boardCategory">전남대학교</b><span>비교과</span></span>
<strong class="cutText">AI 도구 특강 신청 안내(~10/28)</strong></a><input id="b_link_4125" type="hidden" value="0"/></td>
<td class="mobileNone">2026.10.21</td></tr></tbody></table>"""


def test_coss_cate_and_view_path():
    http = FakeHttp({"notice": COSS_LIST})
    p = coss.list_posts({"base": "https://aicoss.kr", "listPath": "/www/notice/", "cate": "전남대학교"}, http, 1)[0]
    assert http.last[1]["cate"] == "전남대학교"                       # 7개 대학 연합 게시판 — 전남대 글만
    assert p.native_id == "4125" and p.category == "비교과" and p.url == "https://aicoss.kr/www/notice/view/4125"
    p = coss.list_posts({"base": "https://futurecar.kr", "listPath": "/notice/", "viewPath": "/notice/view/"},
                        FakeHttp({"notice": COSS_LIST}), 1)[0]
    assert p.url == "https://futurecar.kr/notice/view/4125"


APPLY_LIST = """<ul><li><a href="javascript:void(0);" onclick="movePageView(156)"><span class="applyInfo-basic"><span class="applyInfo-text">
<span class="applyInfo-title"><strong> 2026학년 2학기 기업 연계형 캡스톤디자인 과제 지원 안내</strong></span>
<span class="applyInfo-solt"><em>교과과정</em></span></span></span><span class="applyInfo-period"><span class="applyInfo-date">
<span><em>신청기간 :</em><span>2026-09-22 ~ 2026-09-30</span></span><span><em>진행기간 :</em><span>2026-10-01 ~ 2026-12-04</span></span>
</span><span class="applyInfo-state"><i class="type_3">신청마감</i></span></span></a></li></ul>"""
APPLY_VIEW = """<section class="viewContainer"><h3>2026학년 2학기 기업 연계형 캡스톤디자인 과제 지원 안내</h3>
<div class="applyProgram_info"><table><tr><th>프로그램 참여대상</th><td>6개 참여학과 캡스톤디자인 수강생</td></tr></table></div>
<div class="viewContainer-content"><p>다음과 같이 과제를 지원합니다.</p></div></section>"""


def test_coss_apply_list_and_detail():
    cfg = {"base": "https://jnu.nccoss.kr", "listPath": "/www/apply_program/"}
    p = coss_apply.list_posts(cfg, FakeHttp({"apply_program": APPLY_LIST}), 1)[0]
    assert p.native_id == "156" and p.url == "https://jnu.nccoss.kr/www/apply_program/view/156" and p.posted_at == "2026-09-22"
    assert p.category is None and "신청기간 : 2026-09-22 ~ 2026-09-30" in p.extra["summary"]
    assert "과정 : 교과과정" in p.extra["summary"]                    # 말머리가 아니라 본문 줄로 (학사로 오인하지 않게)
    p = coss_apply.fetch_detail(p, cfg, FakeHttp({"view": APPLY_VIEW}))
    assert p.body.startswith("신청기간 : 2026-09-22") and "참여대상" in p.body and "과제를 지원합니다" in p.body


KB_LIST = """<div class="kboard-list"><table><tbody><tr class="kboard-list-notice"><td class="kboard-list-title">
<a href="/notice/notice-board/?uid=1048&amp;mod=document"><div class="kboard-default-cut-strings custom-title">
<div class="kboard-default-cut-strings custom-title"> [모집홍보] 2026 METAmobility 자율주행 자동차 경진대회 </div></div></a>
<div class="custom-date-margin kboard-list-date"><span class="kboard-date custom-date">2026.10.19</span></div></td></tr></tbody></table></div>"""
KB_VIEW = """<div class="kboard-document-wrap"><div class="kboard-title">[모집홍보] 2026 METAmobility 자율주행 자동차 경진대회</div>
<div class="kboard-detail"><div class="detail-date">작성일 2026-10-19 13:25</div></div>
<div class="kboard-content"><div class="content-view">1. 대 회 명 : METAmobility<br>2. 신청기간: 2026. 10. 19. ~ 10. 31.</div></div>
<div class="kboard-attach"><a href="/?action=kboard_file_download&amp;id=1">붙임1.hwp</a></div></div>"""


def test_kboard_list_and_detail():
    cfg = {"base": "https://sojoong.kr", "paths": ["/notice/notice-board/"]}
    p = kboard.list_posts(cfg, FakeHttp({"notice-board": KB_LIST}), 1)[0]
    assert p.native_id == "notice-notice-board-1048" and p.pinned and p.posted_at == "2026-10-19" and p.category == "모집홍보"
    assert p.url == "https://sojoong.kr/notice/notice-board/?uid=1048&mod=document"
    p = kboard.fetch_detail(p, cfg, FakeHttp({"uid=1048": KB_VIEW}))
    assert "신청기간" in p.body and p.attachments[0]["name"] == "붙임1.hwp"


XE_LIST = """<table class="bd_lst"><tbody>
<tr class="notice"><td class="title"><a href="/board_MRLV57/36329"><strong>[모집공고]창업 아이템 경진대회</strong></a></td></tr>
<tr><td class="title"><a class="hx" href="/index.php?mid=board_MRLV57&amp;page=1&amp;document_srl=36462">[모집공고]2026 대학 혁신창업 포럼</a></td></tr>
</tbody></table>"""
XE_VIEW = """<div class="rd_hd"><h1>[모집공고]2026 대학 혁신창업 포럼</h1><span class="date">2026.10.22 17:48</span></div>
<div class="rd_body"><article><div class="xe_content">신청기간: 2026. 10. 22. ~ 11. 5.</div></article></div>
<a href="/?module=file&amp;act=procFileDownload&amp;file_srl=2144">포스터.pdf</a>"""


def test_xe_list_both_link_shapes_and_detail():
    cfg = {"base": "http://startup.jnu.ac.kr", "mids": ["board_MRLV57"]}
    posts = xe.list_posts(cfg, FakeHttp({"index.php": XE_LIST}), 1)
    assert [p.native_id for p in posts] == ["board_MRLV57-36329", "board_MRLV57-36462"] and posts[0].pinned
    assert posts[1].url == "http://startup.jnu.ac.kr/board_MRLV57/36462"
    p = xe.fetch_detail(posts[1], cfg, FakeHttp({"36462": XE_VIEW}))
    assert p.posted_at == "2026-10-22" and "신청기간" in p.body and p.attachments[0]["name"] == "포스터.pdf"


EV_LIST = """<div class="media"><div class="media-body"><span class="u-label">기타</span>
<h3><a href="/EventView.aspx?eventId=2371">2026-동계 현장실습 참여학생 및 기업모집</a></h3>
<ul><li><span><i class="fa fa-calendar"></i>2026.10.22.(목) ~ 2026.11.10.(화)(20일간) </span></li>
<li><span><i class="fa fa-map-marker"></i>각 기업의 실습 </span></li><li><span><i class="fa fa-building"></i>현장실습지원센터 </span></li></ul>
</div></div>"""
EV_VIEW = """<html><body><ul><li><h4><span>참여대상: 전체(모든사람) </span></h4></li><li><h4><span> 행사방식 : 오프라인(대면) </span></h4></li></ul>
<header><ul><li>주최 및 주관</li><li>/</li><li> 현장실습지원센터</li><li>등록일 2026.10.22 Views 123</li></ul></header>
<a href="https://events.jnu.ac.kr/upload/files/2026/10/a.pdf" download="운영 계획.pdf">운영 계획.pdf</a>
<div><h3>행사 상세 정보 :</h3><p>나. 학생 신청기간: 2026. 10. 27.(화) ~ 11. 10.(화)</p></div></body></html>"""


def test_events_list_and_detail():
    cfg = {"base": "https://events.jnu.ac.kr"}
    p = events.list_posts(cfg, FakeHttp({"Search.aspx": EV_LIST}), 1)[0]
    assert p.native_id == "2371" and p.category == "기타" and p.writer == "현장실습지원센터"
    assert p.extra["when"].startswith("2026.10.22.") and p.extra["place"] == "각 기업의 실습"
    p = events.fetch_detail(p, cfg, FakeHttp({"EventView": EV_VIEW}))
    assert p.posted_at == "2026-10-22" and p.writer == "현장실습지원센터"
    assert p.body.startswith("기간 : 2026.10.22.") and "참여대상 : 전체(모든사람)" in p.body and "학생 신청기간" in p.body
    assert p.attachments[0]["name"] == "운영 계획.pdf"


def test_post_default():
    assert Post("1", "t", "u").extra == {}
