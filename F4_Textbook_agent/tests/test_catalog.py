"""자료 목록 만들기 — 종류 가르기 · 주차 추정 · 스캔(새로/바뀜/사라짐/중복) (F4-R01·R05~R08)."""
import pytest

from textbook import catalog, config as C, store

from conftest import BASIC, eclass_file, entry, make_pdf, write_manifest


# ---------------------------------------------------------------- 종류·주차

def test_kind_by_activity_module():
    mods = {"11": "ubfile", "12": "ubboard", "13": "assign"}
    assert catalog.kind_of({"cmid": "11"}, mods) == "lecture"
    assert catalog.kind_of({"cmid": "12"}, mods) == "board"
    assert catalog.kind_of({"cmid": "13"}, mods) == "assignment"


def test_kind_falls_back_to_path_and_post():
    """courses.json 이 오래돼 활동을 못 찾아도 경로·글 제목으로 가른다."""
    assert catalog.kind_of({"cmid": "99", "post": "3주차 공지"}, {}) == "board"
    assert catalog.kind_of({"cmid": "99", "path": "data\\운영체제\\과제\\a.pdf"}, {}) == "assignment"
    assert catalog.kind_of({"cmid": "99", "path": "data\\운영체제\\게시판\\자료실\\a.pdf"}, {}) == "board"
    assert catalog.kind_of({"cmid": "99", "path": "data\\운영체제\\1주 파일\\a.pdf"}, {}) == "lecture"


@pytest.mark.parametrize("name,week", [
    ("3주차 수업 자료.pdf", 3),
    ("5주. 삼국지의 시대.pdf", 5),
    ("4강 git 기본사용법.pdf", 4),
    ("Week 2_2.ppt", 2),
    ("2-1_소프트웨어품질1 (38-완).pdf", 2),
    ("os04_process.pdf", 4),
    ("comnet05_L3.pdf", 5),
    ("1. 샘플_프로젝트정의서.hwp", None),      # '1.' 뒤가 빈칸이면 주차로 보지 않는다
    ("프로젝트 제안서 양식.docx", None),
    ("99주차 특강.pdf", None),                 # 20주를 넘는 값은 버린다
])
def test_week_guess(name, week):
    assert catalog.week_of(name)[0] == week


def test_week_uses_post_title_when_filename_is_plain():
    assert catalog.week_of("slides.pdf", "3주차 수업 자료")[0] == 3


# ---------------------------------------------------------------- 스캔

def test_scan_reads_manifest(db):
    s = catalog.scan(db)
    assert s["files"] == 4 and s["new"] == 4
    rows = {r["title"]: r for r in store.all_rows(db)}
    assert set(rows) == {"os01_orientation.pdf", "3주차 보충.pdf", "과제안내.docx", "Week1.pptx"}
    assert rows["os01_orientation.pdf"]["pages"] == 18
    assert rows["os01_orientation.pdf"]["kind"] == "lecture"
    assert rows["3주차 보충.pdf"]["kind"] == "board"
    assert rows["3주차 보충.pdf"]["post"] == "3주차 수업 자료"
    assert rows["과제안내.docx"]["kind"] == "assignment"
    assert rows["Week1.pptx"]["course_id"] == "200" and rows["Week1.pptx"]["pages"] == 9


def test_scan_is_idempotent_and_cheap(db):
    catalog.scan(db)
    again = catalog.scan(db)
    assert (again["new"], again["changed"], again["removed"], again["reread"]) == (0, 0, 0, 0)


def test_ensure_scan_skips_when_nothing_moved(db):
    catalog.ensure_scan(db)
    assert catalog.ensure_scan(db)["skipped"] is True
    # manifest 가 바뀌면 다시 훑는다
    m = dict(BASIC)
    m["/k5"] = entry("data/운영체제[2] (CIS2001)/os02 파일/os02.pdf", activity="os02 파일")
    eclass_file("data/운영체제[2] (CIS2001)/os02 파일/os02.pdf", make_pdf(5))
    write_manifest(m)
    out = catalog.ensure_scan(db)
    assert out["skipped"] is False and out["new"] == 1


def test_changed_file_is_read_again(db):
    catalog.scan(db)
    before = store.row(db, catalog.material_id("/k1"))
    eclass_file(BASIC["/k1"]["path"].replace("\\", "/"), make_pdf(30))
    s = catalog.scan(db)
    after = store.row(db, catalog.material_id("/k1"))
    assert s["changed"] == 1 and after["pages"] == 30
    assert after["content_hash"] != before["content_hash"]      # 바뀌면 다시 인덱싱할 근거 (F4-R07)


def test_files_are_placed_into_the_library(db):
    """수집분은 F4 보관함(data/materials)으로 들여온다 — 여기가 자료의 주인이다 (2026-09-30)."""
    catalog.scan(db)
    row = store.row(db, catalog.material_id("/k1"))
    assert row["root"] == "library"
    assert row["rel_path"] == "운영체제[2] (CIS2001)/os01 파일/os01_orientation.pdf"
    assert row["origin_path"].startswith("data/")
    assert row["stored"] in ("link", "copy")
    placed = C.LIBRARY_DIR / row["rel_path"]
    assert placed.is_file() and placed.stat().st_size > 0


