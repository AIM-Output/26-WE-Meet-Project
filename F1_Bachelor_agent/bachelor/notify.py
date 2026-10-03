"""알림 — 학사 일정의 알림 시점을 계산해 때가 된 것을 '배달'한다 (F1-R30~R36, F1 5절).

배달 = notifications 표에 한 줄 넣기. 헤더 종 아이콘이 그 표를 읽는다 (G2: PC 의 앱 내 알림까지).
따로 도는 스케줄러가 없다 — 대시보드가 알림 목록을 부를 때(deliver_due) 지난 시점을 한꺼번에 계산한다.
그래서 PC 가 꺼져 있던 동안의 알림도 다음에 켤 때 빠짐없이 나온다(F1-R34). 예정보다 60분 넘게 늦게
배달된 알림은 missed=1 → '놓친 알림' 으로 묶여 보인다.

규칙 (기준 시각 09:00 — /settings/notifications 에서 바꿈)
    d7/d3/d1  시작 7·3·1일 전 09:00                 '등록금 납부 D-3'
    end1      기간형의 종료 전날 09:00               '내일 마감 · 등록금 납부' (끝 시각이 있으면 '내일 16:00 마감')
    m30       시각이 있는 일정의 시작 30분 전         '30분 후 시작 · 수강신청'
    - 알림 시점이 일정을 처음 본 시각(또는 승인·담기·알림을 켠 시각)보다 앞이면 만들지 않는다
      (공지가 D-2 에 올라오면 D-1 알림만 — 5절 '이미 지난 시점의 알림은 만들지 않는다')
    - id 에 (일정, 코드, 울릴 시각)을 넣어 재동기화해도 중복되지 않는다. 날짜가 바뀌면 새 시각으로 다시 만든다.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import Optional

from . import config as C
from .service import list_events
from .store import get_meta, now_iso


def _alert_time(con: sqlite3.Connection) -> tuple[int, int]:
    raw = get_meta(con, "alert_time", C.ALERT_TIME) or C.ALERT_TIME
    try:
        h, m = raw.split(":")
        return int(h), int(m)
    except ValueError:
        return 9, 0


def _last_day(e: dict) -> date:
    """일정의 마지막 날(포함)."""
    s = date.fromisoformat(e["start"][:10])
    if not e["end"]:
        return s
    end = e["end"]
    if e["allDay"]:
        return date.fromisoformat(end[:10]) - timedelta(days=1)
    d = date.fromisoformat(end[:10])
    return d - timedelta(days=1) if end[11:16] == "00:00" and d > s else d


def fire_times(e: dict, at: tuple[int, int]) -> list[tuple[str, datetime, str]]:
    """켜진 알림 시점마다 (코드, 울릴 시각, 제목)."""
    if not e.get("start"):
        return []
    s_day = date.fromisoformat(e["start"][:10])
    hh, mm = at
    out = []
    for r in e["reminders"]:
        if not r["enabled"]:
            continue
        code = r["code"]
        if code in ("d7", "d3", "d1"):
            n = int(code[1:])
            out.append((code, datetime.combine(s_day - timedelta(days=n), datetime.min.time()).replace(hour=hh, minute=mm),
                        f"D-{n} · {e['title']}"))
        elif code == "end1":
            last = _last_day(e)
            if last > s_day:
                when = f"내일 {e['endTime']} 마감" if e.get("endTime") else "내일 마감"
                if not e["allDay"] and e["end"] and e["end"][11:16] not in ("", "00:00"):
                    when = f"내일 {e['end'][11:16]} 마감"
                out.append((code, datetime.combine(last - timedelta(days=1), datetime.min.time()).replace(hour=hh, minute=mm),
                            f"{when} · {e['title']}"))
        elif code == "m30" and not e["allDay"]:
            start = datetime.fromisoformat(e["start"])
            out.append((code, start - timedelta(minutes=30), f"30분 후 시작 · {e['title']}"))
    return out


def _parse(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        return None


def _when_text(e: dict) -> str:
    s = e["start"]
    t = f"{int(s[5:7])}/{int(s[8:10])}"
    if not e["allDay"]:
        t += f" {s[11:16]}"
    if e["end"]:
        last = _last_day(e)
        if last.isoformat() != s[:10]:
            t += f" ~ {last.month}/{last.day}"
    return t


def deliver_due(con: sqlite3.Connection, profile: Optional[dict], now: Optional[datetime] = None) -> int:
    """때가 된 알림을 notifications 에 넣는다. 넣은 개수."""
    now = now or datetime.now()
    at = _alert_time(con)
    profile_since = _parse((profile or {}).get("updatedAt"))
    added = 0
    for e in list_events(con, profile, now.date()):
        if not e["onCalendar"]:
            continue
        gate = _parse(e["notifySince"]) or now
        if profile_since and profile_since > gate:
            gate = profile_since          # 프로필을 바꿔 새로 '내 해당'이 된 일정의 지난 알림은 쏟아내지 않는다
        opts = {r["code"]: r for r in e["reminders"]}
        for code, fire, title in fire_times(e, at):
            g = gate
            set_at = _parse(opts.get(code, {}).get("setAt"))
            if set_at and set_at > g:
                g = set_at
            if fire > now or fire < g:
                continue
            nid = f"rem:{e['id']}:{code}:{fire:%Y%m%d%H%M}"
            missed = (now - fire) > timedelta(minutes=C.MISSED_AFTER_MIN)
            cur = con.execute(
                "INSERT OR IGNORE INTO notifications(id, kind, ref_id, title, body, fire_at, delivered_at, missed, href) "
                "VALUES (?, 'academic', ?, ?, ?, ?, ?, ?, ?)",
                (nid, e["id"], title, f"{_when_text(e)} · {e['typeLabel']}", fire.isoformat(timespec="seconds"),
                 now.isoformat(timespec="seconds"), int(missed), f"/academic?event={e['id']}"))
            added += cur.rowcount
    return added


def push(con: sqlite3.Connection, kind: str, ref_id: Optional[str], title: str, body: str = "", href: Optional[str] = None,
         nid: Optional[str] = None, fire_at: Optional[datetime] = None, missed: bool = False, upsert: bool = False) -> bool:
    """다른 기능이 알림 센터에 한 줄 바로 넣는다 (F3 출결 경고 · F6 과제 마감 등). 같은 id 면 무시.
    fire_at = 울릴 예정이던 시각(없으면 지금) · missed = 늦게 배달됨('놓친 알림') ·
    upsert = 같은 id 가 아직 안 읽혔으면 제목·본문을 고쳐 쓴다(F6 '새 과제 N건' 하루치 묶음). 읽은 뒤면 새 줄로."""
    now = datetime.now()
    nid = nid or f"{kind}:{ref_id}:{now:%Y%m%d%H%M%S}"
    stamp = now.isoformat(timespec="seconds")
    if upsert:
        row = con.execute("SELECT read_at, title, body FROM notifications WHERE id = ?", (nid,)).fetchone()
        if row and row["title"] == title and row["body"] == body:
            return False
        if row and not row["read_at"]:
            con.execute("UPDATE notifications SET title = ?, body = ?, href = ?, delivered_at = ? WHERE id = ?",
                        (title, body, href, stamp, nid))
            return True
        if row:
            nid = f"{nid}:{now:%H%M%S}"
    cur = con.execute(
        "INSERT OR IGNORE INTO notifications(id, kind, ref_id, title, body, fire_at, delivered_at, missed, href) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (nid, kind, ref_id, title, body, (fire_at or now).isoformat(timespec="seconds"), stamp, int(missed), href))
    return cur.rowcount > 0


def list_notifications(con: sqlite3.Connection, profile: Optional[dict], unread_only: bool = False,
                       limit: int = 60) -> dict:
    """GET /api/notifications — 먼저 배달할 것을 배달하고, 최근 알림 목록(최신 순)과 안 읽은 수."""
    deliver_due(con, profile)
    hidden = {r["id"] for r in con.execute("SELECT id FROM events WHERE user_status = 'hidden'")}
    rows = con.execute("SELECT * FROM notifications ORDER BY fire_at DESC, id LIMIT ?", (limit * 2,)).fetchall()
    items = []
    for r in rows:
        if r["ref_id"] in hidden:
            continue
        if unread_only and r["read_at"]:
            continue
        items.append({"id": r["id"], "kind": r["kind"], "refId": r["ref_id"], "title": r["title"], "body": r["body"],
                      "at": r["fire_at"], "deliveredAt": r["delivered_at"], "read": bool(r["read_at"]),
                      "missed": bool(r["missed"]), "href": r["href"]})
        if len(items) >= limit:
            break
    unread = sum(1 for r in rows if not r["read_at"] and r["ref_id"] not in hidden)
    return {"items": items, "unread": unread, "bundleOver": C.BUNDLE_OVER}


def mark_read(con: sqlite3.Connection, nid: str) -> bool:
    cur = con.execute("UPDATE notifications SET read_at = ? WHERE id = ? AND read_at IS NULL", (now_iso(), nid))
    return cur.rowcount > 0


def mark_all_read(con: sqlite3.Connection) -> int:
    return con.execute("UPDATE notifications SET read_at = ? WHERE read_at IS NULL", (now_iso(),)).rowcount


def upcoming(con: sqlite3.Connection, profile: Optional[dict], days: int = 3, today: Optional[date] = None) -> list[dict]:
    """오늘부터 days 일 안에 시작하거나 끝나는 내 학사 일정 — F10 아침 브리핑이 쓴다 (F1-R35).
    한 달짜리 기간의 한가운데처럼 '진행 중이지만 곧 끝나지 않는' 일정은 넣지 않는다."""
    today = today or date.today()
    until = today + timedelta(days=days)
    out = []
    for e in list_events(con, profile, today):
        if not e["onCalendar"]:
            continue
        s = date.fromisoformat(e["start"][:10])
        last = _last_day(e)
        if today <= s <= until or today <= last <= until:
            out.append({**e, "daysLeft": (s - today).days, "endsIn": (last - today).days})
    return out
