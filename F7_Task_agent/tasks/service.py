"""F7 화면·연동용 묶음 — 과제 목록(F6) + 설정 + 오늘 일정 → 그룹 · 순위 · 이유 · 오늘 남은 시간 · 상위 3건.

입력은 전부 넘겨받는다(백엔드는 자기가 붙인 F6·C1·F3·F5 에서, 명령줄은 sources.py 가 직접 읽어서).
그래서 이 모듈은 파일·DB 를 열지 않는다 — 설정(settings.json)만 예외. fastapi 도 부르지 않는다(명령줄에서도 쓴다).
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable, Optional

from . import config as C
from . import rules, today
from . import settings as S

Invalid = S.Invalid


def _match_course(item: dict, course: str) -> bool:
    return course in (item.get("courseId"), item.get("courseShort"), item.get("course"))


def compact(row: dict) -> dict:
    """상위 N건·브리핑·대화용 한 줄 (F7-S06 · R33)."""
    return {k: row.get(k) for k in ("id", "title", "courseShort", "courseColor", "kindLabel", "due", "group",
                                    "groupLabel", "reason", "estimatedHours", "estimateSource", "url")}


def top_of(ranked: list[dict], n: int = C.TOP_N) -> list[dict]:
    """먼저 할 것 — 놓친 마감·마감 없음은 뺀다(놓친 마감은 따로 맨 위에 보이고, 마감 없음은 순위가 없다)."""
    return [r for r in ranked if r["group"] in ("now", "week", "later")][:max(0, n)]


def groups_of(ranked: list[dict]) -> list[dict]:
    out = []
    for g in C.GROUP_ORDER:
        rows = [r for r in ranked if r["group"] == g]
        out.append({
            "key": g, "label": C.GROUPS[g]["label"], "tone": C.GROUPS[g]["tone"],
            "count": len(rows),
            "totalHours": round(sum(r["estimatedHours"] for r in rows), 2),
            "staleCount": sum(1 for r in rows if r.get("stale")),
            "collapsed": g == "later",                    # 나중에 그룹은 기본 접힘 (Frontend-Route 12-1)
        })
    return out


def overview(items: Iterable[dict], now: Optional[datetime] = None, settings: Optional[dict] = None,
             events: Iterable[dict] = (), study_minutes: float = 0.0, course: Optional[str] = None,
             top_n: int = C.TOP_N) -> dict:
    """GET /api/priority — 급한 순 목록(그룹 → 여유 → 마감 → 과목) + 그룹 헤더 + 오늘 남은 시간 + 상위 N건.

    items 는 F6 원장의 과제 화면 모양. 완료·내가 체크함·사라진 과제는 여기서 빠진다(F7-R13).
    F8 은 items 의 순서를 그대로 받아 공강에 배치한다 — 순서를 다시 계산하지 않는다(F7-R34)."""
    now = now or datetime.now()
    settings = settings or S.load()
    pool = [it for it in items if not course or _match_course(it, course)]
    ranked = rules.rank(pool, now, settings)
    groups = groups_of(ranked)
    need = next(g["totalHours"] for g in groups if g["key"] == "now")
    return {
        "items": ranked,
        "groups": groups,
        "counts": {g["key"]: g["count"] for g in groups} | {"open": len(ranked)},
        "top": [compact(r) for r in top_of(ranked, top_n)],
        "today": today.budget(now, settings, events, study_minutes, need),
        "settings": settings,
        "course": course,
        "computedAt": now.isoformat(timespec="seconds"),
    }


def brief(items: Iterable[dict], now: Optional[datetime] = None, settings: Optional[dict] = None,
          n: int = C.TOP_N) -> dict:
    """아침 브리핑(F10)·대화(F9)용 — 상위 N건 + 그 총 소요시간 + 한 줄 문장 (F7-R33)."""
    now = now or datetime.now()
    settings = settings or S.load()
    ranked = rules.rank(items, now, settings)
    top = top_of(ranked, n)
    total = round(sum(r["estimatedHours"] for r in top), 2)
    text = " · ".join(f"{i}) {r['title']} ({rules.fmt_hours(r['estimatedHours'])})" for i, r in enumerate(top, 1))
    overdue = sum(1 for r in ranked if r["group"] == "overdue" and not r.get("stale"))
    return {
        "items": [compact(r) for r in top], "totalHours": total,
        "totalText": rules.fmt_hours(total) if top else "",
        "text": text, "overdue": overdue,
        "computedAt": now.isoformat(timespec="seconds"),
    }


def status_summary(items: Iterable[dict], now: Optional[datetime] = None, settings: Optional[dict] = None) -> dict:
    """/api/status 의 priority 칸 — 기능 타일·대시보드 숫자. 1분마다 불리므로 일정(수업·내 일정)은 읽지 않는다."""
    now = now or datetime.now()
    settings = settings or S.load()
    ranked = rules.rank(items, now, settings)
    groups = {g["key"]: g for g in groups_of(ranked)}
    return {
        "available": True,
        "now": groups["now"]["count"],
        "nowHours": groups["now"]["totalHours"],
        "overdue": groups["overdue"]["count"] - groups["overdue"]["staleCount"],
        "week": groups["week"]["count"],
        "later": groups["later"]["count"],
        "nodue": groups["nodue"]["count"],
        "open": len(ranked),
        "top": [compact(r) for r in top_of(ranked)],
        "computedAt": now.isoformat(timespec="seconds"),
    }
