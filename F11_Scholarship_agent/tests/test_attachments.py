"""첨부·이미지 읽기 (2026-10-25) — HWP 5.0 레코드 · 그림만 든 HWP · OCR(가짜 엔진) · 다시 읽기 · 판정 보류.

HWP 는 학교 첨부를 저장소에 넣지 않고 레코드를 손으로 만들어 시험한다(실제 첨부 6개로 따로 확인 — 표가 '칸 | 칸' 한 줄로 나온다).
OCR 은 OS 엔진을 띄우지 않는다(conftest UNIVUS_OCR=off) — image_texts·pdf_text 를 가진 가짜를 넘긴다. 진짜 Windows OCR 은 C0 테스트.
"""
import base64
import json
import sqlite3
import zlib
from types import SimpleNamespace

import pytest

from scholarship import attachments as A
from scholarship.sources.base import Post


# ── HWP 레코드 만들기 ───────────────────────────────────────

def rec(tag: int, level: int, payload: bytes) -> bytes:
    if len(payload) >= 0xFFF:
        return (tag | level << 10 | 0xFFF << 20).to_bytes(4, "little") + len(payload).to_bytes(4, "little") + payload
    return (tag | level << 10 | len(payload) << 20).to_bytes(4, "little") + payload


def para(text: str, level: int = 0) -> bytes:
    return rec(66, level, b"\0" * 22) + rec(67, level + 1, text.encode("utf-16-le"))


def cell(row: int, col: int, text: str, level: int = 2) -> bytes:
    head = (1).to_bytes(2, "little") + b"\0\0" + b"\0" * 4 + col.to_bytes(2, "little") + row.to_bytes(2, "little") + b"\0" * 20
    return rec(72, level, head) + rec(66, level, b"\0" * 22) + rec(67, level + 1, text.encode("utf-16-le"))


TABLE_CTRL = "\x0b" + "\0" * 7                    # 표 컨트롤 — 글자 8개 자리를 차지한다
SECTION = (para("2026년 하반기 ○○장학생 선발 공고\r")
           + para(TABLE_CTRL + "\r") + rec(71, 1, b"tbl ") + rec(77, 2, b"\0" * 20)
           + cell(0, 0, "신청기간") + cell(0, 1, "2026. 10. 1.(수) ~ 10. 20.(월)")
           + cell(1, 0, "지원자격") + cell(1, 1, "직전학기 평점 3.5 이상\r12학점 이상 이수")
           + para("문의 : 학생과 " + "062-530-1234\r"))


def test_hwp_section_text_tables_and_controls():
    t = A.hwp_section_text(SECTION)
    assert t.splitlines() == [
        "2026년 하반기 ○○장학생 선발 공고",
        "신청기간 | 2026. 10. 1.(수) ~ 10. 20.(월)",            # 표 한 행 = 한 줄 (기간 규칙이 한 줄을 본다)
        "지원자격 | 직전학기 평점 3.5 이상 12학점 이상 이수",      # 칸 안 줄바꿈은 띄어쓰기로
        "문의 : 학생과 062-530-1234",                          # 한글 전용 기호(사용자 영역 글자)는 지운다
    ]


def test_long_record_size():
    long = "가" * 3000                                         # 크기 칸이 0xFFF 를 넘으면 다음 4바이트가 크기
    assert A.hwp_section_text(para(long) + para("끝")) == long + "\n끝"


class FakeOle:
    def __init__(self, streams: dict[str, bytes]):
        self.streams = streams

    def exists(self, name):
        return name in self.streams

    def openstream(self, name):
        import io
        return io.BytesIO(self.streams["/".join(name) if isinstance(name, list) else name])

    def listdir(self):
        return [k.split("/") for k in self.streams]

    def close(self):
        pass


def header(flags: int) -> bytes:
    return b"HWP Document File".ljust(32, b"\0") + bytes([2, 2, 0, 5]) + flags.to_bytes(4, "little") + b"\0" * 216


