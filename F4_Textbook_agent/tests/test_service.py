"""화면이 받는 모양 — 과목 요약 · 자료 한 줄 · 직접 추가 · 삭제 · 파일 열기 (F4-S01·S02·S05 · R02·R08)."""
import pytest

from textbook import catalog, config as C, service, store

from conftest import COURSES, make_pdf


def courses_getter():
    return [{"id": c["id"], "name": c["name"], "short": c["name"].split("[")[0], "code": "", "section": "",
             "color": "#4f46e5"} for c in COURSES]


def _scan(db):
    return catalog.scan(db)


# ---------------------------------------------------------------- 목록

def test_overview_groups_by_course(db):
    _scan(db)
    o = service.overview(db, courses_getter)
    assert [c["id"] for c in o["courses"]] == ["100", "200"]
    os_course = o["courses"][0]
    assert os_course["files"] == 3 and os_course["byKind"] == {"lecture": 1, "board": 1, "assignment": 1, "upload": 0}
    assert os_course["pages"] == 18 + 7 + 4
    assert os_course["color"] == "#4f46e5"                      # 색은 e클래스 과목 목록(F6)에서 받는다
    assert o["totals"]["files"] == 4 and o["totals"]["courses"] == 2
    assert o["analysis"]["available"] is False                  # 요약·문제·질문은 아직 없다


def test_overview_filters(db):
    _scan(db)
    assert len(service.overview(db, courses_getter, course="200")["materials"]) == 1
    assert len(service.overview(db, courses_getter, kind="board")["materials"]) == 1
    assert len(service.overview(db, courses_getter, q="week")["materials"]) == 1
    assert service.overview(db, courses_getter, course="200")["courses"][0]["files"] == 3   # 요약은 전부 그대로


def test_view_fields(db):
    _scan(db)
    row = store.row(db, catalog.material_id("/k1"))
    v = service.view(row)
    assert v["id"].startswith("mt:")
    assert (v["source"], v["kind"], v["kindLabel"]) == ("eclass", "lecture", "강의자료")
    assert v["pages"] == 18 and v["state"] == "pending" and v["stateLabel"] == "분석 대기"
    assert v["viewable"] and v["indexable"] and not v["canDelete"]        # e클래스 수집분은 삭제 잠금 (9-3)
    assert v["fileUrl"] == f"/api/materials/{v['id']}/file"
    assert v["downloadUrl"].endswith("?download=1")


def test_view_marks_scan_pdf(db):
    from conftest import eclass_file, BASIC
    eclass_file(BASIC["/k1"]["path"].replace("\\", "/"), make_pdf(9, with_font=False))
    _scan(db)
    v = service.view(store.row(db, catalog.material_id("/k1")))
    assert v["state"] == "ocr_needed" and not v["indexable"]
    assert v["note"] == "글자가 없는 이미지 PDF 입니다 — 요약·문제 생성에서 제외됩니다"
    # 조치할 것이 없으므로 '확인 필요' 로 세지 않는다 (2026-10-01)
    assert service.status_summary(db)["attention"] == 0
    assert all(c["attention"] == 0 for c in service.overview(db)["courses"])


def test_status_summary(db):
    _scan(db)
    s = service.status_summary(db)
    assert s["available"] and s["files"] == 4 and s["pages"] == 18 + 7 + 4 + 9 and s["courses"] == 2


# ---------------------------------------------------------------- 직접 추가

def test_upload_target_and_finish(db):
    _scan(db)
    dest = service.upload_target(db, "100", "보충자료.pdf", courses_getter)
    dest.write_bytes(make_pdf(3))
    m = service.finish_upload(db, dest, courses_getter)
    assert m["source"] == "upload" and m["kindLabel"] == "직접 추가" and m["pages"] == 3 and m["canDelete"]
    assert dest.parent == C.UPLOAD_DIR / "100"


