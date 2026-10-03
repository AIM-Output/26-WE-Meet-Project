"""새 글·자료 (공지 · 자료실 글 · 강의자료) — manifest.json 에서 만들고, 처음은 기준선, 새로 보이면 알린다."""
import json
from datetime import datetime

from conftest import COURSES, FakePush

from eclass import config as C
from eclass import feed

NOW = datetime(2026, 10, 3, 12, 0)
LATER = datetime(2026, 10, 3, 16, 0)


def write_manifest(posts=(), files=()):
    """수집기가 쓰는 모양 — posts: (bwid, 게시판, 제목, 본문) / files: (cmid, 파일 이름, mod)."""
    C.DATA_DIR.mkdir(parents=True, exist_ok=True)
    course = COURSES[0]
    acts = []
    m = {"files": {}, "posts": {}}
    for bwid, board, title, body in posts:
        rel = f"data\\{course['name']}\\게시판\\{board}\\2026-10-02_{title}.md"
        p = C.DATA_DIR.parent / rel.replace("\\", "/")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join([f"# {title}", "", f"- 과목: {course['name']}", f"- 게시판: {board}", "- 작성자: 교수",
                                "- 작성일: 2026-10-02 10:00", "", "## 본문", "", body, ""]), encoding="utf-8")
        cmid = "1446165" if "공지" in board else "1446167"
        m["posts"][f"{cmid}:{bwid}"] = {"url": f"https://sel.jnu.ac.kr/mod/ubboard/article.php?id={cmid}&bwid={bwid}", "path": rel,
                                         "title": title, "date": ":\r\n\t\t2026-10-02 10:00", "attachments": [],
                                         "fetched_at": "2026-10-02T12:00:00", "course_id": course["id"], "course": course["name"],
                                         "cmid": cmid, "activity": board, "post": title}
        acts.append({"mod": "ubboard", "cmid": cmid, "name": board})
    for cmid, name, mod in files:
        key = f"/1/mod_{mod}/content/0/{name}"
        sub = "과제" if mod == "assign" else "수업자료"
        m["files"][key] = {"url": "https://sel.jnu.ac.kr/pluginfile.php?file=" + key, "path": f"data\\{course['name']}\\{sub}\\{name}",
                           "size": 2048, "downloaded_at": "2026-10-02T12:00:00", "uploaded_at": "2026-10-01T13:15:48", "course_id": course["id"], "course": course["name"],
                           "cmid": cmid, "activity": sub}
        acts.append({"mod": mod, "cmid": cmid, "name": sub})
    C.MANIFEST_FILE.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    C.COURSES_FILE.write_text(json.dumps([{**course, "activities": acts}], ensure_ascii=False), encoding="utf-8")


def test_first_sync_is_baseline_then_new_items_alert(db):
    write_manifest([("1", "공지사항 게시판", "강의실 변경 안내", "본문")], [("900", "week1.pdf", "ubfile")])
    r = feed.sync(db, NOW)
    assert (r["new"], r["baseline"]) == (0, 2)
    assert feed.summary(db)["unread"] == 0                       # 이미 있던 것은 읽음으로 — 알림 폭탄 없음
    assert feed.deliver(db, FakePush(), NOW) == 0
    write_manifest([("1", "공지사항 게시판", "강의실 변경 안내", "본문"), ("2", "공지사항 게시판", "중간고사 일정", "10월 21일 화요일"),
                    ("3", "자료실 게시판", "5주차 자료", "첨부 확인")],
                   [("900", "week1.pdf", "ubfile"), ("901", "week5.ppt", "ubfile"), ("902", "답안.hwp", "assign")])
    assert feed.sync(db, LATER)["new"] == 3                      # 공지 1 · 자료실 글 1 · 강의자료 1 (과제 첨부는 빼고)
    out = feed.list_items(db)
    assert out["counts"] == {"all": 5, "unread": 3, "notice": 2, "board": 1, "material": 2}
    assert sum(i["isNew"] for i in out["items"]) == 3
    assert [i["excerpt"] for i in out["items"] if i["title"] == "중간고사 일정"] == ["10월 21일 화요일"]
    p = FakePush()
    assert feed.deliver(db, p, NOW) == 2
    (notice,) = [v for k, v in p.rows.items() if k.startswith("ec-post:")]
    assert notice["title"] == "공지 · 운영체제 · 중간고사 일정" and notice["kind"] == "eclass" and "10월 21일" in notice["body"]
    bundle = p.rows["ec-new:2026-10-03"]          # first_seen 날짜로 묶는다
    assert bundle["title"] == "새 글·자료 2건" and "5주차 자료" in bundle["body"] and "week5.ppt" in bundle["body"]
    assert feed.deliver(db, p, NOW) == 0                         # 다시 보내지 않는다


def test_read_marks_and_settings(db):
    write_manifest([("1", "공지사항 게시판", "안내", "본문")])
    feed.sync(db, NOW)
    write_manifest([("1", "공지사항 게시판", "안내", "본문"), ("2", "공지사항 게시판", "휴강 공지", "휴강합니다")])
    feed.sync(db, NOW)
    item = feed.list_items(db, unread=True)["items"][0]
    assert feed.detail(db, item["id"])["body"] == "휴강합니다"
    feed.save_settings(db, notices=False)
    assert feed.deliver(db, FakePush(), NOW) == 0                # 공지 알림 끔
    assert feed.mark_read(db, [item["id"]]) == 1 and feed.summary(db)["unread"] == 0
    feed.mark_read(db, [item["id"]], read=False)
    assert feed.summary(db)["unreadNotices"] == 1
    assert feed.mark_read(db) == 1


def test_unchanged_manifest_is_skipped(db):
    write_manifest([("1", "공지사항 게시판", "안내", "본문")])
    assert feed.sync(db, NOW)["skipped"] is False
    assert feed.sync(db, NOW)["skipped"] is True


def test_material_time_is_eclass_upload_time(db):
    """강의자료는 받은 시각이 아니라 e클래스에 올린 시각(Last-Modified)으로 보인다."""
    write_manifest([], [("900", "week5.ppt", "ubfile")])
    feed.sync(db, NOW)
    (it,) = feed.list_items(db)["items"]
    assert (it["postedAt"], it["fetchedAt"]) == ("2026-10-01T13:15:48", "2026-10-02T12:00:00")
