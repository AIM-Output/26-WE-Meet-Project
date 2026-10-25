"""맨 위 한 줄 요약 — LLM (선택, F10 D1 · 5절 '한 줄 요약 규칙').

OpenAI 호환 chat/completions 를 표준 라이브러리(urllib)로 부른다. 슬롯 이름은 F1·F11·F12 와 같다(LLM_MAIN_*).
모델 선정은 AI팀 몫이라 코드에 모델 이름을 쓰지 않는다.

    입력  템플릿이 만든 **숫자와 제목만**(compose.facts) — 강의실·메모·알림 본문·이름·학번은 보내지 않는다(10절 프라이버시)
    출력  한 문장, 60자 이내. 숫자를 새로 만들지 않는다
    검증  ① 한 줄 ② 60자 이내 ③ 격려 문구 없음 ④ 문장 속 숫자가 전부 입력에 있던 숫자 — 하나라도 어기면 그 줄을 버린다(9절)
    실패  LLM 미설정 · 오류 · 3초 초과 → None (이 줄만 빠지고 나머지는 그대로, F10-R14)
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Optional

from . import config as C

SYSTEM = (
    "너는 대학생의 아침 브리핑 맨 위에 붙일 한 줄 요약을 쓴다. "
    "받은 숫자와 목록만 보고 오늘 무엇이 가장 급한지 한 문장으로 말한다. "
    "규칙: 한국어 한 문장, 60자 이내, 존댓말(~습니다). 받은 숫자 말고는 숫자를 쓰지 않는다. 계산·추측 금지. "
    "'화이팅' 같은 격려나 느낌표를 쓰지 않는다. 문장만 답한다."
)

_NUM = re.compile(r"\d+")


def available() -> bool:
    return C.llm_configured()


def _chat(system: str, user: str) -> str:
    body = json.dumps({"model": C.LLM_MODEL, "temperature": 0.2, "max_tokens": 120,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode("utf-8")
    req = urllib.request.Request(f"{C.LLM_BASE_URL}/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {C.LLM_API_KEY}"})
    with urllib.request.urlopen(req, timeout=C.LLM_TIMEOUT) as r:
        data = json.loads(r.read().decode("utf-8"))
    return str(data["choices"][0]["message"]["content"] or "")


def allowed_numbers(facts: dict) -> set[str]:
    return set(_NUM.findall(json.dumps(facts, ensure_ascii=False)))


def validate(text: Optional[str], facts: dict) -> Optional[str]:
    """규칙을 어기면 None — 고쳐 쓰지 않고 버린다."""
    if not text:
        return None
    line = text.strip().strip('"').strip("'").strip()
    if not line or "\n" in line or len(line) > C.HEADLINE_MAX:
        return None
    if any(b in line for b in C.BANNED):
        return None
    if not set(_NUM.findall(line)) <= allowed_numbers(facts):
        return None                                  # 템플릿에 없던 숫자를 지어냈다
    return line


def make(facts: dict, chat=None) -> tuple[Optional[str], Optional[str]]:
    """(한 줄, 모델 이름) — 실패하면 (None, None). chat(system, user) 은 테스트가 바꿔 끼운다."""
    if chat is None:
        if not available():
            return None, None
        chat = _chat
    if not facts.get("counts"):
        return None, None                            # 오늘은 일정이 없습니다 — 요약할 것이 없다
    try:
        raw = chat(SYSTEM, json.dumps(facts, ensure_ascii=False))
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError, OSError) as e:
        print(f"  브리핑 한 줄 요약 실패 — 생략: {type(e).__name__}: {str(e)[:120]}")
        return None, None
    line = validate(raw, facts)
    return (line, C.LLM_MODEL or "test") if line else (None, None)
