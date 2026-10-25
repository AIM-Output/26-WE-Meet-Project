"""원천 — F11 원천 목록 + 이 기능의 덮어쓰기 → '내 대외활동 원천'. 표준 라이브러리만 (백엔드도 import 한다).

원천 목록·프로필 관련 여부(학교 전체 · 캠퍼스 · 관련 사업단 · 내 소속)는 **F11 과 같다** (scholarship.registry 를 그대로 부른다).
여기서 하는 것은 directory/sources.json 의 덮어쓰기뿐이다:
  - skip      장학만 올라오는 원천(장학안내 분류 · 상시 장학 안내)은 대외활동 목록에서 뺀다
  - sources   원천마다 이름·이유(대외활동 쪽 설명)·게시판 깊이·require(이 말이 있는 글만) — 값이 null 이면 F11 값을 지운다
  - dropCategories · dropWords   대표 공지 말머리(행정공고·입찰공고·채용공고)·제목 어휘(부고·입찰·교원 초빙 …)로 거르는 것
켜고 끈 것은 F11 과 따로 저장한다(store.sources) — 장학은 켜 두고 대외활동만 끌 수 있게.
"""
from __future__ import annotations

import json
from typing import Optional

from . import config as C
from scholarship import registry as base      # F11 원천 목록·관련 여부 (config 가 F11 폴더를 import 경로에 붙였다)

_cache: dict = {"mtime": None, "data": None}

# 프로필 소속 → 홈페이지 · 캠퍼스 · 계열은 F11 과 같은 규칙
homepage = base.homepage
campus_of = base.campus_of
fields_of = base.fields_of
norm = base.norm
relevance = base.relevance


def overlay() -> dict:
    p = C.OVERLAY_FILE
    mtime = p.stat().st_mtime
    if _cache["mtime"] != mtime:
        _cache.update(mtime=mtime, data=json.loads(p.read_text(encoding="utf-8")))
    return _cache["data"]


def groups() -> dict:
    return base.load()["groups"]


def _merge(src: dict) -> dict:
    over = overlay().get("sources", {}).get(src["key"]) or {}
    out = dict(src)
    for k, v in over.items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def sources() -> list[dict]:
    skip = set(overlay().get("skip", []))
    return [_merge(s) for s in base.sources() if s["key"] not in skip]


def get(key: str) -> Optional[dict]:
    return next((s for s in sources() if s["key"] == key), None)


def resolve(profile: Optional[dict], overrides: Optional[dict[str, bool]] = None) -> list[dict]:
    """모든 원천 + 나에게 맞는지 + 켜져 있는지 (F11 resolve 와 같은 모양). overrides = {key: enabled} (사용자가 바꾼 것만)."""
    overrides = overrides or {}
    out = []
    for s in sources():
        rel = relevance(s, profile)
        enabled = overrides.get(s["key"], rel["default"])
        out.append({**s, "relevance": rel, "enabled": bool(enabled), "userSet": s["key"] in overrides})
    return out


def collectable(rows: list[dict]) -> list[dict]:
    """수집기가 실제로 읽을 원천 — 켜져 있고 게시판이 있는 것(relay 는 학교 공지의 작성 부서로 들어온다)."""
    return [r for r in rows if r["enabled"] and r["kind"] != "relay"]


def unit_for(writer: Optional[str], title: str = "", category: Optional[str] = None) -> Optional[dict]:
    """학교 공지의 작성 부서·제목 → 사업단·부서 원천 (F11 규칙). 장학 전용 원천이면 None."""
    u = base.unit_for(writer, title, category)
    if u is None or u["key"] in set(overlay().get("skip", [])):
        return None
    return _merge(u)


def drop_categories() -> list[str]:
    return list(overlay().get("dropCategories", []))


def drop_words() -> list[str]:
    return list(overlay().get("dropWords", []))
