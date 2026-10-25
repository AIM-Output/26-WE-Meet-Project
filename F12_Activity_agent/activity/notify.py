"""알림 — 대시보드 알림 센터(F1 notifications 표, kind=opportunity)로 넣는다. 백엔드가 /api/status(1분마다)에서 deliver 를 부른다.

  - 새 공지(첫 수집 = 기준선 이후) 중 **'내 관심사'만 즉시** (F12-R30) · 관련 있음·관심 밖·끝난 공지는 알리지 않는다
  - 즉시 알림은 **하루 5건까지**, 넘으면 그날 묶음 한 줄 '관심 기회 N건이 더 있습니다'를 고쳐 쓴다 (F12-R31)
  - 마감 D-3 — 담아 둔 것만 · 초안 대기·제출 예정은 D-3·D-1 (09:00 이후 첫 배달, F12-R32)
  - 같은 공지로 두 번 알리지 않는다 — user_state.alerted_at · deadline_alerts (F12-R33)
  - **관심사가 비어 있으면 알리지 않는다** (F12-R14) — 그동안 들어온 글도 '본 것'으로 표시해 관심사를 고른 순간 알림이 쏟아지지 않게
알림을 누르면 그 공지 상세(/opportunities?item=…)로 간다.
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import quote

from . import config as C
from . import interests as I
from . import service, store

Push = Callable[..., None]    # (nid, ref_id, title, body, href, upsert=False)


def _href(nid: str) -> str:
    return f"/opportunities?item={quote(nid, safe='')}"


def deliver(con: sqlite3.Connection, profile: Optional[dict], push: Push, now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    baseline = store.get_meta(con, "baseline_at")
    if not baseline:
        return 0
    sent = 0
    items = service.evaluate(con, profile, now.date())
    states = store.states(con)
    fresh = [i for i in items if (i["firstSeen"] or "") > baseline and not (states.get(i["id"]) and states[i["id"]]["alerted_at"])]
    on = I.is_set(I.from_profile(profile))
    hits = [i for i in fresh if on and i["grade"] == "match" and i["status"] == "open"]
    stamp = store.now_iso()
    for i in fresh:
        store.put_state(con, i["id"], alerted_at=stamp)
    day = now.date().isoformat()
    count = store.loads(store.get_meta(con, "alert_day"), {}) or {}
    if count.get("date") != day:
        count = {"date": day, "count": 0, "bundled": 0}
    for i in hits:
        if count["count"] < C.DAILY_ALERT_MAX:
            dd = f" · D-{i['daysLeft']}" if i["daysLeft"] is not None and i["daysLeft"] >= 0 else ""
            why = ", ".join(i["chips"][:3])
            push(f"opp:new:{i['id']}", i["id"], f"[{i['categoryLabel'] or '대외활동'}] {i['title'][:60]}",
                 f"{i['org'] or ''}{dd}{f' · {why}' if why else ''}".strip(" ·"), _href(i["id"]))
            count["count"] += 1
        else:
            count["bundled"] += 1
        sent += 1
    if count.get("bundled"):
        push(f"opp:bundle:{day}", "bundle", f"관심 기회 {count['bundled']}건이 더 있습니다",
             f"오늘 내 관심사에 맞는 새 공지가 {C.DAILY_ALERT_MAX}건을 넘었습니다 — 목록에서 모아 보세요", "/opportunities",
             upsert=True)
    store.set_meta(con, "alert_day", json.dumps(count))
    h, m = (int(x) for x in C.ALERT_TIME.split(":"))
    if (now.hour, now.minute) >= (h, m):
        for i in items:
            days = C.SAVED_DEADLINE_DAYS if i["progress"] == "saved" else (
                C.DRAFT_DEADLINE_DAYS if i["progress"] in ("draft", "approved") else ())
            if i["daysLeft"] not in days:
                continue
            st = states.get(i["id"])
            done = json.loads(st["deadline_alerts"]) if st and st["deadline_alerts"] else []
            tag = f"{i['deadline'][:10]}:d{i['daysLeft']}"
            if tag in done:
                continue
            push(f"opp:dl:{i['id']}:{tag}", i["id"], f"신청 마감 D-{i['daysLeft']} · {i['title'][:50]}",
                 f"{i['progressLabel']} — 신청은 본인이 직접 합니다", _href(i["id"]))
            store.put_state(con, i["id"], deadline_alerts=json.dumps(done + [tag]))
            sent += 1
    return sent
