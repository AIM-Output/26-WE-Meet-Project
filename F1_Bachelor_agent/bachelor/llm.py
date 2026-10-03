"""(선택) LLM 보조 추출 — OpenAI 호환 /chat/completions. 슬롯은 notice_agent 와 같은 LLM_MAIN_* (.env).

설정이 없으면 아무것도 하지 않는다(규칙 추출만 → 애매한 것은 '확인 필요', F1 9절 'LLM 미설정').

환각 방지: 모델에게 **날짜를 직접 받지 않는다**. 일정 이름과 '원문 그대로의 인용문'만 받고,
    ① 인용문이 원문에 실제로 있는지 검사하고(is_grounded) ② 날짜는 그 인용문을 우리 파서(find_spans)로 다시 읽는다.
그래서 모델이 날짜를 잘못 옮겨 적어도 캘린더에 들어가지 않는다 (F1-R12 '원문에 없는 인용은 버린다').
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Optional

from . import config as C
from .classify import action_for, classify_audience, classify_type, semester_of
from .models import Candidate
from .textutil import find_spans, is_grounded, parse_iso_date

PROMPT = """너는 대학 학사 공지에서 '학생이 캘린더에 넣어야 할 일정'만 찾는 도우미다.
아래 공지에서 일정(신청·납부·마감·시험·행사 기간 등)을 모두 찾아 JSON 으로만 답하라.

형식: {"events": [{"title": "짧은 일정 이름", "quote": "날짜가 들어 있는 원문 문장을 한 글자도 바꾸지 말고 그대로", "audience": "대상(없으면 빈 문자열)"}]}
규칙:
- quote 는 반드시 원문에 그대로 있는 문장이어야 한다. 요약하거나 고치지 마라.
- 자격 조건 속 날짜('~까지 휴학 만료인 자' 등)와 공지 작성일은 일정이 아니다.
- 일정이 없으면 {"events": []}.

제목: {title}
게시일: {posted}
본문:
{body}
"""


def available() -> bool:
    return C.llm_configured()


def _call(prompt: str) -> Optional[dict]:
    import requests
    try:
        r = requests.post(
            f"{C.LLM_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {C.LLM_API_KEY}", "Content-Type": "application/json"},
            json={"model": C.LLM_MODEL, "temperature": 0, "response_format": {"type": "json_object"},
                  "messages": [{"role": "user", "content": prompt}]},
            timeout=C.LLM_TIMEOUT)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"] or ""
    except Exception as e:           # 네트워크·키 오류 → 규칙 추출 결과만 쓴다
        print(f"  LLM 호출 실패 — 규칙 추출만 사용: {str(e)[:120]}")
        return None
    content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    try:
        return json.loads(content)
    except ValueError:
        return None


def refine(post, text: str, cands: list[Candidate], caller=_call) -> list[Candidate]:
    """규칙 후보에 LLM 이 찾은 일정을 더한다. 같은 날짜를 둘 다 찾았으면 규칙 후보의 신뢰도를 올린다."""
    if caller is _call and not available():
        return cands
    ctx = parse_iso_date(post.posted_at) or date.today()
    data = caller(PROMPT.replace("{title}", post.title).replace("{posted}", post.posted_at or "?")
                  .replace("{body}", text[:6000]))
    if not data:
        return cands
    out = list(cands)
    for ev in data.get("events", [])[:20]:
        quote, title = str(ev.get("quote", "")).strip(), str(ev.get("title", "")).strip()[:60]
        if not quote or not title or not is_grounded(quote, text):
            continue
        spans = find_spans(quote, ctx)
        if not spans:
            continue
        sp = spans[0]
        same = next((c for c in out if c.start == sp.start and (c.end == sp.end or c.end is None or sp.end is None)), None)
        if same:
            same.confidence = round(min(0.95, max(same.confidence, 0.85) + 0.05), 2)
            same.flags = sorted(set(same.flags) | {"llm"})
            continue
        type_ = classify_type(title)
        aud = classify_audience(title, context=post.title)
        if ev.get("audience") and not aud.raw:
            aud.raw = str(ev["audience"])[:60]
        act_url, act_label = action_for(type_, aud)
        out.append(Candidate(
            title=title, start=sp.start, start_time=sp.start_time, end=sp.end, end_time=sp.end_time, type=type_,
            audience=aud, evidence=[{"field": "start", "quote": quote[:200]}],
            confidence=0.85 if sp.year_explicit else 0.7, semester=semester_of(title, sp.start), url=post.url,
            post_id=post.post_id, posted_at=post.posted_at, action_url=act_url, action_label=act_label, flags=["llm"],
        ))
    return out