def test_library_copy_survives_the_collect_cache(db):
    """F6 의 수집 캐시를 지워도 보관본으로 계속 열린다 (하드링크든 복사든)."""
    catalog.scan(db)
    catalog.abs_path("eclass", BASIC["/k1"]["path"].replace("\\", "/")).unlink()
    catalog.scan(db)
    row = store.row(db, catalog.material_id("/k1"))
    assert row["missing"] == 0 and row["pages"] == 18
    assert catalog.material_path(row).is_file()


def test_missing_when_the_library_copy_is_gone_too(db):
    catalog.scan(db)
    row = store.row(db, catalog.material_id("/k1"))
    catalog.material_path(row).unlink()
    catalog.abs_path("eclass", BASIC["/k1"]["path"].replace("\\", "/")).unlink()
    catalog.scan(db)
    assert store.row(db, catalog.material_id("/k1"))["missing"] == 1


def test_library_copy_is_refreshed_when_the_source_changes(db):
    catalog.scan(db)
    eclass_file(BASIC["/k1"]["path"].replace("\\", "/"), make_pdf(30))
    catalog.scan(db)
    row = store.row(db, catalog.material_id("/k1"))
    assert row["pages"] == 30 and catalog.material_path(row).is_file()


def test_deleted_library_copy_is_placed_again(db):
    catalog.scan(db)
    row = store.row(db, catalog.material_id("/k1"))
    catalog.material_path(row).unlink()
    catalog.scan(db)                                     # 원본이 남아 있으니 다시 들여온다
    assert catalog.material_path(store.row(db, catalog.material_id("/k1"))).is_file()


def test_entry_dropped_from_manifest_is_detached_not_deleted(db):
    """e클래스에서 내려간 자료도 보관본이 있으면 남긴다 — 이때만 사용자가 지울 수 있다."""
    catalog.scan(db)
    write_manifest({k: v for k, v in BASIC.items() if k != "/k4"})
    s = catalog.scan(db)
    row = store.row(db, catalog.material_id("/k4"))
    assert s["detached"] == 1 and s["removed"] == 0 and row["detached"] == 1
    assert catalog.scan(db)["detached"] == 0             # 다음 스캔에서 또 세지 않는다
    assert store.row(db, catalog.material_id("/k4")) is not None


def test_detached_material_comes_back(db):
    catalog.scan(db)
    write_manifest({k: v for k, v in BASIC.items() if k != "/k4"})
    catalog.scan(db)
    write_manifest(BASIC)
    catalog.scan(db)
    assert store.row(db, catalog.material_id("/k4"))["detached"] == 0


def test_row_is_removed_when_nothing_is_left(db):
    catalog.scan(db)
    row = store.row(db, catalog.material_id("/k4"))
    catalog.material_path(row).unlink()
    write_manifest({k: v for k, v in BASIC.items() if k != "/k4"})
    s = catalog.scan(db)
    assert s["removed"] == 1 and store.row(db, catalog.material_id("/k4")) is None


def test_same_content_marked_duplicate(db):
    """같은 파일이 두 곳(자료실·과제)에 올라와도 하나만 인덱싱한다 (F4 8절)."""
    m = dict(BASIC)
    same = make_pdf(18)                                          # /k1 과 같은 내용
    m["/k9"] = entry("data/운영체제[2] (CIS2001)/게시판/자료실 게시판/사본.pdf", cmid="12",
                     activity="자료실 게시판", post="다시 올립니다")
    eclass_file("data/운영체제[2] (CIS2001)/게시판/자료실 게시판/사본.pdf", same)
    write_manifest(m)
    catalog.scan(db)
    states = {r["title"]: (r["index_state"], r["dup_of"]) for r in store.all_rows(db)}
    dups = [t for t, (st, _) in states.items() if st == "duplicate"]
    assert len(dups) == 1 and states[dups[0]][1] is not None


def test_unsupported_and_scan_states(db):
    m = dict(BASIC)
    m["/kz"] = entry("data/운영체제[2] (CIS2001)/os01 파일/코드.zip")
    m["/kx"] = entry("data/운영체제[2] (CIS2001)/os01 파일/영상.mp4")     # 허용 확장자가 아니다 → 목록에 없다
    eclass_file("data/운영체제[2] (CIS2001)/os01 파일/코드.zip", b"PK\x03\x04zip")
    eclass_file("data/운영체제[2] (CIS2001)/os01 파일/영상.mp4", b"\x00\x00\x00 ftyp")
    write_manifest(m)
    catalog.scan(db)
    rows = {r["title"]: r for r in store.all_rows(db)}
    assert "영상.mp4" not in rows
    assert rows["코드.zip"]["index_state"] == "unsupported"


def test_scan_picks_up_uploads(db):
    up = C.UPLOAD_DIR / "100" / "6주차 필기.pdf"
    up.parent.mkdir(parents=True, exist_ok=True)
    up.write_bytes(make_pdf(6))
    catalog.scan(db)
    row = store.row(db, catalog.material_id("upload:100/6주차 필기.pdf"))
    assert row["source"] == "upload" and row["kind"] == "upload" and row["week"] == 6 and row["pages"] == 6


def test_abs_path_refuses_escape():
    with pytest.raises(ValueError):
        catalog.abs_path("upload", "../../etc/passwd")
    with pytest.raises(ValueError):
        catalog.abs_path("eclass", "data/../../secret.txt")


def test_updated_at_moves_only_when_something_changed(db):
    catalog.scan(db)
    stamp = store.updated_at(db)
    catalog.scan(db)
    assert store.updated_at(db) == stamp                         # 화면이 공연히 다시 부르지 않게
