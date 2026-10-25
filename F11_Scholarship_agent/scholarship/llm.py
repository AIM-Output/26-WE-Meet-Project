"""LLM 호출 (선택) — OpenAI 호환 chat/completions 를 표준 라이브러리(urllib)로. 슬롯 이름은 F1·notice_agent 와 같다.

설정이 없으면 available=False 이고 부르는 쪽은 골격 초안으로 간다 (F11-R48). 모델 선정은 AI팀 몫(F11-Q1)이라 코드에 모델 이름을 쓰지 않는다.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from . import config as C


class LLMError(RuntimeError):
    pass


def available() -> bool:
    return C.llm_configured()


def chat(system: str, user: str, temperature: float = 0.4, max_tokens: int = 1400) -> str:
    if not available():
        raise LLMError("LLM 이 설정되지 않았습니다 (LLM_MAIN_BASE_URL · API_KEY · MODEL)")
    body = json.dumps({"model": C.LLM_MODEL, "temperature": temperature, "max_tokens": max_tokens,
                       "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}).encode("utf-8")
    req = urllib.request.Request(f"{C.LLM_BASE_URL}/chat/completions", data=body, method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {C.LLM_API_KEY}"})
    try:
        with urllib.request.urlopen(req, timeout=C.LLM_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError) as e:
        raise LLMError(f"{type(e).__name__}: {e}") from e
