"""수집 원천 4곳 관리 — 목록·상태, 켜고 끄기, 내 소속 게시판 직접 지정 (F1-R03·R04, F1-S12). 표준 라이브러리만.

  ① jnu_calendar 학교 학사일정 표   ② jnu_notice 학교 공지 › 학사안내
  ③ my_college   내 단과대학 공지    ④ my_dept    내 학부 공지      (③·④ = 프로필 소속으로 찾는다)
끄면 새로 받지 않고, 그 원천에서 온 일정은 목록·캘린더에서 빠진다(service.build_event). 지우지 않으므로 다시 켜면 돌아온다.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

from . import homepages
from .service import Invalid, NotFound
from .store import get_source, list_sources, set_user_config, source_config
from .textutil import parse_board_url

KIND_LABEL = {"calendar_table": "학사일정표", "jnu_board": "학교 공지", "profile_board": "내 소속", "k2web": "게시판"}


def _live_counts(con: sqlite3.Connection) -> dict[str, int]:
    return {r[0]: r[1] for r in con.execute(
        "SELECT source_key, COUNT(*) FROM items WHERE removed_at IS NULL GROUP BY source_key")}


def row_out(r: sqlite3.Row, profile: Optional[dict] = None, live: Optional[dict[str, int]] = None) -> dict:
    cfg = source_config(r)
    out = {
        "key": r["key"], "name": r["name"], "kind": r["kind"], "kindLabel": KIND_LABEL.get(r["kind"], r["kind"]),
        "url": cfg.get("url"), "interval": cfg.get("interval", "06·18시"),
        "enabled": bool(r["enabled"]), "builtin": bool(r["builtin"]),
        "lastRunAt": r["last_run_at"], "lastOkAt": r["last_ok_at"], "state": r["last_result"] or "never",
        "count": r["last_count"], "error": r["last_error"], "items": (live or {}).get(r["key"], 0),
        "scope": None, "target": None, "listedAs": None, "homepage": None, "resolve": None, "board": None,
        "overrideUrl": None, "stale": False,
    }
    if r["kind"] != "profile_board":
        return out
    scope = cfg["scope"]
    res = homepages.resolve(scope, profile)
    user, rt = cfg["user"], cfg["runtime"]
    override = user.get("overrideUrl")
    board = None
    if override:
        parsed = parse_board_url(override) or {}
        board = {"label": "직접 지정", "url": override, "category": "직접 지정한 말머리" if parsed.get("category") else None,
                 "via": "manual", "checkedAt": None}
    elif rt.get("boardUrl") and rt.get("homepage") == res.get("homepage"):
        board = {"label": rt.get("boardLabel"), "url": rt.get("boardUrl"), "category": rt.get("categoryLabel"),
                 "via": "auto", "checkedAt": rt.get("discoveredAt")}
    # 마지막으로 받은 뒤 소속이나 지정 주소가 바뀌었으면 '다시 받아야 함'
    stale = bool(rt.get("identity")) and (
        (override is not None and rt.get("via") != "manual")
        or (override is None and (rt.get("via") == "manual" or rt.get("homepage") != res.get("homepage"))))
    out.update(scope=scope, target=res["target"], listedAs=res.get("listedAs"),
               homepage=(parse_board_url(override) or {}).get("base") if override else res["homepage"],
               resolve="ok" if override else res["status"], board=board, overrideUrl=override, stale=stale,
               url=board["url"] if board else res["homepage"])
    return out


def list_rows(con: sqlite3.Connection, profile: Optional[dict] = None) -> list[dict]:
    live = _live_counts(con)
    return [row_out(r, profile, live) for r in list_sources(con)]


def get_row(con: sqlite3.Connection, key: str, profile: Optional[dict] = None) -> dict:
    r = get_source(con, key)
    if r is None:
        raise NotFound(key)
    return row_out(r, profile, _live_counts(con))


def set_enabled(con: sqlite3.Connection, key: str, enabled: bool) -> None:
    if not get_source(con, key):
        raise NotFound(key)
    con.execute("UPDATE sources SET enabled = ? WHERE key = ?", (int(enabled), key))


def set_override(con: sqlite3.Connection, key: str, url: Optional[str]) -> None:
    """③·④ 의 게시판을 직접 지정한다(자동으로 못 찾았거나 다른 게시판을 원할 때). None 이면 자동으로 되돌린다."""
    r = get_source(con, key)
    if r is None:
        raise NotFound(key)
    if r["kind"] != "profile_board":
        raise Invalid("학교 학사일정·학사안내는 주소를 바꿀 수 없습니다")
    user = source_config(r)["user"]
    if url is None or not url.strip():
        user.pop("overrideUrl", None)
    else:
        if not parse_board_url(url):
            raise Invalid("학과·단과대학 홈페이지 게시판 주소가 아닙니다 — 예: https://aisw.jnu.ac.kr/bbs/aisw/64/artclList.do")
        user["overrideUrl"] = url.strip()
    set_user_config(con, key, user)
