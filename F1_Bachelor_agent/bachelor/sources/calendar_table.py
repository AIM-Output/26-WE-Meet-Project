"""① 학사일정 표 — www.jnu.ac.kr 대학생활 › 학사정보 › 학사일정 (Schedule300.aspx?type=1).

2026-09-28 실측: 달력은 자바스크립트로 그리지만 **데이터는 페이지에 JSON 으로 박혀 있다**.
    var scheduleYear = 2026;var scheduleData = [{"start":"2013-01-07","end":"2013-01-11","title":"…"}, …];
  - 2013년부터 다음 해 초까지 약 900행이 한 번에 온다 (연·월 이동은 화면에서만 걸러 보여 준다).
  - end 는 마지막 날을 포함한다(inclusive). 하루짜리는 start == end.
  - type=1 대학(학부) / type=2 대학원. 기본값(type 없음)은 type=1 과 같다.
형식이 고정돼 있으므로 LLM 없이 규칙만으로 읽는다 (요구사항 F1 7절 '0.9 이상').
"""
from __future__ import annotations

import json
import re

from .base import FormatChanged, Http

_DATA_RE = re.compile(r"var\s+scheduleData\s*=\s*(\[.*?\])\s*;", re.S)
_YEAR_RE = re.compile(r"var\s+scheduleYear\s*=\s*(\d{4})")


def parse(html: str) -> list[dict]:
    """페이지 HTML → [{start, end, title}]. 구조가 바뀌어 데이터를 못 찾으면 FormatChanged."""
    m = _DATA_RE.search(html)
    if not m:
        raise FormatChanged("학사일정 페이지에서 scheduleData 를 찾지 못했습니다")
    try:
        rows = json.loads(m.group(1))
    except ValueError as e:
        raise FormatChanged(f"scheduleData JSON 을 읽지 못했습니다: {e}") from e
    out = []
    for r in rows:
        if not isinstance(r, dict):
            continue
        s, e, t = (r.get("start") or "").strip(), (r.get("end") or "").strip(), (r.get("title") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s) and t:
            out.append({"start": s, "end": e if re.fullmatch(r"\d{4}-\d{2}-\d{2}", e) else s, "title": t})
    if not out:
        raise FormatChanged("학사일정 데이터가 비어 있습니다")
    return out


def fetch(cfg: dict, http: Http) -> tuple[list[dict], dict]:
    """(행 목록, 메타). 메타의 year 는 페이지가 기준으로 삼는 올해."""
    html = http.get(cfg["url"]).text
    rows = parse(html)
    y = _YEAR_RE.search(html)
    return rows, {"year": int(y.group(1)) if y else None, "rows": len(rows)}
