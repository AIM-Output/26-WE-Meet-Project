"""C1 서비스 캘린더 — 규칙 (소스 합치기 · 기간 거르기 · 날짜 검사).

/api/events 는 모든 소스를 **한 배열**로 내려준다 (C1-R10). 소스별 수집·저장 코드는 각 기능 폴더에 있고
여기서는 합치는 규칙만 갖는다 — 순서 · 기간 겹침 · 종일 end exclusive (C1-R14).

fastapi 를 부르지 않는다 — 명령줄(desktop/cli.py)에서도 그대로 쓰기 위해서다. 오류는 문자열로 돌려주고
HTTP 상태로 바꾸는 일은 api.py 가 한다.
"""
from __future__ import annotations

import re
from typing import Callable, Optional, Sequence

from . import store

# 다른 기능이 캘린더에 얹는 일정을 주는 함수: (start, end) → FullCalendar 이벤트 목록.
# 백엔드가 F6(마감)·F1(학사)·F3(수업) 것을 넘겨준다 (C1 3절).
Source = Callable[[Optional[str], Optional[str]], list[dict]]

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2})?)?$")


def date_error(start: Optional[str], end: Optional[str]) -> Optional[str]:
    """start·end 형식과 앞뒤를 본다. 문제가 없으면 None."""
    for label, v in (("start", start), ("end", end)):
        if v is not None and not DATE_RE.match(v):
            return f"{label} 형식이 잘못됐습니다: {v!r} (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM[:SS])"
    if start and end and end <= start:
        return "종료가 시작보다 빠르거나 같습니다."
    return None


def parse_user_id(event_id: str) -> Optional[int]:
    """내 일정 id(숫자)만 고칠 수 있다. 'dl:'(마감)·'ac:'(학사)·'cl:'(수업)은 원천이 따로 있다 (C1 3절)."""
    return int(event_id) if event_id.isdigit() else None


def overlaps(ev: dict, start: Optional[str], end: Optional[str]) -> bool:
    """[start, end] 구간에 걸치는 일정인지. 날짜(YYYY-MM-DD)까지만 본다."""
    s = ev["start"][:10]
    e = (ev.get("end") or ev["start"])[:10]
    return (not end or s <= end) and (not start or e >= start)


def collect(sources: Sequence[Source] = (), start: Optional[str] = None,
            end: Optional[str] = None) -> list[dict]:
    """캘린더에 들어오는 모든 소스 + 내 일정을 합친다.

    소스 하나가 깨져도 캘린더 전체가 죽지 않게 각 소스는 스스로 예외를 삼키고 빈 목록을 준다
    (백엔드 shim 들이 그렇게 되어 있다). 기간은 여기서 한 번에 거른다.
    """
    events: list[dict] = []
    for source in sources:
        events += source(start, end)
    events += store.list_events()
    if start or end:
        events = [ev for ev in events if overlaps(ev, start, end)]
    return events
