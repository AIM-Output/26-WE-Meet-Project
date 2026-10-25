"""첨부 공고문·본문 이미지의 글자 읽기 (F11-R04) — 파일은 저장하지 않고 글자만 남긴다. F12 대외활동도 이 모듈을 쓴다.

  PDF            pypdf (앞 15쪽). 글자가 없는 스캔 PDF 는 OS 내장 OCR (osenv.ocr — Windows 만, 앞 3쪽)
  HWPX · DOCX    zip 안의 XML 에서 글자만 (표준 라이브러리 zipfile)
  HWP            HWP 5.0 (OLE 복합 문서) — olefile 로 BodyText/Section* 를 열고(zlib 압축) 문단 글자 레코드만 (2026-10-25)
                 표는 칸을 ' | ' 로 이어 한 행을 한 줄로 — '신청기간 | 2026. 10. 1 ~ 10. 20' 이 한 줄에 있어야 기간 규칙이 읽는다
                 배포용·암호 문서는 본문이 암호화돼 있어 미리보기 글자(PrvText, 앞부분 1천 자 남짓)만
                 글자 없이 그림만 든 HWP(포스터를 붙여 넣은 공고)는 BinData 의 그림을 OCR
  본문 이미지 · JPG·PNG 첨부   OCR — 본문(+읽은 첨부 글자)이 OCR_BODY_SHORT 보다 짧을 때만, 공지 하나에 MAX_OCR_IMAGES 장까지
  XLSX · PPTX …  못 읽는다 → '첨부를 읽지 못했습니다' + 판정은 확인 필요 (F11 9절)
장학 공지는 본문이 짧고 조건이 첨부에 있는 경우가 많다(2026-10-25 실측: 장학 공지 109건의 첨부 101개 중 HWP 31개를 못 읽고 있었다,
본문이 이미지뿐인 공지 23%).

OCR 로 읽은 글자는 '[본문 이미지 OCR]' · '[첨부 OCR: 이름]' 머리를 달아 attach_text 에 둔다 — 추출이 has_ocr() 로 알아보고
신뢰도를 낮춘다(F11: 자동 '해당'·'비해당' 대신 확인 필요, F12: 'OCR 로 읽음' 안내).

reader_version(ocr) — 읽는 방법의 판. 공지마다 notices.reader_ver 에 남긴다. 저장된 판이 지금보다 낮고 다시 읽으면 나아질 공지
(본문이 이미지 · 못 읽은 HWP·PDF·이미지 첨부)는 수집기가 상세를 한 번 다시 받는다(needs_reread — 예전에 못 읽은 공지 다시 받기).
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile
import zlib
from typing import Optional

READABLE = (".pdf", ".hwpx", ".docx", ".hwp")
IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp")
MAX_CHARS = 12000
OCR_BODY_SHORT = 300                       # 본문+첨부 글자가 이보다 짧으면 이미지를 OCR 한다
MAX_OCR_IMAGES = 4                         # 공지 하나에서 OCR 할 이미지 최대 수 (본문 이미지 + 이미지 첨부)
OCR_PDF_PAGES = 3
OCR_HWP_IMAGES = 3
_OCR_HEAD = re.compile(r"^\[(?:본문 이미지 OCR|첨부 OCR:)", re.M)


def reader_version(ocr) -> int:
    """1: PDF·HWPX·DOCX · 2: + HWP (2026-10-25) · 3: + OCR (이 컴퓨터에서 OS OCR 을 쓸 수 있을 때)."""
    return 3 if ocr is not None else 2


def ext_of(name: str, url: str = "") -> str:
    for s in (name or "", url or ""):
        m = re.search(r"\.(pdf|hwpx|hwp|docx|doc|xlsx|xls|pptx|zip|jpg|jpeg|png|gif|bmp)(?:$|[?#\s)])", s.lower())
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


# ── HWP 5.0 ────────────────────────────────────────────────
# 레코드 머리 4바이트: 태그(10비트) · 수준(10비트) · 크기(12비트, 0xFFF 면 다음 4바이트가 크기) — 한글 문서 파일 형식 5.0 공개 문서
HWPTAG_PARA_TEXT = 67
HWPTAG_LIST_HEADER = 72
# 문단 글자 안의 조절 문자 — 이 번호들은 글자 8개(16바이트) 자리를 차지한다(확장·인라인 컨트롤). 10·13 은 줄바꿈, 나머지 32 미만은 1글자
_CTRL_WIDE = {1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 12, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23}
# 한글 전용 글꼴의 기호(󰊱 같은 사용자 영역 글자)는 다른 곳에서 보이지 않는다 — 지운다
_PUA = re.compile("[-\U000f0000-\U0010ffff]")


def _records(raw: bytes):
    i, n = 0, len(raw)
    while i + 4 <= n:
        h = int.from_bytes(raw[i:i + 4], "little")
        i += 4
        tag, level, size = h & 0x3FF, (h >> 10) & 0x3FF, (h >> 20) & 0xFFF
        if size == 0xFFF:
            size = int.from_bytes(raw[i:i + 4], "little")
            i += 4
        yield tag, level, raw[i:i + size]
        i += size


def _para_text(b: bytes) -> str:
    buf = bytearray()
    j = 0
    while j + 2 <= len(b):
        c = int.from_bytes(b[j:j + 2], "little")
        if c in _CTRL_WIDE:
            if c == 9:
                buf += "\t".encode("utf-16-le")
            j += 16
            continue
        if c in (10, 13):
            buf += "\n".encode("utf-16-le")
        elif c >= 32:
            buf += b[j:j + 2]
        j += 2
    return _PUA.sub("", buf.decode("utf-16-le", "ignore")).strip()


def hwp_section_text(raw: bytes) -> str:
    """압축을 푼 BodyText/Section 스트림 → 글자. 표 칸(LIST_HEADER 의 행 번호)이 같은 행이면 ' | ' 로 잇는다."""
    out: list[str] = []
    row_cells: list[str] = []
    cell: list[str] = []
    cell_level: Optional[int] = None
    row: Optional[int] = None

    def flush_cell():
        nonlocal cell
        if cell_level is not None:
            row_cells.append(" ".join(x for x in cell if x))
        cell = []

    def flush_row():
        nonlocal row_cells
        if any(row_cells):
            out.append(" | ".join(x for x in row_cells if x))
        row_cells = []

    for tag, level, body in _records(raw):
        if tag == HWPTAG_LIST_HEADER and len(body) >= 12:          # 표 칸 — 문단 수·속성(8바이트) 다음에 열·행 번호
            flush_cell()
            r = int.from_bytes(body[10:12], "little")
            if r != row or cell_level is None or level != cell_level:
                flush_row()
            row, cell_level = r, level
            continue
        if cell_level is not None and level < cell_level:          # 표가 끝났다
            flush_cell()
            flush_row()
            cell_level, row = None, None
        if tag == HWPTAG_PARA_TEXT:
            t = _para_text(body)
            if cell_level is not None and level > cell_level:
                cell.append(t.replace("\n", " "))
            elif t:
                out.append(t)
    flush_cell()
    flush_row()
    return "\n".join(x for x in out if x.strip())


def _hwp_open(data: bytes):
    import olefile                                     # desktop/sidecar/requirements.txt (순수 파이썬)
    ole = olefile.OleFileIO(io.BytesIO(data))
    hdr = ole.openstream("FileHeader").read() if ole.exists("FileHeader") else b""
    if not hdr.startswith(b"HWP Document File"):
        ole.close()
        return None, 0
    return ole, int.from_bytes(hdr[36:40], "little")


def _hwp_text(data: bytes) -> Optional[str]:
    ole, flags = _hwp_open(data)
    if ole is None:
        return None
    try:
        compressed, encrypted, distributed = bool(flags & 1), bool(flags & 2), bool(flags & 4)
        parts: list[str] = []
        if not (encrypted or distributed):
            sections = [e for e in ole.listdir() if len(e) == 2 and e[0] == "BodyText" and e[1].startswith("Section")]
            for e in sorted(sections, key=lambda e: int(re.sub(r"\D", "", e[1]) or 0)):
                raw = ole.openstream(e).read()
                if compressed:
                    raw = zlib.decompress(raw, -15)
                parts.append(hwp_section_text(raw))
        text = "\n".join(p for p in parts if p)
        if len(text.strip()) < 30 and ole.exists("PrvText"):        # 배포용·암호 문서 — 미리보기 글자라도
            text = _PUA.sub("", ole.openstream("PrvText").read().decode("utf-16-le", "ignore").replace("\x00", ""))
        return text
    finally:
        ole.close()


def _is_image(b: bytes) -> bool:
    return b[:3] == b"\xff\xd8\xff" or b[:8] == b"\x89PNG\r\n\x1a\n" or b[:4] in (b"GIF8",) or b[:2] == b"BM"


def hwp_images(data: bytes, limit: int = OCR_HWP_IMAGES) -> list[bytes]:
    """HWP 안에 붙여 넣은 그림(BinData) — 큰 것부터. 압축 여부는 그림마다 다를 수 있어 풀어 보고 안 되면 그대로."""
    try:
        ole, _flags = _hwp_open(data)
    except Exception:                                  # noqa: BLE001
        return []
    if ole is None:
        return []
    try:
        out = []
        for e in ole.listdir():
            if len(e) != 2 or e[0] != "BinData":
                continue
            raw = ole.openstream(e).read()
            try:
                raw = zlib.decompress(raw, -15)
            except zlib.error:
                pass
            if _is_image(raw) and len(raw) > 8 * 1024:
                out.append(raw)
        return sorted(out, key=len, reverse=True)[:limit]
    finally:
        ole.close()


# ── 문서 하나 ───────────────────────────────────────────────

def read_text(data: bytes, ext: str) -> Optional[str]:
    """문서 첨부 → 글자 (OCR 없이 읽히는 것만). 못 읽으면 None."""
    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            return "\n".join((p.extract_text() or "") for p in reader.pages[:15])[:MAX_CHARS]
        if ext == ".hwpx":
            return _xml_text(data, (r"Contents/section\d+\.xml",))[:MAX_CHARS]
        if ext == ".docx":
            return _xml_text(data, (r"word/document\.xml",))[:MAX_CHARS]
        if ext == ".hwp":
            t = _hwp_text(data)
            return t[:MAX_CHARS] if t else None
    except Exception:                      # noqa: BLE001 — 깨진 첨부 하나로 수집이 멈추지 않게
        return None
    return None


def _enough(t: Optional[str]) -> bool:
    return bool(t) and len(t.strip()) > 30


# 표 이미지를 OCR 하면 이름표 칸과 값 칸이 다른 줄로 나온다('제출기한' / '2026. 11. 11.(수)') — 추출 규칙은 한 줄을 본다
_LABEL_LINE = re.compile(r"^[□■◎○●•▢◦▶\-\s]*[가-힣][가-힣 ·/]{1,11}[:：]?$")
# Windows OCR 이 '청'을 '정'으로 읽는 일이 잦다(2026-10-25 실측 '신정기간') — 기간 규칙이 '신청 기간'을 찾으므로 이름표만 바로잡는다
_OCR_FIX = re.compile(r"신정(?=\s*(?:기간|기한|방법|서류|자격|마감|대상))")


def clean_ocr(text: str) -> str:
    """OCR 글자 다듬기 — 장식·기호를 잘못 읽은 한 글자 줄('十' '回' 'B')은 버리고,
    짧은 이름표 줄(한글 8자 이하) 다음 줄이 숫자·괄호·물결로 시작하면 '이름표 : 값' 한 줄로."""
    text = _OCR_FIX.sub("신청", text or "")
    ls = [ln.rstrip() for ln in text.splitlines() if len(ln.strip()) > 1]
    out: list[str] = []
    i = 0
    while i < len(ls):
        a = ls[i].strip()
        if (i + 1 < len(ls) and _LABEL_LINE.match(a) and len(re.sub(r"[\s:：□■◎○●•▢◦▶\-]", "", a)) <= 8
                and re.match(r"\s*[\d(~∼]", ls[i + 1])):
            out.append(f"{a.rstrip(':：').strip()} : {ls[i + 1].strip()}")
            i += 2
            continue
        out.append(ls[i])
        i += 1
    return "\n".join(out).strip()


def doc_text(data: bytes, ext: str, ocr=None) -> tuple[Optional[str], Optional[str]]:
    """문서 첨부 → (글자, 읽은 방법 'text' | 'ocr'). 글자가 없는 스캔 PDF·그림만 든 HWP 는 OCR 로."""
    t = read_text(data, ext)
    if _enough(t):
        return t.strip(), "text"
    if ocr is None:
        return None, None
    try:
        if ext == ".pdf":
            t = ocr.pdf_text(data, OCR_PDF_PAGES)
        elif ext == ".hwp":
            imgs = hwp_images(data)
            t = "\n".join(x.strip() for x in ocr.image_texts(imgs) if x) if imgs else None
        else:
            return None, None
    except Exception:                      # noqa: BLE001
        return None, None
    return (clean_ocr(t)[:MAX_CHARS], "ocr") if _enough(t) else (None, None)


# ── 공지 하나 (F11·F12 수집기가 부른다) ─────────────────────

def ocr_engine():
    """이 컴퓨터에서 한국어 OCR 을 쓸 수 있으면 osenv.ocr 모듈, 아니면 None — 수집 한 번에 한 번 부른다."""
    try:
        from osenv import ocr                           # C0 — 기능 config 가 C0 폴더를 sys.path 에 붙여 둔다
        st = ocr.available()
    except Exception:                                   # noqa: BLE001
        return None
    return ocr if st.get("ok") and st.get("korean") else None


def ocr_status() -> dict:
    try:
        from osenv import ocr
        return ocr.available()
    except Exception as e:                              # noqa: BLE001
        return {"ok": False, "reason": f"osenv.ocr 없음 ({type(e).__name__})"}


def _image_bytes(src: str, http) -> Optional[bytes]:
    if src.startswith("data:"):
        head, _, b64 = src.partition(",")
        if not head.startswith("data:image/") or ";base64" not in head:
            return None
        try:
            return base64.b64decode(b64)
        except ValueError:
            return None
    return http.download(src)


def unread_count(infos: list[dict]) -> int:
    """읽지 못한 문서 첨부 수 — 이미지·zip 은 세지 않는다(못 읽어도 '첨부를 읽지 못함'으로 판정을 보류하지 않는다)."""
    return sum(1 for a in infos if not a.get("read") and a.get("ext") not in IMAGE_EXTS + (".zip",))


def has_ocr(attach_text: Optional[str]) -> bool:
    return bool(attach_text and _OCR_HEAD.search(attach_text))


def ocr_part(attach_text: Optional[str]) -> str:
    """attach_text 중 OCR 로 읽은 덩어리만 — 화면의 '이미지에서 읽은 글자'."""
    blocks = re.split(r"\n\n(?=\[(?:첨부|본문 이미지))", attach_text or "")
    return "\n\n".join(b for b in blocks if _OCR_HEAD.match(b))


def gather(post, http, *, max_read: int, read: bool = True, ocr=None) -> tuple[str, list[dict], int]:
    """공지 하나의 첨부 글자 + (본문이 짧으면) 이미지 OCR. 반환 (글자, 첨부 기록, 읽지 못한 문서 첨부 수).
    read=False 면 첨부 목록만 남긴다(F12 — 본문이 길면 첨부를 받지 않는다). ocr = ocr_engine() 의 결과(없으면 OCR 안 함)."""
    texts: list[str] = []
    infos: list[dict] = []
    images: list[tuple[Optional[dict], str]] = []
    n_read = 0
    for a in post.attachments[:8]:
        ext = ext_of(a.get("name", ""), a.get("url", ""))
        info = {"name": a.get("name"), "url": a.get("url"), "ext": ext, "read": False}
        if read and ext in READABLE and n_read < max_read:
            data = http.download(a["url"])
            t, how = doc_text(data, ext, ocr) if data else (None, None)
            if t:
                head = f"[첨부 OCR: {a.get('name')}]" if how == "ocr" else f"[첨부: {a.get('name')}]"
                texts.append(f"{head}\n{t}")
                info["read"] = True
                if how == "ocr":
                    info["ocr"] = True
                n_read += 1
        elif ext in IMAGE_EXTS and a.get("url"):
            images.append((info, a["url"]))
        infos.append(info)
    short = len((post.body or "").strip()) + sum(len(t) for t in texts) < OCR_BODY_SHORT
    if read and ocr is not None and short:
        todo = [(None, u) for u in getattr(post, "images", None) or []] + images
        todo = todo[:MAX_OCR_IMAGES]
        datas = [_image_bytes(u, http) for _, u in todo]
        try:
            outs = ocr.image_texts(datas) if any(datas) else [None] * len(todo)
        except Exception:                  # noqa: BLE001
            outs = [None] * len(todo)
        body_parts = []
        for (info, _u), t in zip(todo, outs):
            if not _enough(t):
                continue
            if info is None:
                body_parts.append(clean_ocr(t))
            else:
                texts.append(f"[첨부 OCR: {info['name']}]\n{clean_ocr(t)[:MAX_CHARS]}")
                info["read"] = info["ocr"] = True
        if body_parts:
            texts.insert(0, "[본문 이미지 OCR]\n" + "\n".join(body_parts)[:MAX_CHARS])
    return "\n\n".join(texts), infos, unread_count(infos) if read else 0


def needs_reread(row, version: int, body_short: Optional[int] = None) -> bool:
    """저장된 공지(notices 한 줄)를 지금 판으로 다시 읽으면 나아질까 — 본문이 이미지이거나 못 읽은 HWP·PDF·이미지 첨부가 있다.
    body_short = 본문이 이만큼 짧을 때만 첨부를 읽는 기능(F12)이면 그 길이."""
    keys = row.keys() if hasattr(row, "keys") else row
    if int((row["reader_ver"] if "reader_ver" in keys else 0) or 0) >= version:
        return False
    if body_short is not None and len((row["body"] or "").strip()) >= body_short and not row["image_only"]:
        return False
    try:
        atts = json.loads(row["attachments"] or "[]")
    except ValueError:
        atts = []
    want = (".hwp",) + ((".pdf",) + IMAGE_EXTS if version >= 3 else ())      # 판 2 는 HWP 만 새로 읽는다
    return (bool(row["image_only"]) and version >= 3) or any(not a.get("read") and a.get("ext") in want for a in atts)
