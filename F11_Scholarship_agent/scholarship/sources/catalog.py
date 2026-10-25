"""상시 장학 안내 — 전남대 대표 홈페이지 '장학/학자금융자 › 교내장학금 · 교외장학금' (로그인 불필요, 2026-10-09 실측).

공지 없이 매 학기 선발하는 장학(진리·창조·응원·가족·도전·미래성장·취업더하기·느티나무·발전기금 …)과
국가장학(Ⅰ·Ⅱ유형·국가근로·이공계·인문100년·희망사다리 …)이 표로 정리돼 있다 → 공지와 합쳐 판정한다 (F11-D12).
학사정보시스템(SSO) '학생 맞춤형 장학 안내'(Jang011)는 로그인이 필요해 1차에서는 이 공개 페이지로 대신한다 (README).

구조  h3.ctype '학부' / '대학원' → p.ctype 장학기본성적 → h4.ctype 분류(우수·법정·복지·특별·생활지원형·발전기금재단)
      → table: 장학금명 | 수혜자격 | 지급액 (교외 페이지는 h3 없이 표 하나, 칸이 두 개인 행은 윗 행 장학의 하위 유형)
대학원 표는 학부생 대상이 아니라 넣지 않는다.
"""
from __future__ import annotations

import re

from .base import Http, html_to_text


def _slug(name: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", name)[:40]


def parse(html: str, url: str) -> list[dict]:
    """페이지 → [{native_id, title, section, level, base, qualification, amount, url}]"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    root = soup.select_one("#contents") or soup.select_one(".contents") or soup.body or soup
    level, base_rule, section = None, "", None
    out: list[dict] = []
    for el in root.find_all(["h3", "h4", "p", "table"]):
        if el.name == "h3" and "ctype" in (el.get("class") or []):
            level, base_rule = el.get_text(strip=True), ""
            continue
        if el.name == "p" and "ctype" in (el.get("class") or []):
            base_rule = el.get_text(" ", strip=True)
            continue
        if el.name == "h4":
            section = el.get_text(" ", strip=True)
            continue
        if el.name != "table" or level == "대학원":
            continue
        heads = [th.get_text(strip=True) for th in el.select("thead th")]
        if not heads or "장학금명" not in heads[0]:
            continue
        prev = None
        for tr in el.select("tbody tr"):
            cells = tr.find_all("td")
            texts = [html_to_text(td) for td in cells]
            if len(texts) >= 2 and len(texts) == len(heads):
                name, qual, amount = texts[0], texts[1], (texts[2] if len(texts) > 2 else "")
                prev = name
            elif len(texts) >= 1 and prev:                          # 윗 행 장학의 하위 유형 (rowspan)
                qual, amount = texts[0], (texts[1] if len(texts) > 1 else "")
                sub = re.split(r"\s+-\s+|\n", qual, maxsplit=1)[0].strip()
                name = f"{prev} · {sub}" if sub and sub not in prev else prev
            else:
                continue
            name = re.sub(r"\s+", " ", name).strip()
            if not name:
                continue
            out.append({"native_id": _slug(name), "title": name, "section": section, "level": level or "학부",
                        "base": base_rule, "qualification": qual, "amount": amount, "url": url})
    return out


def fetch(urls: list[str], http: Http) -> list[dict]:
    items: list[dict] = []
    seen = set()
    for url in urls:
        for it in parse(http.get(url).text, url):
            if it["native_id"] in seen:
                continue
            seen.add(it["native_id"])
            items.append(it)
    return items