def deflate(b: bytes) -> bytes:
    c = zlib.compressobj(wbits=-15)
    return c.compress(b) + c.flush()


@pytest.fixture
def fake_ole(monkeypatch):
    import olefile
    box = {}
    monkeypatch.setattr(olefile, "OleFileIO", lambda f: FakeOle(box["streams"]))
    return box


def test_read_hwp_compressed(fake_ole):
    fake_ole["streams"] = {"FileHeader": header(1), "BodyText/Section0": deflate(SECTION),
                           "BodyText/Section1": deflate(para("2쪽: 제출서류 — 재학증명서 1부"))}
    t = A.read_text(b"ole", ".hwp")
    assert "신청기간 | 2026. 10. 1.(수) ~ 10. 20.(월)" in t and t.rstrip().endswith("재학증명서 1부")


def test_read_hwp_distribution_uses_preview(fake_ole):
    """배포용 문서는 본문이 암호화돼 있다 — 미리보기 글자(PrvText)라도."""
    prv = "2026 배포용 공고문 미리보기 — 신청기간 : 2026. 10. 1. ~ 10. 20." .encode("utf-16-le")
    fake_ole["streams"] = {"FileHeader": header(1 | 4), "BodyText/Section0": b"encrypted", "PrvText": prv}
    assert A.read_text(b"ole", ".hwp").startswith("2026 배포용 공고문")


def test_hwp_images_and_broken_files(fake_ole):
    jpg = b"\xff\xd8\xff\xe0" + b"j" * 20000
    png = b"\x89PNG\r\n\x1a\n" + b"p" * 9000
    fake_ole["streams"] = {"FileHeader": header(1), "BodyText/Section0": deflate(b""),
                           "BinData/BIN0001.jpg": deflate(jpg), "BinData/BIN0002.png": png, "BinData/BIN0003.bmp": b"BM" + b"x" * 100}
    assert A.hwp_images(b"ole") == [jpg, png]                 # 큰 것부터 · 아주 작은 그림(아이콘)은 뺀다 · 압축 안 된 그림도
    assert A.read_text(b"not an ole file", ".pdf") is None
    fake_ole["streams"] = {"FileHeader": b"something else"}
    assert A.read_text(b"ole", ".hwp") is None and A.hwp_images(b"ole") == []


# ── OCR (가짜 엔진) ──────────────────────────────────────────

class FakeOcr:
    def __init__(self, image="", pdf=None):
        self.image, self.pdf, self.calls = image, pdf, []

    def image_texts(self, datas):
        self.calls.append(("image", len(datas)))
        return [f"{self.image} ({d[:5].decode('latin-1')})" if d else None for d in datas]

    def pdf_text(self, data, pages=3):
        self.calls.append(("pdf", pages))
        return self.pdf


class FakeHttp:
    def __init__(self, files):
        self.files, self.urls = files, []

    def download(self, url):
        self.urls.append(url)
        return self.files.get(url)


POSTER = ("2026 하반기 ○○재단 장학생 모집\n신정기간\n2026. 11. 11.(수)\n"
          "지원자격 : 직전학기 평점 3.5 이상(4.5 만점)\n十\n回\n제출서류 : 지원서 1부, 재학증명서 1부")


def test_clean_ocr_joins_label_lines():
    t = A.clean_ocr(POSTER)
    assert "신청기간 : 2026. 11. 11.(수)" in t.splitlines()
    assert "十" not in t and "回" not in t


