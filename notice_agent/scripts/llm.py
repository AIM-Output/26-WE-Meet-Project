"""LLM 호출 계층 — OpenAI 호환 인터페이스, 슬롯(LLM_MAIN_*) 기반.  (계획서 4.3 나·라, AI_MODULES `core`)

Univ-Us 의 core_ai-agent 가 완성되면 이 파일은 그쪽 호출로 바꿔 끼운다. 그때까지 필요한 최소 기능만 둔다.
  - 스키마 지정 구조화 출력 (json_schema → 미지원 프로바이더면 json_object 로 후퇴) + Pydantic 검증 + 재시도
  - 같은 입력은 캐시에서 반환 (개발 중 토큰 낭비 방지)   data/cache/
  - 호출마다 토큰 사용량 로그                            data/logs/llm_usage.jsonl
  - 프롬프트는 코드가 아니라 assets/prompts/*.md 파일   (버전 헤더 포함)

키가 없으면 LLM.available 이 False 다. 호출부는 그 경우 규칙 기반으로만 동작해야 한다.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, TypeVar

from pydantic import BaseModel, ValidationError

from . import config as C

T = TypeVar("T", bound=BaseModel)
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class LLMError(RuntimeError):
    pass


def load_prompt(name: str) -> tuple[str, str]:
    """assets/prompts/<name>.md → (version, 본문). 첫 줄 블록 `---\\nversion: N\\n---` 을 버전으로 읽는다."""
    path = C.PROMPT_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    version = "0"
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            k, _, v = line.partition(":")
            if k.strip() == "version":
                version = v.strip()
        text = text[m.end():]
    return version, text.strip()


def render(template: str, **vars) -> str:
    """{{name}} 자리표시자 치환. 없는 변수는 빈 문자열."""
    return re.sub(r"\{\{\s*(\w+)\s*\}\}", lambda m: str(vars.get(m.group(1), "")), template)


class LLM:
    def __init__(self):
        self.available = C.llm_configured()
        self.model = C.LLM_MAIN_MODEL
        self._client = None
        self._json_schema_ok: Optional[bool] = None    # 프로바이더가 json_schema 를 받는지 (첫 호출에서 판정)

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=C.LLM_MAIN_BASE_URL or None, api_key=C.LLM_MAIN_API_KEY,
                                  timeout=C.LLM_TIMEOUT, max_retries=2)
        return self._client

    # -- 캐시 / 로그 ------------------------------------------------------
    def _cache_path(self, key: str) -> Path:
        return C.CACHE_DIR / f"{key}.json"

    @staticmethod
    def _key(*parts: str) -> str:
        h = hashlib.sha256()
        for p in parts:
            h.update(p.encode("utf-8"))
            h.update(b"\x1f")
        return h.hexdigest()[:24]

    def _log(self, purpose: str, usage, cached: bool, elapsed: float) -> None:
        C.LOG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"ts": datetime.now().isoformat(timespec="seconds"), "model": self.model, "purpose": purpose,
               "cached": cached, "elapsed_s": round(elapsed, 2),
               "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
               "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None}
        with open(C.LOG_DIR / "llm_usage.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # -- 호출 -------------------------------------------------------------
    def _chat(self, messages: list[dict], response_format: Optional[dict], temperature: float):
        kw = {"model": self.model, "messages": messages, "temperature": temperature}
        if response_format is not None:
            kw["response_format"] = response_format
        return self.client.chat.completions.create(**kw)

    def structured(self, purpose: str, system: str, user: str, schema: type[T],
                   temperature: float = 0.0, max_attempts: int = 3) -> T:
        """스키마 검증을 통과한 객체를 돌려준다. 계속 실패하면 LLMError."""
        if not self.available:
            raise LLMError("LLM_MAIN_API_KEY / LLM_MAIN_MODEL 이 설정되지 않았습니다 (.env)")
        key = self._key(self.model, purpose, system, user, schema.__name__)
        cp = self._cache_path(key)
        if C.ENABLE_RESPONSE_CACHE and cp.exists():
            try:
                obj = schema.model_validate_json(cp.read_text(encoding="utf-8"))
                self._log(purpose, None, cached=True, elapsed=0.0)
                return obj
            except ValidationError:
                cp.unlink(missing_ok=True)

        json_schema = schema.model_json_schema()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        last_err = ""
        for attempt in range(1, max_attempts + 1):
            rf = None
            if self._json_schema_ok is not False:
                rf = {"type": "json_schema",
                      "json_schema": {"name": schema.__name__, "schema": json_schema, "strict": False}}
            else:
                rf = {"type": "json_object"}
            t0 = time.time()
            try:
                resp = self._chat(messages, rf, temperature)
            except Exception as e:
                msg = str(e)
                # json_schema 를 모르는 프로바이더 → json_object 로 한 번 후퇴
                if self._json_schema_ok is None and ("response_format" in msg or "json_schema" in msg or "400" in msg):
                    self._json_schema_ok = False
                    continue
                raise LLMError(f"LLM 호출 실패: {msg[:200]}") from e
            if self._json_schema_ok is None:
                self._json_schema_ok = True
            content = (resp.choices[0].message.content or "").strip()
            self._log(purpose, getattr(resp, "usage", None), cached=False, elapsed=time.time() - t0)
            content = _FENCE.sub("", content).strip()
            try:
                obj = schema.model_validate_json(content)
            except ValidationError as ve:
                last_err = str(ve)[:600]
                # 검증 오류를 돌려주고 고치게 한다
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content":
                                 "위 JSON 이 스키마 검증에 실패했습니다. 오류를 고쳐 **JSON 만** 다시 출력하세요.\n" + last_err})
                continue
            if C.ENABLE_RESPONSE_CACHE:
                C.CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cp.write_text(obj.model_dump_json(indent=2), encoding="utf-8")
            return obj
        raise LLMError(f"스키마 검증 {max_attempts}회 실패: {last_err[:200]}")

    def text(self, purpose: str, system: str, user: str, temperature: float = 0.4) -> str:
        if not self.available:
            raise LLMError("LLM_MAIN_API_KEY / LLM_MAIN_MODEL 이 설정되지 않았습니다 (.env)")
        key = self._key(self.model, purpose, system, user, "text", str(temperature))
        cp = self._cache_path(key)
        if C.ENABLE_RESPONSE_CACHE and cp.exists():
            self._log(purpose, None, cached=True, elapsed=0.0)
            return cp.read_text(encoding="utf-8")
        t0 = time.time()
        try:
            resp = self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}],
                              None, temperature)
        except Exception as e:
            raise LLMError(f"LLM 호출 실패: {str(e)[:200]}") from e
        out = (resp.choices[0].message.content or "").strip()
        self._log(purpose, getattr(resp, "usage", None), cached=False, elapsed=time.time() - t0)
        if C.ENABLE_RESPONSE_CACHE:
            C.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cp.write_text(out, encoding="utf-8")
        return out
