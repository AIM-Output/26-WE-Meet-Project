"""첨부 공고문 내려받기 + 텍스트 추출.

장학 공지는 본문이 "첨부 참고" 한 줄이고 진짜 자격 요건은 공고문(PDF/HWP)에 있는 경우가 많다.
  - PDF  → pypdf 로 텍스트를 뽑아 추출기 입력에 붙인다 (attachment_text).
  - HWP/HWPX/DOCX → 내려받기만 하고 텍스트는 못 뽑는다 → notes 에 남겨 '확인 필요' 근거로 쓴다.
    (Univ-Us 의 DOC_PARSER 슬롯이 정해지면 여기서 호출하도록 확장한다.)
용량 제한 config.MAX_ATTACH_MB, 확장자 제한 config.ATTACH_EXT.
"""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import config as C
from .schemas import Notice
from .textutil import sanitize_filename


def guess_ext(att_name: str, url: str) -> str:
    for cand in (att_name, unquote(urlparse(url).path), parse_qs(urlparse(url).query).get("filename", [""])[0]):
        suf = Path(cand).suffix.lower()
        if suf and len(suf) <= 6:
            return suf
    return ""


def _reflow(text: str) -> str:
    """어떤 PDF 는 글자·어절 단위로 줄이 끊겨 나온다(평균 줄 길이가 아주 짧음). 그런 경우 줄을 이어 붙여 문장으로 만든다."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    avg = sum(len(ln) for ln in lines) / len(lines)
    if avg >= 8:
        return "\n".join(lines)
    joined = " ".join(lines)
    # 번호 매긴 항목 앞에서는 줄을 바꿔 구조를 조금 살린다
    joined = re.sub(r"\s+(?=(?:\d{1,2}\s*\.|[가-힣]\s*\.|[■□○●▶※√]|Ⅰ|Ⅱ|Ⅲ|Ⅳ|Ⅴ)\s)", "\n", joined)
    return re.sub(r"[ \t]{2,}", " ", joined)


def pdf_text(path: Path, max_pages: int = 15, max_chars: int = 20_000) -> str:
    try:
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        out = []
        for i, page in enumerate(reader.pages[:max_pages]):
            t = page.extract_text() or ""
            if t.strip():
                out.append(f"--- p.{i + 1} ---\n{_reflow(t.strip())}")
        text = "\n".join(out)
        return text[:max_chars]
    except Exception as e:      # 암호화·스캔 PDF 등
        return f"[PDF 텍스트 추출 실패: {str(e)[:80]}]"


def fetch_attachments(http, notice: Notice, dry_run: bool = False) -> None:
    """notice.attachments 를 내려받고 PDF 텍스트를 notice.attachment_text 에 붙인다 (in place)."""
    if not notice.attachments:
        return
    ndir = C.ATTACH_DIR / sanitize_filename(notice.id.replace(":", "_"))
    texts = []
    for att in notice.attachments:
        ext = guess_ext(att.name, att.url)
        if ext not in C.ATTACH_EXT:
            continue
        dest = ndir / sanitize_filename(att.name if Path(att.name).suffix else att.name + ext)
        if dry_run:
            continue
        if not dest.exists():
            try:
                size = http.download(att.url, dest)
            except Exception as e:
                texts.append(f"[첨부 내려받기 실패: {att.name} — {str(e)[:60]}]")
                continue
            if size is None:
                texts.append(f"[첨부 건너뜀(HTML 응답 또는 용량 초과): {att.name}]")
                continue
        att.local_path = str(dest.relative_to(C.ROOT))
        if ext in C.TEXT_EXTRACTABLE_EXT:
            t = pdf_text(dest)
            if t.strip():
                att.text_extracted = True
                texts.append(f"[첨부: {att.name}]\n{t}")
        else:
            texts.append(f"[첨부: {att.name} — {ext} 파일은 텍스트를 읽지 못함. 자격 요건이 이 파일에만 있을 수 있음]")
    notice.attachment_text = "\n\n".join(texts)