def test_upload_rejects_bad_input(db):
    _scan(db)
    with pytest.raises(service.Invalid):
        service.upload_target(db, "100", "바이러스.exe", courses_getter)
    with pytest.raises(service.Invalid):
        service.upload_target(db, "../etc", "a.pdf", courses_getter)
    with pytest.raises(service.Invalid):
        service.upload_target(db, "999", "a.pdf", courses_getter)       # 모르는 과목
    with pytest.raises(service.Invalid):
        service.upload_target(db, "", "a.pdf", courses_getter)


def test_upload_name_is_sanitized_and_deduped(db):
    _scan(db)
    dest = service.upload_target(db, "100", "../../몰래.pdf", courses_getter)
    assert dest.parent == C.UPLOAD_DIR / "100" and dest.name == "몰래.pdf"
    dest.write_bytes(make_pdf(1))
    second = service.upload_target(db, "100", "몰래.pdf", courses_getter)
    assert second.name == "몰래 (2).pdf"


# ---------------------------------------------------------------- 삭제·파일

def test_delete_only_uploads(db):
    _scan(db)
    with pytest.raises(service.Conflict):
        service.delete(db, catalog.material_id("/k1"))              # e클래스 수집분 (F4-R08 · 9-3)
    dest = service.upload_target(db, "100", "내필기.pdf", courses_getter)
    dest.write_bytes(make_pdf(2))
    m = service.finish_upload(db, dest, courses_getter)
    service.delete(db, m["id"])
    assert store.row(db, m["id"]) is None and not dest.exists()


def test_delete_detached_material(db):
    """e클래스에서 내려간 보관본은 내 것이므로 지울 수 있다 (2026-09-30)."""
    from conftest import BASIC, write_manifest
    _scan(db)
    write_manifest({k: v for k, v in BASIC.items() if k != "/k4"})
    _scan(db)
    mid = catalog.material_id("/k4")
    v = service.view(store.row(db, mid))
    assert v["detached"] and v["canDelete"] and "내려갔" in v["note"]
    path = catalog.material_path(store.row(db, mid))
    service.delete(db, mid)
    assert store.row(db, mid) is None and not path.exists()


def test_view_says_where_the_file_is_kept(db):
    _scan(db)
    v = service.view(store.row(db, catalog.material_id("/k1")))
    assert v["stored"] in ("link", "copy") and not v["detached"]
    d = service.detail(db, catalog.material_id("/k1"))
    assert "materials" in d["path"] and d["originPath"].endswith("os01_orientation.pdf")


def test_delete_unknown(db):
    with pytest.raises(service.NotFound):
        service.delete(db, "mt:없는것")


def test_file_target(db):
    _scan(db)
    path, name, mime = service.file_target(db, catalog.material_id("/k1"))
    assert path.is_file() and name == "os01_orientation.pdf" and mime == "application/pdf"


def test_file_target_when_file_vanished(db):
    _scan(db)
    path, _, _ = service.file_target(db, catalog.material_id("/k1"))
    path.unlink()
    with pytest.raises(service.NotFound):
        service.file_target(db, catalog.material_id("/k1"))


def test_detail_lists_same_activity(db):
    from conftest import BASIC, eclass_file, entry, write_manifest
    m = dict(BASIC)
    m["/k1b"] = entry("data/운영체제[2] (CIS2001)/os01 파일/os01_부록.pdf")
    eclass_file("data/운영체제[2] (CIS2001)/os01 파일/os01_부록.pdf", make_pdf(2))
    write_manifest(m)
    _scan(db)
    d = service.detail(db, catalog.material_id("/k1"))
    assert [x["title"] for x in d["sameActivity"]] == ["os01_부록.pdf"]
    assert d["path"].endswith("os01_orientation.pdf")


def test_media_types():
    assert service.media_type(".pdf") == "application/pdf"
    assert service.media_type(".hwp") == "application/x-hwp"
    assert service.media_type(".unknown") == "application/octet-stream"
