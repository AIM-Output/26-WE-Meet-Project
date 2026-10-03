"""테스트 공통 — 임시 data/ 와 **가짜 e클래스 수집 폴더**를 쓴다.

내 강의자료(F6_Eclass_agent/data)와 자료 목록(F4_Textbook_agent/data)을 건드리지 않는다.
네트워크에 닿는 코드가 아예 없다 — F4 는 파일을 내려받지 않는다.
"""
import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="f4test_"))
os.environ["F4_DATA_DIR"] = str(_TMP / "f4data")
os.environ["F6_AGENT_DIR"] = str(_TMP / "eclass")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

COURSES = [
    {"id": "100", "name": "운영체제[2] (CIS2001)", "url": "https://sel.jnu.ac.kr/course/view.php?id=100",
     "activities": [{"mod": "ubfile", "cmid": "11", "name": "os01 파일"},
                    {"mod": "ubboard", "cmid": "12", "name": "자료실 게시판"},
                    {"mod": "assign", "cmid": "13", "name": "과제1"}]},
    {"id": "200", "name": "컴퓨터네트워크[1] (ECE3026)", "url": "https://sel.jnu.ac.kr/course/view.php?id=200",
     "activities": [{"mod": "ubfile", "cmid": "21", "name": "1주차 수업자료 파일"}]},
]


# ---------------------------------------------------------------- 만들어 쓰는 파일

def make_pdf(pages: int = 2, with_font: bool = True) -> bytes:
    """페이지 객체를 세어 볼 수 있는 아주 작은 PDF (쪽수·글꼴 판정 시험용)."""
    body = [b"%PDF-1.4"]
    body.append(b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj")
    kids = " ".join(f"{i + 3} 0 R" for i in range(pages)).encode()
    body.append(b"2 0 obj << /Type /Pages /Count " + str(pages).encode() + b" /Kids [" + kids + b"] >> endobj")
    for i in range(pages):
        res = b"/Resources << /Font << /F1 << /Type /Font /BaseFont /Helvetica >> >> >>" if with_font else b""
        body.append(f"{i + 3} 0 obj << /Type /Page /Parent 2 0 R ".encode() + res + b" >> endobj")
    body.append(b"trailer << /Root 1 0 R >>")
    body.append(b"%%EOF")
    return b"\n".join(body)


def make_pptx(slides: int = 3) -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for i in range(1, slides + 1):
            z.writestr(f"ppt/slides/slide{i}.xml", "<p:sld/>")
        z.writestr("ppt/slideMasters/slideMaster1.xml", "<p:sldMaster/>")
    return buf.getvalue()


def make_docx(pages: int = 4, words: int = 120) -> bytes:
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("docProps/app.xml", f"<Properties><Pages>{pages}</Pages><Words>{words}</Words></Properties>")
    return buf.getvalue()


def eclass_file(rel: str, data: bytes) -> Path:
    """가짜 수집 폴더에 파일 하나 (rel 은 'data/<과목>/…' 모양)."""
    from textbook import config as C
    path = C.ECLASS_ROOT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def write_manifest(files: dict, posts: dict | None = None) -> None:
    from textbook import config as C
    C.ECLASS_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    C.ECLASS_MANIFEST.write_text(json.dumps({"files": files, "posts": posts or {}}, ensure_ascii=False),
                                 encoding="utf-8")
    C.ECLASS_COURSES.write_text(json.dumps(COURSES, ensure_ascii=False), encoding="utf-8")


def entry(path: str, course_id: str = "100", cmid: str = "11", activity: str = "os01 파일",
          post: str | None = None, at: str = "2026-09-13T00:24:26") -> dict:
    e = {"url": f"https://sel.jnu.ac.kr/pluginfile.php?file={path}", "path": path.replace("/", "\\"),
         "size": 0, "downloaded_at": at, "course_id": course_id,
         "course": next(c["name"] for c in COURSES if c["id"] == course_id), "cmid": cmid, "activity": activity}
    if post:
        e["post"] = post
    return e


# ---------------------------------------------------------------- 기본 자료 한 판

BASIC = {
    "/k1": entry("data/운영체제[2] (CIS2001)/os01 파일/os01_orientation.pdf"),
    "/k2": entry("data/운영체제[2] (CIS2001)/게시판/자료실 게시판/3주차 보충.pdf",
                 cmid="12", activity="자료실 게시판", post="3주차 수업 자료"),
    "/k3": entry("data/운영체제[2] (CIS2001)/과제/과제안내.docx", cmid="13", activity="과제1"),
    "/k4": entry("data/컴퓨터네트워크[1] (ECE3026)/1주차 수업자료 파일/Week1.pptx", course_id="200", cmid="21",
                 activity="1주차 수업자료 파일"),
}
CONTENT = {
    "/k1": lambda: make_pdf(18),
    "/k2": lambda: make_pdf(7),
    "/k3": lambda: make_docx(4),
    "/k4": lambda: make_pptx(9),
}


@pytest.fixture()
def eclass():
    """가짜 수집 결과 4건 (강의자료 · 게시판 첨부 · 과제 첨부 · 다른 과목)."""
    from textbook import config as C, store
    for p in Path(os.environ["F4_DATA_DIR"]).glob("textbook.db*"):
        p.unlink()
    store._initialized.clear()
    if C.ECLASS_ROOT.exists():
        import shutil
        shutil.rmtree(C.ECLASS_ROOT, ignore_errors=True)
    if C.UPLOAD_DIR.exists():
        import shutil
        shutil.rmtree(C.UPLOAD_DIR, ignore_errors=True)
    write_manifest(BASIC)
    for key, e in BASIC.items():
        eclass_file(e["path"].replace("\\", "/"), CONTENT[key]())
    yield BASIC


@pytest.fixture()
def db(eclass):
    from textbook import store
    with store.connect() as con:
        yield con
