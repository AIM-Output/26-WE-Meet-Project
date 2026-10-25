"""브리핑 만들기·보여 주기 — 재료 모으기 · 정시/놓침 판정 · 수집 기다리기 · 스냅샷 저장 · 알림 1건 · 보관 정리.

따로 도는 스케줄러가 없다 — F1 알림 · F11 자동 수집과 같은 방식이다. 대시보드가 1분마다 부르는 /api/status 와
화면이 여는 GET /api/briefing/today 가 ensure_today 를 부르고, 그때 '오늘 브리핑을 만들 때가 됐는데 아직 없으면' 만든다.
    - 예정 시각(기본 08:00)이 지났고 오늘 것이 없다 → 만든다
        · 예정 시각에서 60분 안이면 scheduled, 그보다 늦으면(PC 가 꺼져 있었다) catchup = '놓친 브리핑' (F10-R02 · D2)
    - 그 순간 수집(e클래스·학사·장학·대외활동)이 돌고 있으면 끝날 때까지 기다린다 — 최대 5분, 넘으면 그대로 만든다 (9절)
    - 지난 날짜는 만들지 않는다(F10-R03). 하루 한 번 — 다시 만들기만 덮어쓴다(F10-R04)
    - 처음 만들 때 알림 센터에 1건(F10-R05). 다시 만들기는 알림을 새로 남기지 않는다
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from . import compose, headline, store
from . import config as C
from . import settings as S

_lock = threading.Lock()          # /api/status 와 /api/briefing/today 가 동시에 와도 하루 한 번만 만든다


class NotFound(Exception):
    pass


@dataclass
class Sources:
    """백엔드가 넘겨주는 재료 함수 — 없는 기능은 None(그 섹션만 빠진다). 모양은 compose.py 머리 주석."""
    classes: Optional[Callable[[], dict]] = None                  # F3 오늘 수업 + 위험 과목
    events: Optional[Callable[[str, str], list[dict]]] = None     # C1 합친 캘린더 (start, end)
    priority: Optional[Callable[[], dict]] = None                 # F7 먼저 할 것 3건
    academic: Optional[Callable[[], list[dict]]] = None           # F1 D-3 이내 학사 일정
    study: Optional[Callable[[], dict]] = None                    # F5 오늘 공부 분량 + 가장 가까운 시험
    blocks: Optional[Callable[[], dict]] = None                   # F8 오늘 학습 블록
    scholarships: Optional[Callable[[], list[dict]]] = None       # F11 마감 임박 장학
    activities: Optional[Callable[[], list[dict]]] = None         # F12 담아 둔 것의 마감
    alerts: Optional[Callable[[], list[dict]]] = None             # 알림 센터의 안 읽은 알림
    busy: Optional[Callable[[], list[str]]] = None                # 지금 수집 중인 기능 이름들
    notify: Optional[Callable[..., Any]] = None                   # 알림 센터에 한 줄 (nid, title, body, href, fire_at, missed)
    headline_chat: Optional[Callable[[str, str], str]] = None     # 한 줄 요약을 바꿔 끼울 때(테스트) — 없으면 LLM_MAIN_*


INGREDIENTS = ("classes", "events", "priority", "academic", "study", "blocks", "scholarships", "activities", "alerts")


# ---------------------------------------------------------------- 재료

def gather(src: Sources, now: datetime) -> tuple[dict, list[str]]:
    """재료를 모은다. 실패한 재료는 None 으로 두고 gaps 에 기능 이름을 적는다 — 브리핑은 있는 것으로 만든다."""
    ing: dict[str, Any] = {}
    gaps: list[str] = []
    start = now.date().isoformat()
    end = (now.date() + timedelta(days=C.SOON_DAYS + 1)).isoformat()
    for key in INGREDIENTS:
        fn = getattr(src, key)
        if fn is None:
            ing[key] = None
            continue
        try:
            ing[key] = fn(start, end) if key == "events" else fn()
        except Exception as e:                          # noqa: BLE001 — 기능 하나가 깨져도 브리핑은 나온다
            ing[key] = None
            gaps.append(C.SOURCE_NAMES.get(key, key))
            print(f"  브리핑 재료 {key} 를 읽지 못함: {type(e).__name__}: {str(e)[:120]}")
    return ing, gaps


def _busy(src: Sources) -> list[str]:
    if src.busy is None:
        return []
    try:
        return [x for x in src.busy() if x]
    except Exception:                                   # noqa: BLE001
        return []


# ---------------------------------------------------------------- 시각

def scheduled_at(settings: dict, day: date) -> datetime:
    h, m = (int(x) for x in settings["time"].split(":"))
    return datetime.combine(day, datetime.min.time()).replace(hour=h, minute=m)


def _alerts_since(con: sqlite3.Connection, now: datetime) -> datetime:
    """새 알림의 기준 — 지난 브리핑 이후, 그래도 최대 하루치."""
    floor = now - timedelta(hours=C.ALERT_LOOKBACK_HOURS)
    prev = store.latest_before(con, now.date().isoformat())
    if prev:
        try:
            return max(floor, datetime.fromisoformat(prev["generated_at"]))
        except ValueError:
            pass
    return floor


# ---------------------------------------------------------------- 화면 모양

def view(row: sqlite3.Row) -> dict:
    counts = store.loads(row["counts"], {})
    empty = not counts.get("total")
    return {
        "id": f"br:{row['date']}", "date": row["date"],
        "generatedAt": row["generated_at"], "scheduledFor": row["scheduled_for"],
        "source": row["source"], "firstSource": row["first_source"], "firstGeneratedAt": row["first_generated_at"],
        "missed": row["first_source"] == "catchup",
        "headline": row["headline"], "summary": row["summary"],
        "sections": store.loads(row["sections"], []), "counts": counts, "gaps": store.loads(row["gaps"], []),
        "empty": empty, "emptyText": C.ALL_EMPTY_TEXT if empty else None,
        "model": row["model"], "promptVersion": row["prompt_version"],
    }


def list_item(row: sqlite3.Row) -> dict:
    v = view(row)
    return {k: v[k] for k in ("id", "date", "generatedAt", "scheduledFor", "source", "firstSource", "firstGeneratedAt",
                              "missed", "headline", "summary", "counts", "empty")}


# ---------------------------------------------------------------- 만들기

def prune(con: sqlite3.Connection, settings: dict, today: date) -> int:
    """보관 기간(오늘 포함 keepDays 일)이 지난 것부터 지운다."""
    cutoff = today - timedelta(days=settings["keepDays"] - 1)
    return store.delete_before(con, cutoff.isoformat())


def _make(con: sqlite3.Connection, src: Sources, now: datetime, source: str, settings: dict) -> dict:
    day = now.date()
    ing, gaps = gather(src, now)
    built = compose.build(ing, now, _alerts_since(con, now))
    line, model = headline.make(compose.facts(built), src.headline_chat) if not built["empty"] else (None, None)
    first = store.get(con, day.isoformat()) is None
    b = {
        "date": day.isoformat(), "generatedAt": now.isoformat(timespec="seconds"),
        "scheduledFor": settings["time"], "source": source,
        "headline": line, "summary": built["summary"], "sections": built["sections"], "counts": built["counts"],
        "gaps": gaps, "model": model, "promptVersion": C.PROMPT_VERSION if model else None,
    }
    store.put(con, b)
    prune(con, settings, day)
    store.set_meta(con, "waiting", None)
    store.touch(con)
    con.commit()
    if first and source != "manual" and src.notify is not None:
        missed = source == "catchup"
        title = f"놓친 브리핑 — {now:%H:%M} 기준으로 만들었습니다" if missed else "오늘 브리핑이 도착했습니다"
        try:
            src.notify(f"briefing:{day.isoformat()}", title, built["summary"], "/",
                       scheduled_at(settings, day), missed)
        except Exception as e:                          # noqa: BLE001 — 알림 센터가 없어도 브리핑은 남는다
            print(f"  브리핑 알림을 남기지 못함: {type(e).__name__}: {e}")
    row = store.get(con, day.isoformat())
    return view(row)


def _waited_enough(con: sqlite3.Connection, day: str, now: datetime) -> bool:
    """수집을 기다리기 시작한 지 5분이 지났나 — 처음 기다리는 것이면 지금부터 센다."""
    w = store.loads(store.get_meta(con, "waiting"), {})
    if w.get("date") != day:
        store.set_meta(con, "waiting", store.dumps({"date": day, "since": now.isoformat(timespec="seconds")}))
        store.touch(con)
        return False
    try:
        since = datetime.fromisoformat(w["since"])
    except (KeyError, ValueError):
        return True
    return now - since >= timedelta(minutes=C.WAIT_COLLECT_MIN)


def ensure_today(src: Sources, now: Optional[datetime] = None) -> dict:
    """오늘 브리핑 — 있으면 그대로, 만들 때가 됐으면 만든다.

    state: ready(있다) · before(예정 시각 전 — 카드를 띄우지 않는다) · pending(수집이 끝나기를 기다리는 중 — 스켈레톤)
           · off(꺼짐 — 카드 없음. 손으로 만든 것이 있으면 briefing 에 싣는다)"""
    now = (now or datetime.now()).replace(microsecond=0)
    day = now.date().isoformat()
    with _lock, store.connect() as con:
        s = S.load(con)
        at = scheduled_at(s, now.date())
        row = store.get(con, day)
        base = {"date": day, "enabled": s["enabled"], "scheduledFor": s["time"], "scheduledAt": at.isoformat(),
                "waitingFor": [], "created": False}
        if not s["enabled"]:
            return {**base, "state": "off", "briefing": view(row) if row else None}
        if row:
            return {**base, "state": "ready", "briefing": view(row)}
        if now < at:
            return {**base, "state": "before", "briefing": None}
        busy = _busy(src)
        if busy and not _waited_enough(con, day, now):
            return {**base, "state": "pending", "briefing": None, "waitingFor": busy}
        source = "scheduled" if now - at <= timedelta(minutes=C.MISSED_AFTER_MIN) else "catchup"
        return {**base, "state": "ready", "briefing": _make(con, src, now, source, s), "created": True}


def regenerate(src: Sources, now: Optional[datetime] = None) -> dict:
    """다시 만들기 — 지금 시점 기준으로 오늘 것을 덮어쓴다(F10-R24). 예정 시각 전·꺼짐이어도 사용자가 누르면 만든다."""
    now = (now or datetime.now()).replace(microsecond=0)
    with _lock, store.connect() as con:
        return _make(con, src, now, "manual", S.load(con))


def get(day: str) -> dict:
    with store.connect() as con:
        row = store.get(con, day)
        if row is None:
            raise NotFound(day)
        return view(row)


def history(limit: int = 30) -> dict:
    """지난 브리핑 목록(최신 순) — 본문(sections)은 빼고 날짜·생성 시각·놓침·한 줄·건수만."""
    with store.connect() as con:
        s = S.load(con)
        return {"items": [list_item(r) for r in store.rows(con, limit)], "keepDays": s["keepDays"],
                "today": date.today().isoformat()}


def status(src: Sources, now: Optional[datetime] = None) -> dict:
    """/api/status 의 briefing 칸 — 1분마다 불린다. 겸사겸사 만들 때가 됐으면 만든다(위 머리 주석)."""
    t = ensure_today(src, now)
    b = t.get("briefing")
    with store.connect() as con:
        updated = store.get_meta(con, "updated_at")
    return {
        "available": True, "enabled": t["enabled"], "time": t["scheduledFor"], "state": t["state"],
        "waitingFor": t["waitingFor"], "updatedAt": updated, "llm": headline.available(),
        "today": {k: b[k] for k in ("date", "generatedAt", "source", "missed", "summary", "counts", "headline")} if b else None,
    }


def settings_view() -> dict:
    with store.connect() as con:
        return S.view(con)


def save_settings(patch: dict, reset: bool = False, today: Optional[date] = None) -> dict:
    with store.connect() as con:
        out = S.save(con, patch, reset=reset)
        prune(con, S.load(con), today or date.today())
        return out


__all__ = ["Sources", "NotFound", "gather", "ensure_today", "regenerate", "get", "history", "status",
           "settings_view", "save_settings", "scheduled_at", "view"]