def test_gather_reads_images_when_body_is_short():
    png = base64.b64encode(b"PNGDATA").decode()
    post = Post("1", "[장학안내] ○○재단 장학생 모집", "https://x.invalid/1", body="")
    post.images = ["https://x.invalid/poster.jpg", f"data:image/png;base64,{png}"]
    post.attachments = [{"name": "공고문.pdf", "url": "https://x.invalid/scan.pdf"},
                        {"name": "포스터2.jpg", "url": "https://x.invalid/p2.jpg"},
                        {"name": "명단.xlsx", "url": "https://x.invalid/a.xlsx"}]
    http = FakeHttp({"https://x.invalid/scan.pdf": b"%PDF-scanned", "https://x.invalid/poster.jpg": b"JPEG1",
                     "https://x.invalid/p2.jpg": b"JPEG2"})
    ocr = FakeOcr(image=POSTER, pdf="스캔 공고문 — 신청기간 : 2026. 11. 1. ~ 11. 11.")
    text, infos, unread = A.gather(post, http, max_read=3, ocr=ocr)
    assert text.startswith("[본문 이미지 OCR]\n2026 하반기")
    assert "[첨부 OCR: 공고문.pdf]\n스캔 공고문" in text and "[첨부 OCR: 포스터2.jpg]" in text
    assert "(PNGDA)" in text                                  # data: 주소 이미지는 받지 않고 바로
    assert A.has_ocr(text) and "[본문 이미지 OCR]" in A.ocr_part(text)
    assert [i["read"] for i in infos] == [True, True, False] and infos[0]["ocr"]
    assert unread == 1                                        # xlsx 만 못 읽음
    assert ("image", 3) in ocr.calls                          # 본문 이미지 2 + 이미지 첨부 1 을 한 번에


def test_gather_skips_ocr_for_long_body_and_without_engine():
    post = Post("2", "[장학안내] 장학생 모집", "https://x.invalid/2", body="신청기간 : 2026. 10. 1. ~ 10. 20.\n" * 20)
    post.images = ["https://x.invalid/poster.jpg"]
    post.attachments = [{"name": "공고.hwp", "url": "https://x.invalid/a.hwp"}]
    ocr = FakeOcr(image=POSTER)
    text, infos, unread = A.gather(post, FakeHttp({"https://x.invalid/a.hwp": b"broken"}), max_read=3, ocr=ocr)
    assert text == "" and ocr.calls == [] and unread == 1     # 본문이 길면 포스터는 읽지 않는다 · 깨진 HWP 는 못 읽음
    post.body = ""
    text, infos, unread = A.gather(post, FakeHttp({}), max_read=3, ocr=None)
    assert text == "" and unread == 1                         # OCR 이 없는 컴퓨터 — 이미지는 '못 읽음'으로 세지 않는다
    _, _, unread = A.gather(post, FakeHttp({}), max_read=3, read=False, ocr=ocr)
    assert unread == 0 and ocr.calls == []                    # F12 — 본문이 길어 첨부를 받지 않는 글


def test_needs_reread():
    row = {"reader_ver": 1, "image_only": 1, "body": "", "attachments": "[]"}
    assert A.needs_reread(row, 3) and not A.needs_reread(row, 2)          # 이미지 공지는 OCR 이 있을 때만
    row = {"reader_ver": 1, "image_only": 0, "body": "", "attachments": json.dumps([{"ext": ".hwp", "read": False}])}
    assert A.needs_reread(row, 2) and not A.needs_reread({**row, "reader_ver": 2}, 2)
    assert not A.needs_reread({**row, "body": "긴 본문" * 100}, 3, body_short=300)   # F12 — 본문이 길면 첨부를 안 읽는다
    assert not A.needs_reread({**row, "attachments": json.dumps([{"ext": ".hwp", "read": True}])}, 3)


# ── 추출·판정 ─────────────────────────────────────────────────

def test_ocr_lowers_confidence_and_holds_verdict(profile):
    from scholarship import extract, match
    text = "신청기간 : 2026. 10. 1. ~ 2026. 10. 20.\n지원자격 : 직전학기 평점 3.8 이상\n3학년 재학생"
    plain = extract.extract("[장학안내] ○○재단 장학생 선발", text, default_year=2026)
    ocr = extract.extract("[장학안내] ○○재단 장학생 선발", text, default_year=2026, ocr=True)
    assert ocr["ocr"] and ocr["confidence"] <= 0.55 < plain["confidence"]
    assert any("OCR" in n for n in ocr["notes"])
    today = __import__("datetime").date(2026, 10, 9)
    assert match.decide(plain, profile, today=today)["verdict"] == "ineligible"     # 평점 3.6 < 3.8
    d = match.decide(ocr, profile, today=today)
    assert d["verdict"] == "needs_review" and "OCR" in d["reasons"][0]["message"]   # OCR 은 숫자를 잘못 읽을 수 있다


