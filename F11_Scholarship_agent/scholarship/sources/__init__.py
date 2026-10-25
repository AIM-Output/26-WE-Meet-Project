"""수집기 — 원천 kind → (list_posts, fetch_detail). 자식 프로세스에서만 import 한다 (requests·bs4).

    jnu_board · aspx_board   aspx.py        대표 홈페이지 공지 · 국제협력본부 · 언어교육원
    k2web · profile_board    k2web.py       단과대학·학과·사업단·센터 사이트 (profile_board 는 discover 로 게시판을 먼저 찾는다)
    coss                     coss.py        AICOSS(말머리 '전남대학교') · 차세대통신 COSS · 미래차 부트캠프
    coss_apply               coss_apply.py  차세대통신 '프로그램 신청' 목록 (신청 기간·진행 기간·상태)
    coursemos                coursemos.py   교육혁신본부 · 성장마루
    kboard                   kboard.py      SW중심대학사업단 sojoong.kr (워드프레스 KBoard)
    xe                       xe.py          창업보육센터·창업포털 startup.jnu.ac.kr (XpressEngine)
    events                   events.py      CNU Events 행사일정 events.jnu.ac.kr
    catalog                  catalog.py     교내·교외 장학금 안내 (상시)
"""
from __future__ import annotations

from . import aspx, coss, coss_apply, coursemos, events, k2web, kboard, xe

COLLECTORS = {
    "jnu_board": aspx,
    "aspx_board": aspx,
    "k2web": k2web,
    "profile_board": k2web,
    "coss": coss,
    "coss_apply": coss_apply,
    "coursemos": coursemos,
    "kboard": kboard,
    "xe": xe,
    "events": events,
}
