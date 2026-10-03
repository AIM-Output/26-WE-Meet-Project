"""파일에서 읽는 메타 — 쪽수 · 텍스트 유무 · 암호 · 내용 해시. 표준 라이브러리만.

왜 직접 읽나
  - **쪽수**는 화면(F4-S02 '13쪽')과 F5 학습 분량 산정(F5-R10)이 바로 쓴다. 인덱싱(AI팀)보다 먼저 필요하다.
  - **텍스트 유무**는 스캔 PDF 를 `OCR 필요` 로 걸러 빈 요약을 만들지 않기 위한 것이다 (F4-R06).
  - **내용 해시**는 같은 파일 중복 판정(F4 8절)과 '파일이 바뀌면 다시 인덱싱'(F4-R07)의 기준이다.

정확도에 대해
  - PDF 는 페이지 객체(`/Type /Page`)를 센다. 객체 스트림(압축 xref)에 숨어 있으면 스트림을 풀어서 다시 센다.
    그래도 못 세면 페이지 트리의 `/Count` 중 가장 큰 값을 쓴다. 전부 실패하면 **쪽수 없음(None)** — 틀린 숫자를 만들지 않는다.
  - 텍스트 유무는 글꼴(`/Font`)이 하나라도 있는지로 본다. 없으면 `none`(스캔본), 있으면 `text`,
    파일을 못 읽었으면 `unknown` — **`none` 일 때만** 화면이 'OCR 필요'로 표시한다.
  - PPTX 는 슬라이드 수, DOCX 는 만든 프로그램이 적어 둔 `docProps/app.xml` 의 쪽수(없으면 None).
"""
from __future__ import annotations

import hashlib
import re
import zipfile
import zlib
from pathlib import Path
from typing import Optional

# 객체 스트림을 풀어 볼 때의 상한 — 큰 PDF 에서 시간을 다 쓰지 않게
_MAX_OBJSTM = 80
_MAX_INFLATED = 16 * 1024 * 1024

_PAGE_OBJ = re.compile(rb"/Type\s*/Page(?![s/\w])")
_PAGES_COUNT = re.compile(rb"/Type\s*/Pages\b")
_COUNT = re.compile(rb"/Count\s+(\d+)")
_FONT = re.compile(rb"/(?:Font|FontFile\d?|BaseFont)\b")
_STREAM = re.compile(rb"stream\r?\n")
_OBJSTM = re.compile(rb"/Type\s*/ObjStm")


class Meta(dict):
    """{pages, textState('text'|'none'|'unknown'), locked, error}"""


def _meta(pages: Optional[int] = None, text: str = "unknown", locked: bool = False, error: str = "") -> Meta:
    return Meta(pages=pages, textState=text, locked=locked, error=error)


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def read(path: Path, ext: Optional[str] = None) -> Meta:
    """파일 하나의 쪽수·텍스트 유무. 읽지 못해도 예외를 올리지 않는다 (error 에 사유)."""
    ext = (ext or path.suffix).lower()
    try:
        if ext == ".pdf":
            return pdf(path.read_bytes())
        if ext == ".pptx":
            return _pptx(path)
        if ext == ".docx":
            return _docx(path)
        if ext in (".txt", ".md"):
            return _meta(None, "text")
    except FileNotFoundError:
        return _meta(error="파일이 없습니다")
    except Exception as e:                       # noqa: BLE001 — 자료 하나 때문에 목록이 죽지 않게
        return _meta(error=f"{type(e).__name__}: {e}")
    return _meta()


# ---------------------------------------------------------------- PDF

def pdf(data: bytes) -> Meta:
    if not data.startswith(b"%PDF"):
        return _meta(error="PDF 가 아닙니다")
    if b"/Encrypt" in data:
        return _meta(locked=True, error="암호가 걸린 PDF")
    pages = len(_PAGE_OBJ.findall(data))
    has_font = bool(_FONT.search(data))
    if pages == 0 or not has_font:
        # 압축 xref 를 쓰는 PDF 는 페이지 객체·글꼴이 객체 스트림 안에 들어 있다 (2026-09-30 실측: 일부 강의자료가 그렇다)
        objstm = _object_streams(data)
        if pages == 0:
            pages = len(_PAGE_OBJ.findall(objstm))
        has_font = has_font or bool(_FONT.search(objstm))
        if pages == 0:
            pages = _from_count(data) or _from_count(objstm)
    return _meta(pages or None, "text" if has_font else "none")


def _from_count(data: bytes) -> int:
    """페이지 트리의 /Count 중 가장 큰 값 (페이지 객체를 못 셌을 때의 마지막 수단)."""
    if not _PAGES_COUNT.search(data):
        return 0
    counts = [int(m.group(1)) for m in _COUNT.finditer(data)]
    return max(counts) if counts else 0


def _object_streams(data: bytes) -> bytes:
    """객체 스트림(`/Type /ObjStm`)만 골라 풀어 이어 붙인다 — 상한 안에서만.
    이미지까지 전부 풀면 몇 초씩 걸리고 얻을 것도 없다. 사전(페이지·글꼴)은 여기에만 숨는다."""
    out: list[bytes] = []
    total = 0
    for i, m in enumerate(_OBJSTM.finditer(data)):
        if i >= _MAX_OBJSTM or total >= _MAX_INFLATED:
            break
        sm = _STREAM.search(data, m.end())
        if sm is None:
            break
        end = data.find(b"endstream", sm.end())
        if end < 0:
            break
        try:
            blob = zlib.decompress(data[sm.end():end])
        except zlib.error:
            continue                                     # 다른 필터로 압축된 스트림 — 건너뛴다
        out.append(blob)
        total += len(blob)
    return b"".join(out)


# ---------------------------------------------------------------- Office

_SLIDE = re.compile(r"ppt/slides/slide\d+\.xml")
_DOC_PAGES = re.compile(rb"<Pages>(\d+)</Pages>")
_DOC_WORDS = re.compile(rb"<Words>(\d+)</Words>")


def _pptx(path: Path) -> Meta:
    with zipfile.ZipFile(path) as z:
        n = sum(1 for name in z.namelist() if _SLIDE.fullmatch(name))
    return _meta(n or None, "text")


def _docx(path: Path) -> Meta:
    with zipfile.ZipFile(path) as z:
        try:
            app = z.read("docProps/app.xml")
        except KeyError:
            return _meta(None, "text")
    pages = _DOC_PAGES.search(app)
    words = _DOC_WORDS.search(app)
    return _meta(int(pages.group(1)) if pages else None,
                 "none" if words and int(words.group(1)) == 0 else "text")