# ── 저장소 · 수집 ─────────────────────────────────────────────

def test_old_db_gets_reader_ver_column():
    from scholarship import config as C, store
    C.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(C.DB_PATH)
    con.execute("CREATE TABLE notices (id TEXT PRIMARY KEY, source TEXT NOT NULL, source_name TEXT NOT NULL, unit_key TEXT, "
                "kind TEXT NOT NULL DEFAULT 'notice', title TEXT NOT NULL, url TEXT NOT NULL, posted_at TEXT, writer TEXT, "
                "category TEXT, body TEXT NOT NULL DEFAULT '', attach_text TEXT NOT NULL DEFAULT '', "
                "attachments TEXT NOT NULL DEFAULT '[]', image_only INTEGER NOT NULL DEFAULT 0, content_hash TEXT NOT NULL DEFAULT '', "
                "is_result INTEGER NOT NULL DEFAULT 0, title_key TEXT NOT NULL DEFAULT '', dup_of TEXT, req TEXT, "
                "extract_ver INTEGER NOT NULL DEFAULT 0, first_seen TEXT NOT NULL, fetched_at TEXT NOT NULL, changed_at TEXT)")
    con.execute("INSERT INTO notices(id, source, source_name, title, url, first_seen, fetched_at) "
                "VALUES ('www:9', 'jnu_scholarship', 't', '예전 공지', 'u', '2026-10-01', '2026-10-01')")
    con.commit()
    con.close()
    with store.connect() as con:
        assert store.notice(con, "www:9")["reader_ver"] == 0


def test_collect_rereads_old_image_notice(monkeypatch):
    from scholarship import collect, sources, store
    from conftest import add_notice
    posts = [Post("7", "[장학안내] ○○재단 장학생 모집", "https://x.invalid/7", "2026-10-07"),
             Post("8", "[장학안내] △△재단 장학생 모집", "https://x.invalid/8", "2026-10-07")]

    def fetch_detail(post, cfg, http):
        post.body, post.image_only, post.images = "", True, [f"https://x.invalid/{post.native_id}.jpg"]
        return post
    monkeypatch.setitem(sources.COLLECTORS, "fakeboard", SimpleNamespace(list_posts=lambda cfg, http, pages: list(posts),
                                                                        fetch_detail=fetch_detail))
    with store.connect() as con:
        for nid in ("www:7", "www:8"):
            add_notice(con, nid, posts[0].title if nid == "www:7" else posts[1].title, posted="2026-10-07")
            con.execute("UPDATE notices SET image_only = 1, reader_ver = ? WHERE id = ?", (1 if nid == "www:7" else 3, nid))
        store.put_source(con, "jnu_scholarship", last_ok_at="2026-10-08T06:00:00")
    monkeypatch.setattr(collect.C, "RECHECK_DAYS", 0)        # '최근 글 다시 보기'와 섞이지 않게
    http = FakeHttp({"https://x.invalid/7.jpg": b"JPEG7"})
    c = collect.collect_source({"key": "jnu_scholarship", "kind": "fakeboard", "site": "www", "filter": "all", "name": "t"},
                               http, {}, ocr=FakeOcr(image=POSTER))
    assert c["reread"] == 1 and http.urls == ["https://x.invalid/7.jpg"]     # 이미 판 3 으로 읽은 8 은 다시 받지 않는다
    with store.connect() as con:
        row = store.notice(con, "www:7")
        req = json.loads(row["req"])
    assert row["reader_ver"] == 3 and row["attach_text"].startswith("[본문 이미지 OCR]")
    assert req["ocr"] and req["period"]["end"].startswith("2026-11-11") and not req["needsOcr"]
