"""쪽수·텍스트 유무 읽기 (F4-S02 '13쪽' · F4-R06 'OCR 필요')."""
import zlib

from textbook import docmeta

from conftest import make_docx, make_pdf, make_pptx


def test_pdf_pages(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(13))
    m = docmeta.read(p)
    assert m["pages"] == 13
    assert m["textState"] == "text"
    assert not m["locked"]


def test_pdf_without_font_is_scan(tmp_path):
    """글꼴이 하나도 없으면 이미지만 있는 PDF — 요약을 만들어도 빈 내용이 된다 (F4-R06)."""
    p = tmp_path / "scan.pdf"
    p.write_bytes(make_pdf(4, with_font=False))
    m = docmeta.read(p)
    assert m["pages"] == 4
    assert m["textState"] == "none"


def test_pdf_encrypted(tmp_path):
    p = tmp_path / "lock.pdf"
    p.write_bytes(make_pdf(3).replace(b"trailer <<", b"trailer << /Encrypt 9 0 R"))
    m = docmeta.read(p)
    assert m["locked"] and m["pages"] is None


def test_pdf_pages_inside_object_stream(tmp_path):
    """압축 xref 를 쓰는 PDF 는 페이지 객체가 스트림 안에 있다 (2026-09-30 실측: 강의자료 3건이 그랬다)."""
    inner = b"<< /Type /Page >> " * 20 + b"/Type /Font /BaseFont /Malgun"
    blob = zlib.compress(inner)
    data = (b"%PDF-1.7\n1 0 obj << /Type /ObjStm /N 20 /Filter /FlateDecode >>\nstream\n"
            + blob + b"\nendstream endobj\ntrailer << /Root 1 0 R >>\n%%EOF")
    p = tmp_path / "objstm.pdf"
    p.write_bytes(data)
    m = docmeta.read(p)
    assert m["pages"] == 20
    assert m["textState"] == "text"


def test_pdf_count_fallback(tmp_path):
    """페이지 객체를 못 찾으면 페이지 트리의 /Count 를 쓴다."""
    data = b"%PDF-1.4\n2 0 obj << /Type /Pages /Count 42 >> endobj\ntrailer << >>\n%%EOF"
    p = tmp_path / "count.pdf"
    p.write_bytes(data)
    assert docmeta.read(p)["pages"] == 42


def test_not_a_pdf(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"not a pdf at all")
    m = docmeta.read(p)
    assert m["pages"] is None and m["error"]


def test_pptx_slides_and_docx_pages(tmp_path):
    a, b = tmp_path / "a.pptx", tmp_path / "b.docx"
    a.write_bytes(make_pptx(9))
    b.write_bytes(make_docx(7))
    assert docmeta.read(a)["pages"] == 9
    assert docmeta.read(b)["pages"] == 7


def test_docx_without_words_is_empty(tmp_path):
    p = tmp_path / "empty.docx"
    p.write_bytes(make_docx(1, words=0))
    assert docmeta.read(p)["textState"] == "none"


def test_unknown_ext_is_quiet(tmp_path):
    p = tmp_path / "a.hwp"
    p.write_bytes(b"HWP Document File")
    m = docmeta.read(p)
    assert m["pages"] is None and m["textState"] == "unknown" and not m["error"]


def test_missing_file(tmp_path):
    m = docmeta.read(tmp_path / "없는파일.pdf")
    assert m["error"] and m["pages"] is None


def test_hash_changes_with_content(tmp_path):
    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(2))
    first = docmeta.file_hash(p)
    p.write_bytes(make_pdf(3))
    assert docmeta.file_hash(p) != first
