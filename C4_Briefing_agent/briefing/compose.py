"""재료 → 브리핑 섹션 (순수 함수 — 파일·DB 를 열지 않는다, fastapi 도 부르지 않는다).

재료(ing)는 각 기능이 브리핑용으로 내놓은 값 그대로다. 없는 재료는 None — 그 섹션만 빠진다(F10 9절 '있는 섹션만').
    classes       F3 오늘 수업 + 위험 과목     {classes: [{courseId, name, start, end, room, state, level, levelLabel}], totals: {risky}}
    events        C1 합친 캘린더(오늘 ~ D-3)   [CalEvent] — 내 일정·할 일·학사·시험·과제 마감(kind=deadline)
    priority      F7 먼저 할 것                {items: [{id, title, courseShort, kindLabel, reason}], totalText, overdue}
    academic      F1 D-3 이내 학사 일정         [{id, title, start, daysLeft, reminders: [{enabled}]}]
    study         F5 오늘 공부 분량             {blocks: [{course, text, done, examId}], nextExam: {examId, course, typeLabel, dday, ddayLabel}}
    blocks        F8 오늘 학습 블록             {blocks: [{id, title, start, end, done, href, taskType}]}
    scholarships  F11 마감 임박 장학            [{id, title, daysLeft}]
    activities    F12 담아 둔 것의 마감         [{id, title, daysLeft}]
    alerts        알림 센터 안 읽은 알림        [{id, kind, refId, title, body, href, deliveredAt}]

**숫자는 다시 계산하지 않는다**(F10-R17). 여기서 하는 일은 고르고(오늘·D-3), 정렬하고, 한 줄 글로 옮기는 것뿐이다.
D-n 은 화면의 D-day 칩과 같은 '달력 날짜 차이'로 센다. 00:00 마감은 전날 밤 마감이다(F6 자정 규칙).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Optional

from . import config as C

WEEKDAY_KO = "월화수목금토일"

Item = dict[str, Any]


# ---------------------------------------------------------------- 날짜·글

def _dt(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s[:19] if len(s) > 10 else s)
    except ValueError:
        return None


def due_day(due: datetime) -> tuple[date, str]:
    """마감의 '날짜'와 보일 시각 — 00:00 마감은 전날 24:00 (F6 자정 규칙)."""
    if due.hour == 0 and due.minute == 0:
        return (due - timedelta(days=1)).date(), "24:00"
    return due.date(), f"{due:%H:%M}"


def day_word(d: date, today: date) -> str:
    n = (d - today).days
    if n == 0:
        return "오늘"
    if n == 1:
        return "내일"
    return f"{d.month}/{d.day}({WEEKDAY_KO[d.weekday()]})"


def _hm(s: Optional[str]) -> str:
    """'2026-10-25T09:00:00' · '09:00' → '09:00'."""
    if not s:
        return ""
    return s[11:16] if len(s) > 10 else s[:5]


def _on_day(ev: dict, today: date) -> bool:
    """그날에 걸치는가 — 종일 일정의 end 는 exclusive (C1-R14)."""
    s = _dt(ev.get("start"))
    if s is None:
        return False
    if ev.get("allDay"):
        e = _dt(ev.get("end")) or (s + timedelta(days=1))
        return s.date() <= today < e.date()
    e = _dt(ev.get("end"))
    if e and e.date() > s.date():
        return s.date() <= today <= e.date()
    return s.date() == today


def _props(ev: dict) -> dict:
    return ev.get("extendedProps") or {}


# ---------------------------------------------------------------- 섹션별

def _attention(ing: dict) -> list[Item]:
    """F3-R35 위험·초과 과목(브리핑 상단) · F7 놓친 마감."""
    out: list[Item] = []
    risky = ((ing.get("classes") or {}).get("totals") or {}).get("risky") or []
    for c in risky:
        over = c.get("level") == "over"
        spare = c.get("spareSessions")
        out.append({
            "text": f"{c.get('name')} 출결 {c.get('levelLabel') or ('초과' if over else '위험')}",
            "sub": "결석이 한도를 넘었습니다" if over else (f"남은 결석 여유 {spare}회" if spare else "한 번 더 결석하면 한도를 넘습니다"),
            "href": f"/attendance?course={c.get('id')}", "tone": "danger", "tag": "출결",
        })
    overdue = (ing.get("priority") or {}).get("overdue") or 0
    if overdue:
        out.append({"text": f"놓친 마감 {overdue}건 · 미제출", "sub": "2주 안에 지난 것",
                    "href": "/assignments?sort=priority", "tone": "danger", "tag": "과제"})
    return out


def _classes(ing: dict) -> list[Item]:
    """F10-R10 오늘 수업 — 시간 순, 강의실 포함. 휴강도 보여 준다(그 시간이 비었다는 뜻이니까)."""
    out: list[Item] = []
    for s in (ing.get("classes") or {}).get("classes") or []:
        canceled = s.get("state") == "canceled"
        risky = s.get("level") in ("danger", "over")
        out.append({
            "time": _hm(s.get("start")),
            "text": f"{_hm(s.get('start'))} {s.get('name')}",
            "sub": "휴강" if canceled else (" · ".join(x for x in (s.get("room") or "", f"출결 {s.get('levelLabel')}" if risky else "") if x) or None),
            "href": f"/?view=week&event={s['id']}" if s.get("id") else "/?view=week",    # 캘린더 주 보기 + 그 회차 상세
            "tone": "muted" if canceled else ("danger" if risky else None),
        })
    return sorted(out, key=lambda x: x["time"])


def _events(ing: dict, today: date) -> list[Item]:
    """F10-R11 오늘 일정 — 내 일정 · 할 일 · 학습 블록(F8) · 오늘 공부(F5) · 시험 · 그날의 학사 일정. 종일이 먼저, 그다음 시각 순."""
    out: list[Item] = []
    for ev in ing.get("events") or []:
        p = _props(ev)
        kind = p.get("kind")
        if kind not in ("user", "academic", "exam") or not _on_day(ev, today):
            continue
        if kind == "user" and p.get("done"):
            continue                                        # 끝낸 할 일
        all_day = bool(ev.get("allDay")) or (kind == "exam" and p.get("timeUnknown"))
        t = "종일" if all_day else _hm(ev.get("start"))
        if kind == "academic":
            href, tag, tone = f"/academic?event={p.get('refId') or ev.get('id')}", "학사", None
        elif kind == "exam":
            href, tag, tone = p.get("href") or f"/exams?exam={p.get('examId') or ev.get('id')}", "시험", "danger"
        else:
            href, tag, tone = f"/?event={ev.get('id')}", ("할 일" if p.get("isTodo") else None), None
        out.append({"time": "" if all_day else t, "text": f"{t} {ev.get('title')}", "href": href, "tag": tag,
                    "tone": tone, "sub": p.get("place") or None})
    for b in (ing.get("blocks") or {}).get("blocks") or []:
        if b.get("done"):
            continue
        href = b.get("href") or (f"/?event={b['id']}" if b.get("taskType") not in ("study",) else "/exams")
        out.append({"time": b.get("start") or "", "text": f"{b.get('start')} {b.get('title')}", "href": href,
                    "tag": "학습 블록", "sub": f"~{b.get('end')}" if b.get("end") else None})
    for s in (ing.get("study") or {}).get("blocks") or []:
        if s.get("done"):
            continue
        out.append({"time": "", "text": f"오늘 공부 · {s.get('text')}",
                    "href": f"/exams?exam={s['examId']}" if s.get("examId") else "/exams", "tag": "시험 공부"})
    return sorted(out, key=lambda x: (x["time"] != "", x["time"]))


def _deadlines(ing: dict, now: datetime) -> list[Item]:
    """F10-R12 마감 임박(D-3) — 과제·퀴즈·동영상(F6, 제출·체크한 것 빼고) + 학사(F1-R35) + 장학(F11-R74)
    + 담아 둔 대외활동(F12-R34) + 시험(F5). 가까운 순."""
    today = now.date()
    rows: list[tuple[tuple, Item]] = []
    for ev in ing.get("events") or []:
        p = _props(ev)
        if p.get("kind") != "deadline" or p.get("done") or p.get("removed"):
            continue
        due = _dt(p.get("due") or ev.get("start"))
        if due is None or due < now:
            continue                                        # 지난 마감은 '주의'의 놓친 마감으로
        d, hm = due_day(due)
        n = (d - today).days
        if n > C.SOON_DAYS:
            continue
        rows.append(((n, hm), {
            "text": f"{day_word(d, today)} {hm} {ev.get('title')}",
            "sub": " · ".join(x for x in (p.get("courseShort") or "", p.get("type") or "") if x) or None,
            "href": f"/?event={ev.get('id')}", "tone": "danger" if n == 0 else ("warn" if n == 1 else None),
            "tag": "과제", "dday": n,
        }))
    for a in ing.get("academic") or []:
        if not any(r.get("enabled") for r in a.get("reminders") or []):
            continue                                        # 알림을 꺼 둔 것(휴업일·수업일수 등)은 빼고 — F1-R35 '알림 항목이 그대로'
        n, end = a.get("daysLeft"), a.get("endsIn")
        if n is not None and 1 <= n <= C.SOON_DAYS:         # 곧 시작 (오늘 시작하는 것은 '오늘 일정'에)
            text, d = f"D-{n} {a.get('title')}", n
        elif n is not None and n < 0 and end is not None and 0 <= end <= C.SOON_DAYS:
            # 이미 시작한 기간이 곧 끝난다 — '휴학 등록 8/18~10/28' 의 마감 (F1 notify.upcoming 이 '끝나는 것'도 준다)
            text, d = f"{'오늘' if end == 0 else f'D-{end}'} {a.get('title')} 마감", end
        else:
            continue
        rows.append(((d, "99:99"), {"text": text, "href": f"/academic?event={a.get('id')}",
                                     "tag": "학사", "dday": d, "tone": "danger" if d == 0 else ("warn" if d == 1 else None)}))
    nxt = (ing.get("study") or {}).get("nextExam")
    if nxt and nxt.get("dday") is not None and 1 <= nxt["dday"] <= C.SOON_DAYS:
        n = nxt["dday"]
        rows.append(((n, nxt.get("time") or "99:98"), {
            "text": f"D-{n} {nxt.get('course')} {nxt.get('typeLabel') or '시험'}",
            "sub": " · ".join(x for x in (nxt.get("time") or "", nxt.get("place") or "") if x) or None,
            "href": f"/exams?exam={nxt.get('examId')}", "tag": "시험", "dday": n, "tone": "warn"}))
    for key, tag, path in (("scholarships", "장학", "/scholarships"), ("activities", "대외활동", "/opportunities")):
        for x in ing.get(key) or []:
            n = x.get("daysLeft")
            if n is None or not 0 <= n <= C.SOON_DAYS:
                continue
            rows.append(((n, "99:99"), {
                "text": f"{'오늘 마감' if n == 0 else f'D-{n}'} {x.get('title')}",
                "sub": x.get("progress") or None, "href": f"{path}?item={x.get('id')}", "tag": tag, "dday": n,
                "tone": "danger" if n == 0 else ("warn" if n == 1 else None)}))
    rows.sort(key=lambda r: r[0])
    return [it for _, it in rows]


def _priority(ing: dict) -> tuple[list[Item], Optional[str]]:
    """F10-R13 먼저 할 것 — F7 상위 3건, 이유 한 줄과 함께. 순서는 F7 그대로."""
    p = ing.get("priority") or {}
    items = [{"text": f"{i}) {r.get('title')}", "sub": " · ".join(x for x in (r.get("courseShort") or "", r.get("reason") or "") if x),
              "href": f"/?event={r.get('id')}" if r.get("id") else "/assignments?sort=priority"}
             for i, r in enumerate((p.get("items") or [])[:C.TOP_N], 1)]
    return items, (f"합계 {p['totalText']}" if items and p.get("totalText") else None)


def _alerts(ing: dict, since: Optional[datetime]) -> list[Item]:
    """새 알림 — 알림 센터에서 since 이후 배달됐고 아직 안 읽은 것. 다른 섹션과 겹치는 D-n 알림은 뺀다."""
    out: list[Item] = []
    for n in ing.get("alerts") or []:
        if n.get("read") or n.get("kind") in C.ALERT_SKIP_KINDS:
            continue
        nid = str(n.get("id") or "")
        if nid.startswith(C.ALERT_SKIP_ID_PREFIX) or (n.get("kind") == "deadline" and n.get("refId")):
            continue
        at = _dt(n.get("deliveredAt") or n.get("at"))
        if since and at and at < since:
            continue
        out.append({"text": n.get("title") or "", "sub": n.get("body") or None, "href": n.get("href") or "/",
                    "tag": ALERT_TAGS.get(n.get("kind") or "", None), "at": (n.get("deliveredAt") or n.get("at")),
                    "tone": "danger" if n.get("kind") in ("attendance", "system") else None})
    return out


ALERT_TAGS = {"academic": "학사", "change": "마감 변경", "system": "시스템", "deadline": "과제", "opportunity": "대외활동",
              "scholarship": "장학", "attendance": "출결", "exam": "시험", "eclass": "e클래스"}


# ---------------------------------------------------------------- 묶기

def summary_of(counts: dict) -> str:
    """'수업 3 · 일정 2 · 마감 3 · 먼저 할 것 3' — 접힌 카드·알림 본문·로그용 규칙 한 줄 (LLM 아님)."""
    words = (("attention", "주의"), ("classes", "수업"), ("events", "일정"), ("deadlines", "마감"),
             ("priority", "먼저 할 것"), ("alerts", "새 알림"))
    parts = [f"{w} {counts[k]}" for k, w in words if counts.get(k)]
    return " · ".join(parts) if parts else C.ALL_EMPTY_TEXT


def build(ing: dict, now: datetime, alerts_since: Optional[datetime] = None) -> dict:
    """{sections, counts, summary, empty} — sections 는 보일 것만, 화면 순서대로."""
    today = now.date()
    pri_items, pri_footer = _priority(ing)
    lists: dict[str, list[Item]] = {
        "attention": _attention(ing),
        "classes": _classes(ing),
        "events": _events(ing, today),
        "deadlines": _deadlines(ing, now),
        "priority": pri_items,
        "alerts": _alerts(ing, alerts_since),
    }
    counts = {k: len(v) for k, v in lists.items()}
    counts["total"] = sum(counts.values())
    empty = counts["total"] == 0
    sections = []
    if not empty:
        for key in C.SECTION_ORDER:
            meta = C.SECTIONS[key]
            items = lists[key]
            if not items and meta["empty"] is None:
                continue                                    # 5절 섹션 규칙 — 비면 숨긴다 (마감 임박만 한 줄 남긴다)
            sections.append({
                "key": key, "label": meta["label"], "icon": meta["icon"], "link": meta["link"],
                "count": len(items), "items": items[:C.KEEP_LINES], "more": max(0, len(items) - C.KEEP_LINES),
                "empty": meta["empty"] if not items else None,
                "footer": pri_footer if key == "priority" else None,
            })
    return {"sections": sections, "counts": counts, "summary": summary_of(counts), "empty": empty,
            "emptyText": C.ALL_EMPTY_TEXT if empty else None}


def facts(built: dict) -> dict:
    """한 줄 요약(LLM)에 넘길 것 — 숫자와 제목 수준만 (F10 10절 프라이버시). 강의실·과목 메모·알림 본문은 넣지 않는다."""
    secs = {s["key"]: s for s in built["sections"]}

    def titles(key: str, n: int = 3) -> list[str]:
        return [it["text"] for it in (secs.get(key) or {}).get("items", [])[:n]]

    return {"counts": {k: v for k, v in built["counts"].items() if k != "total" and v},
            "attention": titles("attention"), "classes": titles("classes"), "deadlines": titles("deadlines"),
            "priority": titles("priority")}
