"""알림 — 대시보드 알림 센터(F1 notifications 표)로 넣는다. 백엔드가 /api/status(1분마다)에서 deliver 를 부른다.

  - 새 공지(첫 수집 = 기준선 이후)가 해당·확인 필요면 즉시 (F11-R70) · 비해당·마감·대상 아님은 알리지 않는다
    한 번에 BUNDLE_OVER 건보다 많으면 한 줄로 묶는다 ('새 장학 공지 7건 — 해당 2 · 확인 필요 5')
  - 신청 마감 D-3 · D-1 (09:00 이후 첫 배달) — 초안 대기·승인 건만 (F11-R71)
  - 같은 공지로 두 번 알리지 않는다 — user_state.alerted_at · deadline_alerts (F11-R72)
  - 상시 장학 목록(catalog)은 알리지 않는다 — 공지가 아니라 늘 있는 안내다
알림을 누르면 그 공지 상세(/scholarships?item=…)로 간다 (F11-R73).
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Callable, Optional
from urllib.parse import quote

from . import config as C
from . import service, store

Push = Callable[[str, str, str, str, Optional[str]], None]    # (nid, ref_id, title, body, href)


def _href(nid: str) -> str:
    return f"/scholarships?item={quote(nid, safe='')}"


def deliver(con: sqlite3.Connection, profile: Optional[dict], push: Push, now: Optional[datetime] = None) -> int:
    now = now or datetime.now()
    baseline = store.get_meta(con, "baseline_at")
    if not baseline:
        return 0
    sent = 0
    items = service.evaluate(con, profile, now.date())
    states = store.states(con)
    fresh = [i for i in items if i["kind"] == "notice" and (i["firstSeen"] or "") > baseline
             and not (states.get(i["id"]) and states[i["id"]]["alerted_at"])]
    hits = [i for i in fresh if i["verdict"] in ("eligible", "needs_review")]
    stamp = store.now_iso()
    for i in fresh:
        store.put_state(con, i["id"], alerted_at=stamp)
    if len(hits) > C.BUNDLE_OVER:
        e = sum(1 for i in hits if i["verdict"] == "eligible")
        push(f"sch:new:{stamp}", "bundle", f"새 장학 공지 {len(hits)}건", f"해당 {e} · 확인 필요 {len(hits) - e}", "/scholarships")
        sent += 1
    else:
        for i in hits:
            dd = f" · D-{i['daysLeft']}" if i["daysLeft"] is not None and i["daysLeft"] >= 0 else ""
            why = f" · {i['hint']}" if i.get("hint") else ""
            push(f"sch:new:{i['id']}", i["id"], f"[{i['label']}] {i['title'][:60]}", f"{i['org'] or ''}{dd}{why}".strip(" ·"),
                 _href(i["id"]))
            sent += 1
    h, m = (int(x) for x in C.ALERT_TIME.split(":"))
    if (now.hour, now.minute) >= (h, m):
        for i in items:
            if i["progress"] not in ("draft", "approved") or i["daysLeft"] not in C.DEADLINE_DAYS:
                continue
            st = states.get(i["id"])
            done = json.loads(st["deadline_alerts"]) if st and st["deadline_alerts"] else []
            tag = f"{i['deadline'][:10]}:d{i['daysLeft']}"
            if tag in done:
                continue
            push(f"sch:dl:{i['id']}:{tag}", i["id"], f"장학 마감 D-{i['daysLeft']} · {i['title'][:50]}",
                 f"{i['progressLabel']} — 신청은 본인이 직접 합니다", _href(i["id"]))
            store.put_state(con, i["id"], deadline_alerts=json.dumps(done + [tag]))
            sent += 1
    return sent
