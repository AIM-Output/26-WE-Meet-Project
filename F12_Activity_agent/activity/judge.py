"""LLM 관련도 판단 (선택, F12-R21) — 키워드·태그로 못 가른 '모집 중' 공지만 LLM 에 묻는다 (5절 ④).

보내는 것은 **제목 + 본문 앞부분 + 내 관심사 목록**뿐이다(9절 프라이버시 — 이름·학번·프로필은 보내지 않는다).
결과는 (공지, 관심사 해시) 마다 저장해 다시 묻지 않고, 관심사를 바꾸면 새로 판단한다. 하루 호출 상한(LLM_DAILY_MAX)을 넘으면
그날은 키워드 판정만 한다(9절 비용). LLM 이 없으면 아무것도 하지 않는다 — 등급은 키워드·소속으로만(F12-R24).
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import date
from typing import Callable, Optional

from . import config as C
from . import interests as I
from . import llm as L
from . import service, store

SYSTEM = """너는 대학생에게 온 학교 공지가 그 학생의 관심사와 얼마나 관련 있는지 판단한다.
답은 한 줄만: '높음 - 이유' · '중간 - 이유' · '낮음 - 이유' (이유는 30자 이내). 다른 말은 쓰지 않는다."""
GRADE = {"높음": "match", "중간": "related", "낮음": "other"}


def _day(con: sqlite3.Connection, today: date) -> int:
    d = store.loads(store.get_meta(con, "llm_day"), {}) or {}
    return int(d.get("count", 0)) if d.get("date") == today.isoformat() else 0


def pending(con: sqlite3.Connection, profile: Optional[dict], today: Optional[date] = None) -> list[dict]:
    """LLM 에 물을 공지 — 모집 중이고 키워드·태그·제외어에 하나도 안 걸린 것(소속으로만 '관련 있음'인 것 포함), 마감 가까운 순."""
    items = service.evaluate(con, profile, today)
    return [i for i in items if i["status"] == "open" and i["by"] in ("none", "affiliation") and not i["flipped"]]


def run_batch(con: sqlite3.Connection, profile: Optional[dict], chat: Optional[Callable[[str, str], str]] = None,
              limit: int = C.LLM_BATCH, today: Optional[date] = None) -> int:
    """한 번에 최대 limit 건 판단해 저장. 반환: 판단한 수."""
    today = today or date.today()
    chat = chat or (L.chat if L.available() else None)
    interests = I.from_profile(profile)
    if chat is None or not I.is_set(interests):
        return 0
    room = C.LLM_DAILY_MAX - _day(con, today)
    if room <= 0:
        return 0
    ih = I.ihash(interests)
    wanted = ", ".join([*interests["tags"], *[f'"{k}"' for k in interests["keywords"]]])
    done = 0
    for it in pending(con, profile, today)[:min(limit, room)]:
        row = store.notice(con, it["id"])
        body = re.sub(r"\s+", " ", (row["body"] or ""))[:600] if row else ""
        try:
            out = chat(SYSTEM, f"[학생의 관심사]\n{wanted}\n\n[공지 제목]\n{it['title']}\n\n[본문 앞부분]\n{body}")
        except Exception:                        # noqa: BLE001 — LLM 이 실패하면 그 공지는 키워드 판정 그대로
            break
        m = re.search(r"(높음|중간|낮음)\s*[-:–]?\s*(.*)", out or "")
        if not m:
            continue
        store.put_llm_grade(con, it["id"], ih, GRADE[m.group(1)], m.group(2).strip()[:60] or None)
        done += 1
    if done:
        store.set_meta(con, "llm_day", json.dumps({"date": today.isoformat(), "count": _day(con, today) + done}))
        store.touch(con)
    return done
