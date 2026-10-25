"""LLM 호출 (선택) — OpenAI 호환 chat/completions 를 표준 라이브러리(urllib)로. 슬롯 이름은 F1·F11 과 같다(LLM_MAIN_*).

설정이 없으면 available=False — 관련도는 키워드·소속으로만(F12-R24), 초안 문단은 골격+빈칸으로 간다.
모델 선정은 AI팀 몫이라 코드에 모델 이름을 쓰지 않는다. 이름·학번은 어떤 프롬프트에도 넣지 않는다.
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


def chat(system: str, user: str, temperature: float = 0.3, max_tokens: int = 1400) -> str:
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
