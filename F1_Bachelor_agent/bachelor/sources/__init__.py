"""수집기 — 원천 설정의 kind 로 고른다.

    calendar_table  학사일정 표 (JSON 이 박힌 페이지)          → extract.from_table
    jnu_board       전남대 홈페이지 공지사항(ASP.NET 게시판)     → extract.from_post
    k2web           학과·단과대 홈페이지 (K2Web Wizard)         → extract.from_post
구조가 같은 게시판은 같은 kind 에 설정만 추가한다. 구조가 다르면 파일을 하나 더 만든다.
"""
from . import calendar_table, jnu_board, k2web, k2web_discover  # noqa: F401

BOARD_KINDS = {"jnu_board": jnu_board, "k2web": k2web}
