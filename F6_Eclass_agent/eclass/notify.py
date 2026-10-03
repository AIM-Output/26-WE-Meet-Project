"""알림 — 과제 마감 알림 시점 계산과 배달 (F6-D2 · R40~R44). 표준 라이브러리만.

배달 = 알림 센터(헤더 종)에 한 줄. 알림 표는 F1 이 처음 만들었고, 대시보드 백엔드가 push(...) 로 넘겨준다
(이 폴더는 F1 을 모른다). 따로 도는 스케줄러가 없다 — 백엔드가 상태를 부를 때(1분마다) 지난 시점을 한꺼번에 계산한다.
그래서 PC 가 꺼져 있던 동안의 알림도 켤 때 나오고, 예정보다 60분 넘게 늦은 것은 '놓친 알림'이 된다.

규칙
    d3 · d1   마감 3·1일 전 09:00                          'D-3 · 3주차 실습 과제'
    d0        마감 당일 09:00 — 마감이 09:00 이전이면 마감 3시간 전 (F6-R41)   '오늘 23:59 마감 · …'
    - 00:00 마감은 전날 밤으로 본다 ('10월 4일 자정까지' = 10/5 00:00) → D-3·D-1·당일이 모두 하루 당겨진다
    - 제출 완료·내가 체크함·사라진 과제는 남은 알림을 만들지 않는다 (F6-R44)
    - 알림 시점이 과제를 처음 본 때(마감이 바뀌었으면 바뀐 때)보다 앞이면 만들지 않는다 — 지난 알림을 쏟아내지 않는다
    - 마감이 지났으면 만들지 않는다
    - id 에 (과제, 코드, 울릴 시각)을 넣어 중복되지 않는다. 마감이 바뀌면 새 시각으로 다시 만든다
그 밖에
    새 과제      수집에서 새로 본 과제 — 하루치를 한 줄로 묶는다 ('새 과제 3건', F6-R42)
    마감 변경    'kind=change' (F6-R22·R43)
    수집 실패    로그인 필요(코드 2) · 연속 3회 실패 — 실패가 이어지는 동안 한 번씩 (F6-R13·R15·R43)
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from typing import Callable, Optional

from . import config as C
from . import runs as R
from . import service, store

# push(nid, kind, ref_id, title, body, href, fire_at, missed, upsert) -> 새로 넣었으면 True
Push = Callable[..., bool]

WEEKDAYS = "월화수목금토일"
LABEL = {"d3": "D-3", "d1": "D-1", "d0": "당일 아침"}


# ---------------------------------------------------------------- 설정

def settings(con: sqlite3.Connection) -> dict:
    s = store.get_json(con, "notify_settings", {}) or {}
    rem = [c for c in (s.get("reminders") if isinstance(s.get("reminders"), list) else C.DEFAULT_REMINDERS)
           if c in C.REMINDER_CHOICES]
    return {"reminders": rem, "alertTime": C.ALERT_TIME, "earlyDueHours": C.EARLY_DUE_HOURS,
            "setAt": s.get("setAt"), "choices": [{"code": c, "label": LABEL[c]} for c in C.REMINDER_CHOICES]}


def save_settings(con: sqlite3.Connection, reminders: list[str], now: Optional[datetime] = None) -> dict:
    """켤 시점을 저장한다. 켠 시각(setAt)보다 앞선 알림은 만들지 않는다 — 방금 켠 D-3 이 지난 것까지 쏟아내지 않게."""
    bad = [c for c in reminders if c not in C.REMINDER_CHOICES]
    if bad:
        raise service.Invalid(f"알 수 없는 알림 시점: {', '.join(bad)}")
    store.set_json(con, "notify_settings", {"reminders": [c for c in C.REMINDER_CHOICES if c in reminders],
                                            "setAt": (now or datetime.now()).isoformat(timespec="seconds")})
    return settings(con)


# ---------------------------------------------------------------- 시점

def _at(day: date) -> datetime:
    h, m = (int(x) for x in C.ALERT_TIME.split(":"))
    return datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)


def _when(due: datetime) -> str:
    """'10/4(일) 23:59' — 00:00 마감은 전날 '24:00' 으로 (화면·캘린더와 같은 규칙)."""
    if (due.hour, due.minute) == (0, 0):
        d = due - timedelta(days=1)
        return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]}) 24:00"
    return f"{due.month}/{due.day}({WEEKDAYS[due.weekday()]}) {due:%H:%M}"


def due_day(due: datetime) -> date:
    """마감이 속한 날. 00:00 마감은 전날 밤으로 본다 — '10월 4일 자정까지'가 e클래스에는 10/5 00:00 으로 적힌다(2026-09-30 실측)."""
    return (due - timedelta(minutes=1)).date() if (due.hour, due.minute) == (0, 0) else due.date()


def fire_times(due: datetime, name: str, codes: list[str]) -> list[tuple[str, datetime, str]]:
    """켜진 알림 시점마다 (코드, 울릴 시각, 제목)."""
    day = due_day(due)
    out = []
    for code in codes:
        if code in ("d3", "d1"):
            n = int(code[1:])
            out.append((code, _at(day - timedelta(days=n)), f"D-{n} · {name}"))
        elif code == "d0":
            morning = _at(day)
            if day != due.date():                   # 자정 마감 → 그날 아침에 '오늘 자정 마감'
                out.append((code, morning, f"오늘 자정 마감 · {name}"))
            elif due <= morning:                    # 09:00 이전 마감 → 3시간 전 (F6-R41)
                out.append((code, due - timedelta(hours=C.EARLY_DUE_HOURS), f"{C.EARLY_DUE_HOURS}시간 후 마감 · {name}"))
            else:
                out.append((code, morning, f"오늘 {due:%H:%M} 마감 · {name}"))
    return out


def _parse(ts: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts) if ts else None
    except ValueError:
        return None


def planned(con: sqlite3.Connection, now: Optional[datetime] = None) -> list[dict]:
    """앞으로 울릴 알림 (상세 창·명령줄 확인용)."""
    now = now or datetime.now()
    codes = settings(con)["reminders"]
    out = []
    for r in con.execute("SELECT * FROM items WHERE removed_at IS NULL AND due != '' AND submitted = 0 AND user_done = 0"):
        due = service.parse_due(r["due"])
        if not due or due < now:
            continue
        for code, fire, title in fire_times(due, r["name"], codes):
            if fire > now:
                out.append({"id": r["id"], "code": code, "at": fire.isoformat(timespec="seconds"), "title": title})
    return sorted(out, key=lambda x: x["at"])


# ---------------------------------------------------------------- 배달

def deliver(con: sqlite3.Connection, push: Optional[Push], now: Optional[datetime] = None,
            run_list: Optional[list[dict]] = None) -> int:
    """때가 된 알림을 push 로 넣는다. 넣은 개수. push 가 없으면(F1 없음) 아무것도 하지 않는다."""
    if push is None:
        return 0
    now = now or datetime.now()
    n = _deliver_changes(con, push, now)
    n += _deliver_reminders(con, push, now)
    n += _deliver_failures(push, run_list if run_list is not None else R.list_runs(30))
    return n


def _deliver_reminders(con: sqlite3.Connection, push: Push, now: datetime) -> int:
    st = settings(con)
    set_at = _parse(st["setAt"])
    added = 0
    for r in con.execute("SELECT * FROM items WHERE removed_at IS NULL AND due != '' AND submitted = 0 AND user_done = 0"):
        due = service.parse_due(r["due"])
        if not due or now > due:
            continue
        gate = max(t for t in (_parse(r["first_seen"]), _parse(r["changed_at"]), set_at, datetime.min) if t)
        parts = service.split_course(r["course"])
        for code, fire, title in fire_times(due, r["name"], st["reminders"]):
            if fire > now or fire < gate:
                continue
            nid = f"dl:{r['id'][3:]}:{code}:{fire:%Y%m%d%H%M}"
            body = f"{parts['short'] or r['course']} · {r['type']} · {_when(due)} 마감"
            missed = (now - fire) > timedelta(minutes=C.MISSED_AFTER_MIN)
            if push(nid, "deadline", r["id"], title, body, f"/?event={r['id']}", fire, missed, False):
                added += 1
    return added


def _deliver_changes(con: sqlite3.Connection, push: Push, now: datetime) -> int:
    rows = con.execute(
        "SELECT c.*, i.name, i.course, i.type FROM changes c JOIN items i ON i.id = c.item_id "
        "WHERE c.notified = 0 AND c.kind IN ('new', 'due') ORDER BY c.seq").fetchall()
    if not rows:
        return 0
    added = 0
    seqs = []
    new_days: set[str] = set()
    for c in rows:
        seqs.append(c["seq"])
        if c["kind"] == "new":
            new_days.add(c["at"][:10])
            continue
        before = (json.loads(c["before"]) or {}).get("due") if c["before"] else None
        after = (json.loads(c["after"]) or {}).get("due") if c["after"] else None
        b, a = service.parse_due(before), service.parse_due(after)
        if not (b and a):
            continue
        word = "연장" if a > b else "앞당겨짐"
        if push(f"dl-chg:{c['item_id'][3:]}:{a:%Y%m%d%H%M}", "change", c["item_id"], f"마감 {word} · {c['name']}",
                f"{_when(b)} → {_when(a)}", f"/?event={c['item_id']}", _parse(c["at"]), False, False):
            added += 1
    for day in sorted(new_days):                   # 하루치 묶음 — 같은 날 새로 보이면 그 줄을 고쳐 쓴다(읽기 전이면)
        # 처음 볼 때 이미 끝난 것(제출·시청 완료, 마감 지남)은 '새 과제'로 알리지 않는다 — 예: 지난 주차 동영상을 처음 들여올 때
        names = [r["name"] for r in con.execute(
            "SELECT i.name FROM changes c JOIN items i ON i.id = c.item_id "
            "WHERE c.kind = 'new' AND substr(c.at, 1, 10) = ? AND i.baseline = 0 AND i.submitted = 0 "
            "AND (i.due = '' OR i.due >= substr(c.at, 1, 10) || ' ' || substr(c.at, 12, 5)) ORDER BY c.seq", (day,))]
        if not names:
            continue
        body = ", ".join(names[:3]) + (f" 외 {len(names) - 3}건" if len(names) > 3 else "")
        if push(f"dl-new:{day}", "deadline", None, f"새 과제 {len(names)}건", body, "/assignments?tab=open",
                now if day == now.date().isoformat() else _parse(f"{day}T23:59:00"), False, True):
            added += 1
    con.executemany("UPDATE changes SET notified = 1 WHERE seq = ?", [(s,) for s in seqs])
    return added


def _deliver_failures(push: Push, run_list: list[dict]) -> int:
    if not run_list:
        return 0
    s = R.failure_streak(run_list)
    if s["count"] == 0 or not s["since"]:
        return 0
    added = 0
    ok = f" · 마지막 성공 {s['lastOkAt'][:16].replace('T', ' ')}" if s["lastOkAt"] else ""
    if s["lastCode"] == C.EXIT_LOGIN:
        if push(f"dl-sys:login:{s['since']}", "system", None, "e클래스 로그인이 필요합니다",
                f"자동 재로그인이 되지 않았습니다 — 수집 원천에서 '로그인 창 열기'로 한 번 로그인하세요{ok}",
                "/settings/sources", None, False, False):
            added += 1
    if s["count"] >= C.FAILURE_STREAK_WARN:
        if push(f"dl-sys:streak:{s['since']}", "system", None, f"e클래스 수집이 {s['count']}회 연속 실패했습니다",
                f"{s['lastError'] or '원인 불명'}{ok}", "/settings/sources", None, False, False):
            added += 1
    return added
