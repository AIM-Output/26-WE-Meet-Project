"""수집기 레지스트리 — config.SOURCES[].kind → 수집기 클래스.

게시판 구조가 같은 사이트는 같은 kind 를 쓴다. 새 게시판은 셀렉터가 같은 kind 에 설정만 추가하고,
구조가 다르면 base.BaseSource 를 상속한 파일을 하나 더 만든다 (BE 분해서: "다중 게시판 수집기 — 소스별 개별 구현").
"""
from __future__ import annotations

from .base import BaseSource, ListItem
from .jnu_aspx import JnuAspxBoard
from .k2web import K2WebBoard
from .aicoss import AicossBoard

REGISTRY: dict[str, type[BaseSource]] = {
    "jnu_aspx": JnuAspxBoard,
    "k2web": K2WebBoard,
    "aicoss": AicossBoard,
}


def make_source(cfg: dict, http) -> BaseSource:
    kind = cfg["kind"]
    if kind == "hakstd":
        from .hakstd import HakstdCatalog      # playwright 는 여기서만 필요 → 지연 import
        return HakstdCatalog(cfg, http)
    if kind not in REGISTRY:
        raise KeyError(f"알 수 없는 수집기 kind: {kind}")
    return REGISTRY[kind](cfg, http)


__all__ = ["BaseSource", "ListItem", "make_source", "REGISTRY"]
