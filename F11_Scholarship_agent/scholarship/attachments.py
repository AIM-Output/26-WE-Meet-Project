"""첨부 공고문의 글자 읽기 (F11-R04) — 파일은 저장하지 않고 글자만 남긴다.

  PDF            pypdf (앞 15쪽)
  HWPX · DOCX    zip 안의 XML 에서 글자만 (표준 라이브러리 zipfile)
  HWP · XLSX …   못 읽는다 → '첨부를 읽지 못했습니다' + 판정은 확인 필요 (F11 9절)
장학 공지는 본문이 짧고 조건이 첨부에 있는 경우가 많다(2026-09 notice_agent 실측: 첨부 30여 개 중 HWP/HWPX 가 절반).
"""
from __future__ import annotations

import io
import re
import zipfile
from typing import Optional

READABLE = (".pdf", ".hwpx", ".docx")
MAX_CHARS = 12000


def ext_of(name: str, url: str = "") -> str:
    for s in (name or "", url or ""):
        m = re.search(r"\.(pdf|hwpx|hwp|docx|doc|xlsx|xls|pptx|zip|jpg|jpeg|png)(?:$|[?#\s)])", s.lower())
        if m:
            return "." + m.group(1)
    return ""


def _xml_text(data: bytes, members: tuple[str, ...]) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names = [n for n in z.namelist() if any(re.fullmatch(p, n) for p in members)]
        parts = []
        for n in sorted(names):
            xml = z.read(n).decode("utf-8", "replace")
            xml = re.sub(r"</(?:hp:p|w:p|hp:tr|w:tr)>", "\n", xml)
            xml = re.sub(r"</(?:hp:tc|w:tc)>", " | ", xml)
            parts.append(re.sub(r"<[^>]+>", "", xml))
    text = "\n".join(parts)
    text = re.sub(r"&lt;", "<", re.sub(r"&gt;", ">", re.sub(r"&amp;", "&", text)))
    return re.sub(r"[ \t]+", " ", text)


def read_text(data: bytes, ext: str) -> Optional[str]:
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:15])[:MAX_CHARS]
        if ext == ".hwpx":
            return _xml_text(data, (r"Contents/section\d+\.xml",))[:MAX_CHARS]
        if ext == ".docx":
            return _xml_text(data, (r"word/document\.xml",))[:MAX_CHARS]
    except Exception:                      # noqa: BLE001 — 깨진 첨부 하나로 수집이 멈추지 않게
        return None
    return None
