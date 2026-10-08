"""화면이 쓰는 모양 — 시험 목록 · 계획 미리보기/등록 · 진도 · 재조정 · 캘린더 연동.

계산은 전부 여기(백엔드)에서 한다. 화면은 받은 대로 그린다 (Frontend-Route 10절).
날짜 나누기 자체는 `plan.compute`(순수 함수)가 하고, 여기서는 **원천을 모아 넣고 저장하는 일**을 한다.

지키는 것
  - 미리보기는 저장하지 않는다. `create_plan` 만 캘린더에 블록을 만든다 (F5 D3).
  - 재조정은 **제안만** 돌려준다. 사용자가 다시 `create_plan` 을 불러야 캘린더가 바뀐다 (F5 5절).
  - 공지에서 온 시험을 사용자가 고치면(edited) 재수집이 덮어쓰지 않는다 (F5-R03).
  - 계획을 취소하면 **완료하지 않은 블록만** 지운다 — 완료한 기록은 남는다 (F5-R35).
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import date, timedelta
from typing import Any, Callable, Optional

from . import config as C
from . import academic, defaults, notices, plan as P, scope, store

CoursesGetter = Callable[[], list[dict]]
Notify = Callable[[dict], None]

WEEKDAYS = P.WEEKDAYS
_COURSE = re.compile(r"^(?P<short>.*?)\s*(?:\[(?P<section>[^\]]*)\])?\s*(?:\((?P<code>[^)]*)\))?\s*$")

STATUS_LABEL = {"confirmed": "확인됨", "review": "확인 필요"}
SOURCE_LABEL = {"notice": "공지에서 찾음", "manual": "직접 추가", "auto": "임의 일정"}
PLAN_STATE_LABEL = {"draft": "미리보기", "active": "진행 중", "done": "완료", "canceled": "취소됨"}
DAY_KIND_LABEL = {"study": "학습", "review": "마무리 복습", "excluded": "제외일"}


class Invalid(ValueError):
    """사용자 입력이 규칙에 어긋난다 (422)."""


class NotFound(LookupError):
    """그런 시험·계획이 없다 (404)."""


class Conflict(RuntimeError):
    """지금은 할 수 없다 — 이미 등록된 계획, 이미 차 있는 날짜 등 (409)."""


# ---------------------------------------------------------------- 과목 · 학기

def _date(v, what: str) -> str:
    """plan.date_str 을 이 폴더의 오류형으로 올려 준다 — api 가 422 로 바꾼다."""
    try:
        return P.date_str(v, what)
    except P.Invalid as e:
        raise Invalid(str(e))


def _split_course(name: str) -> dict:
    m = _COURSE.match((name or "").strip())
    g = m.groupdict() if m else {}
    return {"short": (g.get("short") or name or "").strip(), "code": (g.get("code") or "").strip(),
            "section": (g.get("section") or "").strip()}


def _courses_from_file() -> list[dict]:
    """명령줄에서 직접 읽을 때 — 대시보드에서는 백엔드가 같은 모양을 넘겨준다."""
    try:
        raw = json.loads(C.ECLASS_COURSES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for i, c in enumerate(raw if isinstance(raw, list) else []):
        parts = _split_course(c.get("name", ""))
        out.append({"id": str(c.get("id", i)), "name": c.get("name", ""), **parts,
                    "color": C.COURSE_PALETTE[i % len(C.COURSE_PALETTE)]})
    return out


def course_map(get_courses: Optional[CoursesGetter] = None) -> dict[str, dict]:
    try:
        rows = list(get_courses() or []) if get_courses else _courses_from_file()
    except Exception:                                   # noqa: BLE001 — 과목 목록을 못 받아도 시험은 보여 준다
        rows = []
    out: dict[str, dict] = {}
    for i, c in enumerate(rows):
        cid = str(c.get("id", i))
        parts = _split_course(c.get("name", "")) if not c.get("short") else {}
        out[cid] = {"id": cid, "name": c.get("name", ""),
                    "short": c.get("short") or parts.get("short") or c.get("name", ""),
                    "code": c.get("code") or parts.get("code") or "",
                    "section": c.get("section") or parts.get("section") or "",
                    "color": c.get("color") or C.COURSE_PALETTE[i % len(C.COURSE_PALETTE)]}
    return out


def _course_of(row: Any, courses: dict[str, dict]) -> dict:
    cid = row["course_id"]
    known = courses.get(cid)
    if known:
        return known
    parts = _split_course(row["course"] or cid)
    return {"id": cid, "name": row["course"] or cid, "color": "#64748b", **parts}


def semester_of(d: date) -> str:
    """날짜가 속한 정규 학기 id — 3~8월 1학기, 9~2월 2학기 (F3 와 같은 규칙)."""
    if 3 <= d.month <= 8:
        return f"{d.year}-1"
    return f"{d.year if d.month >= 9 else d.year - 1}-2"


def semester_label(sid: str) -> str:
    y, _, t = sid.partition("-")
    return f"{y}-{t}학기" if t in ("1", "2") else sid


def semester_span(sid: str) -> tuple[str, str]:
    """학기의 대략 범위 — 시험 목록을 거르는 데만 쓴다(개강·종강은 F1 이 갖고 있다)."""
    if not re.match(r"^\d{4}-[12]$", sid or ""):
        raise Invalid(f"학기 형식이 잘못됐습니다: {sid!r} (예: 2026-2)")
    y, t = int(sid[:4]), sid[-1]
    if t == "1":
        return f"{y}-03-01", f"{y}-08-31"
    return f"{y}-09-01", f"{y + 1}-02-29" if _leap(y + 1) else f"{y + 1}-02-28"


def _leap(y: int) -> bool:
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


# ---------------------------------------------------------------- 공지에서 시험 찾기 (F5-R01~R03)

def ensure_sync(con: sqlite3.Connection, today: Optional[date] = None,
                notify: Optional[Notify] = None,
                get_courses: Optional[CoursesGetter] = None) -> Optional[dict]:
    """공지 목록(manifest.json)이 **바뀌었을 때만** 다시 읽는다 (F4 catalog.ensure_scan 과 같은 방식).

    대시보드가 1분마다 상태를 부르는데 그때마다 공지 18건을 다시 파싱할 이유가 없다.
    새 시험 공지가 올라오면 사용자가 아무 것도 누르지 않아도 '확인 필요'에 들어온다 (F5-R01)."""
    found = notices.load(today=today or date.today())
    if not found["available"] or found["stamp"] == store.get_meta(con, "notice_stamp"):
        return None
    return sync_notices(con, today, notify, get_courses)


def exam_id(course_id: str, exam_type: str, exam_date: str) -> str:
    """`ex:<과목>:<해시8>` (F5 6절).

    중간·기말은 과목마다 하나다 → 해시에 날짜를 넣지 않는다. 그래서 공지가 날짜를 고쳐 다시 올라와도
    **같은 시험**으로 갱신되고 '연기'로 감지된다 (F5 8절). 퀴즈·발표는 여러 번 있을 수 있어 날짜까지 넣는다.
    """
    base = f"{course_id}|{exam_type}" if exam_type in C.SINGLETON_TYPES else f"{course_id}|{exam_type}|{exam_date}"
    return f"ex:{course_id}:{hashlib.sha1(base.encode('utf-8')).hexdigest()[:8]}"


def sync_notices(con: sqlite3.Connection, today: Optional[date] = None,
                 notify: Optional[Notify] = None, get_courses: Optional[CoursesGetter] = None) -> dict:
    """e클래스 공지를 다시 읽어 시험을 넣거나 갱신한다. 사용자가 손댄 것·지운 것은 건드리지 않는다.

    돌려주는 것: {available, stamp, posts, new, updated, postponed: [...], hints: [...], reviewCount}
    """
    today = today or date.today()
    found = notices.load(today=today)
    if not found["available"]:
        return {"available": False, "stamp": None, "posts": 0, "new": 0, "updated": 0,
                "postponed": [], "hints": [], "error": f"e클래스 게시판 목록이 없습니다: {C.ECLASS_MANIFEST}"}

    courses = course_map(get_courses)
    manual = {(r["course_id"], r["date"]): r["id"] for r in store.exam_rows(con) if r["source"] == "manual"}
    new = updated = 0
    postponed: list[dict] = []
    confirmed: list[dict] = []                                  # 임의 일정 → 공지의 진짜 일정
    hints: list[dict] = []
    stamp = store.now()

    for cid, slot in found["byCourse"].items():
        hints += [{**h, "courseId": cid, "course": courses.get(cid, {}).get("short", cid)} for h in slot["hints"]]
        for e in slot["exams"]:
            eid = exam_id(cid, e["type"], e["date"])
            cur = store.exam(con, eid, include_removed=True)
            if cur is not None and cur["removed_at"]:
                continue                                        # 사용자가 지운 것은 되살리지 않는다
            if cur is None and (cid, e["date"]) in manual:
                continue                                        # 같은 과목·같은 날짜의 수기 시험이 있다 — 수기가 이긴다 (F5 8절)
            row = {
                "id": eid, "course_id": cid, "course": courses.get(cid, {}).get("name", "") or e.get("course", ""),
                "type": e["type"], "title": e["title"], "date": e["date"], "time": e["time"],
                "end_time": e["endTime"], "place": e["place"],
                "scope_weeks": store.jdump(e["scopeWeeks"]), "scope_ids": store.jdump([]),
                "scope_note": e["scopeNote"], "source": "notice",
                "evidence": store.jdump(e["evidence"]), "confidence": e["confidence"], "status": e["status"],
                "notice_key": e["noticeKey"], "notice_url": e["noticeUrl"], "posted_at": e["postedAt"],
                "edited": 0, "changed": "", "removed_at": None, "added_at": stamp, "seen_at": stamp,
            }
            if cur is None:
                store.upsert_exam(con, row)
                new += 1
                continue

            if cur["source"] == "auto":
                # 수업평가 기간·수업 요일로 임의로 잡아 둔 자리에 진짜 일정이 나왔다 — 공지 값으로 바꾼다 (defaults.py 4).
                # 사용자가 임의 일정에 넣어 둔 범위·장소는 공지에 없으면 살린다.
                row["added_at"] = cur["added_at"]
                row["note"] = ""
                if not e["place"]:
                    row["place"] = cur["place"]
                if not e["scopeWeeks"] and not e["scopeNote"]:
                    row["scope_weeks"], row["scope_ids"], row["scope_note"] = cur["scope_weeks"], cur["scope_ids"], cur["scope_note"]
                if (cur["date"], cur["time"]) != (e["date"], e["time"]):
                    row["changed"] = store.jdump({"field": "date", "from": cur["date"], "to": e["date"],
                                                  "at": stamp, "kind": "confirmed"})
                store.upsert_exam(con, row)
                updated += 1
                confirmed.append({"examId": eid, "courseId": cid, "course": courses.get(cid, {}).get("short", cid),
                                  "type": e["type"], "typeLabel": C.type_label(e["type"]),
                                  "from": cur["date"], "to": e["date"], "time": e["time"],
                                  "planned": store.active_plan(con, eid) is not None})
                continue

            if not e["time"] and cur["time_auto"] and cur["time"]:
                # 공지에는 여전히 시각이 없다 — 수업 시간으로 채워 둔 값을 지키지 않으면 수집마다 비웠다 채웠다 한다
                row["time"], row["end_time"] = cur["time"], cur["end_time"]
            if cur["edited"]:
                store.update_exam(con, eid, {"seen_at": stamp})
                continue                                        # 사용자가 고친 것은 덮어쓰지 않는다 (F5-R03)
            if e["postedAt"] < (cur["posted_at"] or ""):
                # 더 오래된 공지다 — 근거만 보태고 값은 그대로 둔다
                store.update_exam(con, eid, {"evidence": store.jdump(_merge_evidence(cur, e)), "seen_at": stamp})
                continue

            row["added_at"] = cur["added_at"]
            row["evidence"] = store.jdump(_merge_evidence(cur, e))
            if cur["date"] != e["date"]:                        # 시험 연기·변경 (F5 8절)
                change = {"field": "date", "from": cur["date"], "to": e["date"], "at": stamp}
                row["changed"] = store.jdump(change)
                postponed.append({"examId": eid, "courseId": cid,
                                  "course": courses.get(cid, {}).get("short", cid),
                                  "type": e["type"], "typeLabel": C.type_label(e["type"]),
                                  **{k: change[k] for k in ("from", "to")}})
            elif cur["confidence"] > e["confidence"] and cur["status"] == "confirmed":
                # 더 확실한 근거가 이미 있다 — 신뢰도·상태를 낮추지 않는다
                row["confidence"] = cur["confidence"]
                row["status"] = cur["status"]
                row["changed"] = cur["changed"]
            else:
                row["changed"] = cur["changed"]
            if _differs(cur, row):
                store.upsert_exam(con, row)
                updated += 1
            else:
                store.update_exam(con, eid, {"seen_at": stamp, "evidence": row["evidence"]})

    if new or updated or postponed:
        store.touch(con)
    store.set_meta(con, notice_stamp=found["stamp"], notice_synced_at=stamp)
    _notify_postponed(postponed, notify)
    _notify_confirmed(confirmed, notify)
    review = sum(1 for r in store.exam_rows(con) if r["status"] == "review")
    return {"available": True, "stamp": found["stamp"], "posts": found["posts"], "new": new, "updated": updated,
            "postponed": postponed, "confirmed": confirmed, "hints": hints, "reviewCount": review, "syncedAt": stamp}


_WATCHED = ("date", "time", "end_time", "place", "scope_note", "scope_weeks", "title",
            "confidence", "status", "notice_key", "notice_url", "posted_at")


def _differs(cur: Any, row: dict) -> bool:
    return any(str(cur[k]) != str(row[k]) for k in _WATCHED)


def _merge_evidence(cur: Any, e: dict) -> list[dict]:
    """근거 원문은 쌓는다 — 같은 시험을 두 공지가 말하면 둘 다 볼 수 있어야 한다 (F5 9절 '신뢰')."""
    out = store.jload(cur["evidence"], [])
    seen = {(x.get("quote"), x.get("url")) for x in out if isinstance(x, dict)}
    for ev in e["evidence"]:
        if (ev["quote"], ev["url"]) not in seen:
            out.append(ev)
    return out[:8]


def _notify_postponed(postponed: list[dict], notify: Optional[Notify]) -> None:
    if not notify:
        return
    for p in postponed:
        _safe_notify(notify, {
            "kind": "exam", "refId": p["examId"],
            "title": f"{p['course']} {p['typeLabel']} 날짜가 바뀌었습니다",
            "body": f"{_md(p['from'])} → {_md(p['to'])} · 계획을 다시 만드세요",
            "href": f"/exams?exam={p['examId']}&step=options", "at": store.now(),
        })


def _notify_confirmed(confirmed: list[dict], notify: Optional[Notify]) -> None:
    """임의 일정 자리에 공지의 진짜 일정이 들어왔다 — 계획을 등록해 뒀으면 다시 만들라고 한다."""
    if not notify:
        return
    for p in confirmed:
        when = f"{_md(p['to'])}{' ' + p['time'] if p['time'] else ''}"
        moved = p["from"] != p["to"]
        _safe_notify(notify, {
            "kind": "exam", "refId": p["examId"],
            "title": f"{p['course']} {p['typeLabel']} 일정이 나왔습니다",
            "body": f"{when}" + (f" · 임의로 잡아 둔 {_md(p['from'])} 대신" if moved else "")
                    + (" · 계획을 다시 만드세요" if p["planned"] and moved else ""),
            "href": f"/exams?exam={p['examId']}" + ("&step=options" if p["planned"] and moved else ""),
            "at": store.now(),
        })


def _notify_created(created: list[dict], notify: Optional[Notify]) -> None:
    """임의 일정을 새로 잡았다 — 학기 첫 중간고사 묶음, 중간고사 뒤의 기말고사 묶음을 한 줄로 알린다."""
    if not notify or not created:
        return
    for kind in C.DEFAULT_EXAM_TYPES:
        items = [x for x in created if x["type"] == kind]
        if not items:
            continue
        name = C.type_label(kind)
        first = min(x["date"] for x in items)
        _safe_notify(notify, {
            "kind": "exam", "refId": f"auto:{kind}:{first}",
            "title": f"{name} 일정을 {len(items)}과목 임의로 잡았습니다",
            "body": f"{', '.join(x['course'] for x in items[:4])}{' 외' if len(items) > 4 else ''} · "
                    f"수업평가 기간의 수업 요일 기준 — 공지가 나오면 바뀝니다",
            "href": "/exams", "at": first,
        })


def _safe_notify(notify: Optional[Notify], alert: dict) -> None:
    if not notify:
        return
    try:
        notify(alert)
    except Exception:                                   # noqa: BLE001 — 알림 센터 문제로 본 작업이 막히지 않게
        pass


# ---------------------------------------------------------------- 시험 한 줄 보기

def exam_view(row: Any, courses: dict[str, dict], today: date,
              plan_row: Optional[Any] = None, days: Optional[list[Any]] = None,
              scope_info: Optional[dict] = None) -> dict:
    c = _course_of(row, courses)
    d = date.fromisoformat(row["date"])
    dday = (d - today).days
    weeks = store.jload(row["scope_weeks"], [])
    ids = store.jload(row["scope_ids"], [])
    out = {
        "id": row["id"], "courseId": row["course_id"], "courseName": c["name"], "course": c["short"],
        "courseCode": c["code"], "section": c["section"], "color": c["color"],
        "type": row["type"], "typeLabel": C.type_label(row["type"]),
        "title": row["title"] or C.type_label(row["type"]),
        "date": row["date"], "weekday": WEEKDAYS[d.weekday()],
        "time": row["time"], "endTime": row["end_time"], "timeUnknown": not row["time"],
        "timeFromClass": bool(row["time_auto"]) if "time_auto" in row.keys() else False,   # 시각 미정 → 수업 시간
        "confirmed": is_confirmed(row),
        "place": row["place"],
        "dday": dday, "ddayLabel": _dday(dday), "past": dday < 0, "soon": 0 <= dday <= 7,
        "scope": {"weeks": weeks, "materialIds": ids, "note": row["scope_note"],
                  "specified": bool(weeks or ids or row["scope_note"])},
        "source": row["source"], "sourceLabel": SOURCE_LABEL.get(row["source"], row["source"]),
        # 임의 일정 — 학사일정 평가 기간·수업 요일로 잡아 둔 자리. 공지가 나오면 바뀌고, 직접 고칠 수도 있다
        "isAuto": row["source"] == "auto",
        "note": row["note"] if "note" in row.keys() else "",
        "status": row["status"], "statusLabel": STATUS_LABEL.get(row["status"], row["status"]),
        "needsReview": row["status"] == "review",
        "confidence": round(row["confidence"], 2),
        "evidence": store.jload(row["evidence"], []),
        "noticeUrl": row["notice_url"], "postedAt": row["posted_at"],
        "edited": bool(row["edited"]),
        "changed": store.jload(row["changed"], {}) or None,
        "canDelete": True,
        "addedAt": row["added_at"],
        # 발표는 준비 완료만 체크한다 (2026-10-06) — 공부 계획·자료 체크·진도 그래프가 없다
        "prepOnly": row["type"] in C.PREP_ONLY_TYPES,
        "ready": bool(_ready_at(row)),
        "readyAt": _ready_at(row),
    }
    if scope_info is not None:
        # note = 공지·사용자가 말한 **범위 문구**, autoNote = F4 자료를 세어 본 결과. 섞지 않는다.
        out["pages"] = scope_info["pages"]
        out["scope"]["pages"] = scope_info["pages"]
        out["scope"]["files"] = scope_info["files"]
        out["scope"]["noPages"] = scope_info["noPages"]
        out["scope"]["autoNote"] = scope_info["note"]
        out["scope"]["scopePages"] = scope_info.get("scopePages", scope_info["pages"])
        out["scope"]["donePages"] = scope_info.get("donePages", 0)
        out["scope"]["doneFiles"] = scope_info.get("doneFiles", 0)
        out["scope"]["basis"] = scope_info.get("basis", "all")
        out["scope"]["label"] = scope_info.get("label", "")
    out["plan"] = plan_view(plan_row, days or [], row, today) if plan_row is not None else None
    out["planState"] = out["plan"]["state"] if out["plan"] else "none"
    if scope_info is not None:
        out["study"] = study_progress(scope_info, out["plan"])
    return out


def study_progress(info: dict, plan: Optional[dict]) -> dict:
    """과목 카드의 공부 진도 그래프 (2026-10-06) — 범위 자료 중 얼마나 공부했나.

    checked  = 서비스 밖에서 공부했다고 **체크한 자료**의 쪽수
    planned  = 진행 중 계획에서 **완료한 블록**의 쪽수 — 계획은 체크하고 남은 분량으로 만들어지므로 둘을 더한다
    쪽수를 못 센 자료가 **절반 이상**이면(.ppt 가 대부분인 과목 — 실측: 컴퓨터그래픽스 7개 중 6개) **자료 개수**로 잰다.
    쪽수로 재면 그 자료들을 체크해도 그래프가 움직이지 않는다.
    """
    planned = plan["progress"]["donePages"] if plan and plan.get("unit") == "pages" else 0
    total = info.get("scopePages", info["pages"])
    if total and info.get("noPages", 0) * 2 < info["files"]:
        checked = info.get("donePages", 0)
        done = min(total, checked + planned)
        return {"unit": "pages", "total": total, "checked": checked, "planned": done - checked,
                "done": done, "remaining": total - done, "percent": _pct(done, total),
                "files": info["files"], "doneFiles": info.get("doneFiles", 0)}
    files = info["files"]
    checked = info.get("doneFiles", 0)
    return {"unit": "files", "total": files, "checked": checked, "planned": 0, "done": checked,
            "remaining": files - checked, "percent": _pct(checked, files),
            "files": files, "doneFiles": checked}


def _ready_at(row: Any) -> Optional[str]:
    return row["ready_at"] if "ready_at" in row.keys() else None


def _dday(n: int) -> str:
    if n == 0:
        return "오늘"
    return f"D-{n}" if n > 0 else f"D+{-n}"


def _md(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{d.month}/{d.day}({WEEKDAYS[d.weekday()]})"


# ---------------------------------------------------------------- 계획 한 줄 보기 · 진도

def _pct(done: int, total: int) -> int:
    """완료율 — 0.5 는 올림 (15/120 = 12.5% → 13%)."""
    return int(done / total * 100 + 0.5) if total else 0


def plan_view(row: Any, days: list[Any], exam_row: Any, today: date) -> dict:
    """등록된 계획 + 진도 (F5-R33·R34 · S07)."""
    t = today.isoformat()
    total_pages = sum(d["pages"] for d in days)
    done_pages = sum(d["pages"] for d in days if d["done"])
    planned_before = sum(d["pages"] for d in days if d["date"] < t)
    behind_pages = max(0, planned_before - done_pages)
    behind_days = [d["date"] for d in days if d["date"] < t and not d["done"]]
    remaining = [d for d in days if d["date"] >= t]
    unit = row["unit"]
    total_units = row["total_pages"] if unit == "pages" else row["total_minutes"]
    return {
        "id": f"pl:{row['id']}", "planId": row["id"], "examId": row["exam_id"],
        "examDate": exam_row["date"], "examDday": (date.fromisoformat(exam_row["date"]) - today).days,
        "state": row["state"], "stateLabel": PLAN_STATE_LABEL.get(row["state"], row["state"]),
        "unit": unit, "totalPages": row["total_pages"], "totalMinutes": row["total_minutes"],
        "pageMinutes": row["page_minutes"], "difficulty": row["difficulty"],
        "difficultyLabel": C.DIFFICULTY.get(row["difficulty"], {}).get("label", row["difficulty"]),
        "reviewDays": row["review_days"], "excludedDates": store.jload(row["excluded"], []),
        "includeQuiz": bool(row["include_quiz"]), "quizCount": row["quiz_count"],
        "scopeWeeks": store.jload(row["scope_weeks"], []), "scopeMaterialIds": store.jload(row["scope_ids"], []),
        "sourcePages": row["source_pages"],
        "dayMinutes": _pins(row),
        "days": [{**day_view(d), "pinned": d["date"] in _pins(row) and d["kind"] == "study"} for d in days],
        "progress": {
            "plannedPages": total_pages, "donePages": done_pages, "behindPages": behind_pages,
            "totalUnits": total_units,
            "percent": _pct(done_pages, total_pages) if total_pages else
                       _pct(sum(1 for d in days if d["done"]), len(days)),
            "doneDays": sum(1 for d in days if d["done"]), "totalDays": len(days),
            "behindDays": len(behind_days), "behindDates": behind_days,
            "remainingDays": len(remaining),
            "remainingPages": max(0, total_pages - done_pages),
            "todayPages": next((d["pages"] for d in days if d["date"] == t), 0),
            "todayMinutes": next((d["minutes"] for d in days if d["date"] == t), 0),
        },
        "behind": behind_pages > 0 or bool(behind_days),
        "behindMessage": _behind_message(behind_pages, behind_days, remaining, row),
        "createdAt": row["created_at"], "rebalancedAt": row["rebalanced_at"], "closedAt": row["closed_at"],
    }


def _behind_message(behind_pages: int, behind_days: list[str], remaining: list[Any], row: Any) -> str:
    """'2일 밀렸습니다 — 남은 6일로 다시 나누면 하루 19쪽입니다' (Frontend-Route 10-5)."""
    if not behind_days and behind_pages <= 0:
        return ""
    left_days = [d for d in remaining if d["kind"] == "study"] or remaining
    head = f"{len(behind_days)}일 밀렸습니다" if behind_days else f"{behind_pages}쪽 밀렸습니다"
    if not left_days:
        return f"{head} — 남은 학습일이 없습니다. 마무리 복습일에 몰아 보거나 계획을 다시 만드세요"
    if row["unit"] != "pages":
        return f"{head} — 남은 {len(left_days)}일로 다시 나눌 수 있습니다"
    left_pages = sum(d["pages"] for d in left_days) + behind_pages
    return (f"{head} — 남은 {len(left_days)}일로 다시 나누면 하루 "
            f"{-(-left_pages // len(left_days))}쪽입니다")


def day_view(d: Any) -> dict:
    day = date.fromisoformat(d["date"])
    return {"date": d["date"], "weekday": WEEKDAYS[day.weekday()], "pages": d["pages"], "minutes": d["minutes"],
            "kind": d["kind"], "kindLabel": DAY_KIND_LABEL.get(d["kind"], d["kind"]), "quiz": d["quiz"],
            "done": bool(d["done"]), "doneAt": d["done_at"], "moved": bool(d["moved"]),
            "blockId": f"st:{d['plan_id']}:{d['date']}"}


# ---------------------------------------------------------------- 목록 (F5-S01·S02)

def overview(con: sqlite3.Connection, get_courses: Optional[CoursesGetter] = None,
             semester: Optional[str] = None, today: Optional[date] = None,
             with_scope: bool = True) -> dict:
    """`/exams` 목록 — 다가오는 시험 카드 · 확인 필요 · 지난 시험 · 오늘 분량."""
    today = today or date.today()
    ensure_sync(con, today, get_courses=get_courses)
    made = defaults.ensure(con, today, get_courses)             # 과목마다 중간·기말 — 일정이 없으면 임의로 잡는다
    close_past(con, today)
    courses = course_map(get_courses)
    sid = semester or semester_of(today)
    lo, hi = semester_span(sid)
    rows = [r for r in store.exam_rows(con) if lo <= r["date"] <= hi]
    plans = {r["exam_id"]: r for r in store.plan_rows(con, state="active")}

    items = []
    for r in rows:
        p = plans.get(r["id"])
        info = _scope_info(con, r) if with_scope and r["type"] not in C.PREP_ONLY_TYPES else None
        items.append(exam_view(r, courses, today, p, store.days(con, p["id"]) if p else None, info))
    upcoming = [e for e in items if not e["past"]]
    past = [e for e in items if e["past"]]
    return {
        "semester": {"id": sid, "label": semester_label(sid), "start": lo, "end": hi},
        "semesters": sorted({semester_of(date.fromisoformat(r["date"])) for r in store.exam_rows(con)} | {sid},
                            reverse=True),
        "exams": upcoming,
        "past": past,
        "review": [e for e in items if e["needsReview"]],
        "counts": {"total": len(items), "upcoming": len(upcoming), "past": len(past),
                   "review": sum(1 for e in items if e["needsReview"]),
                   "planned": sum(1 for e in upcoming if e["planState"] == "active"),
                   "behind": sum(1 for e in upcoming if e["plan"] and e["plan"]["behind"])},
        "today": today_block(con, today, courses),
        "source": source_block(con),
        "types": [{"key": k, "label": v["label"], "reviewDays": v["reviewDays"]} for k, v in C.TYPES.items()],
        "difficulties": difficulty_view(con),
        "courseSettings": course_settings_view(con, courses, today),
        "defaults": {"periods": defaults.period_view(academic.periods(semester_of(today))),
                     "hints": made.get("hints", []),
                     "auto": sum(1 for e in upcoming if e["isAuto"]),
                     "created": made.get("created", []), "moved": made.get("moved", [])},
        "updatedAt": store.updated_at(con),
    }


def difficulty_minutes(con: sqlite3.Connection) -> dict[str, float]:
    """난이도별 쪽당 시간(분) — 사용자가 바꾼 값(meta.difficulty_minutes), 없으면 기본 1 / 1.5 / 2분."""
    out = {k: v["pageMinutes"] for k, v in C.DIFFICULTY.items()}
    saved = store.jload(store.get_meta(con, "difficulty_minutes"), {})
    for k, v in saved.items():
        if k in out and isinstance(v, (int, float)):
            out[k] = float(v)
    return out


def difficulty_view(con: sqlite3.Connection) -> list[dict]:
    mins = difficulty_minutes(con)
    return [{"key": k, "label": v["label"], "pageMinutes": mins[k], "defaultMinutes": v["pageMinutes"]}
            for k, v in C.DIFFICULTY.items()]


def set_difficulty_minutes(con: sqlite3.Connection, body: dict) -> dict:
    """'난이도 시간 설정' 저장 — {easy?, normal?, hard?} 분/쪽. null 이면 기본값으로. 이미 등록한 계획은 바꾸지 않는다."""
    unknown = set(body) - set(C.DIFFICULTY)
    if unknown or not body:
        raise Invalid(f"난이도는 {', '.join(C.DIFFICULTY)} 중에서 주세요")
    cur = store.jload(store.get_meta(con, "difficulty_minutes"), {})
    for k, v in body.items():
        if v is None:
            cur.pop(k, None)
            continue
        try:
            n = round(float(v), 2)
        except (TypeError, ValueError):
            raise Invalid(f"{C.DIFFICULTY[k]['label']}: 숫자를 넣어 주세요")
        if not 0.1 <= n <= C.PAGE_MINUTES_MAX:
            raise Invalid(f"{C.DIFFICULTY[k]['label']}: 쪽당 0.1~{C.PAGE_MINUTES_MAX:g}분 사이로 넣어 주세요")
        # 기본값과 같으면 저장하지 않는다 — 모달은 세 값을 다 보내므로, 그대로 두면 손대지 않은 기본값까지 굳어
        # 나중에 기본값을 바꿔도 안 먹는다(2026-10-02 실제로 어려움 3분이 남았다)
        if n == C.DIFFICULTY[k]["pageMinutes"]:
            cur.pop(k, None)
        else:
            cur[k] = n
    store.set_meta(con, difficulty_minutes=store.jdump(cur))
    store.touch(con)
    return {"difficulties": difficulty_view(con), "updatedAt": store.updated_at(con)}


# ---------------------------------------------------------------- 저녁 시간대 (2026-10-07)

def _hm_ok(v: Any, what: str, allow_24: bool = False) -> int:
    s = str(v or "").strip()
    h, _, m = s.partition(":")
    if not (h.isdigit() and m.isdigit() and len(m) == 2):
        raise Invalid(f"{what}은 HH:MM 모양이어야 합니다: {v}")
    hh, mm = int(h), int(m)
    if mm >= 60 or hh > 24 or (hh == 24 and (mm or not allow_24)):
        raise Invalid(f"{what}이 올바르지 않습니다: {v}")
    return hh * 60 + mm


def evening(con: sqlite3.Connection) -> dict:
    """시험 공부 계획이 놓이는 저녁 시간대 {start, end} — 사용자가 바꾼 값(meta.evening), 없으면 19:00~24:00."""
    out = {"start": C.EVENING_START, "end": C.EVENING_END}
    saved = store.jload(store.get_meta(con, "evening"), {})
    try:
        cand = {**out, **{k: saved[k] for k in ("start", "end") if k in saved}}
        s, e = _hm_ok(cand["start"], "저녁 시작"), _hm_ok(cand["end"], "저녁 끝", allow_24=True)
        if s >= _hhmm_to_min(C.EVENING_EARLIEST) and e - s >= 30:
            out = cand
    except Invalid:
        pass                                             # 깨진 값이면 기본값으로 — 화면이 죽지 않게
    return out


def evening_view(con: sqlite3.Connection) -> dict:
    cur = evening(con)
    return {**cur, "defaults": {"start": C.EVENING_START, "end": C.EVENING_END},
            "changed": cur != {"start": C.EVENING_START, "end": C.EVENING_END}, "earliest": C.EVENING_EARLIEST}


def set_evening(con: sqlite3.Connection, body: Any) -> dict:
    """{start?, end?} — null 이면 그 칸 기본값. 기본값과 같으면 저장하지 않는다(F5 난이도 설정과 같은 방식)."""
    if body is None:
        body = {"start": None, "end": None}
    if not isinstance(body, dict) or set(body) - {"start", "end"}:
        raise Invalid("저녁 시간대는 {start, end} 모양이어야 합니다")
    cur = evening(con)
    for k, v in body.items():
        cur[k] = (C.EVENING_START if k == "start" else C.EVENING_END) if v is None else str(v).strip()
    s, e = _hm_ok(cur["start"], "저녁 시작"), _hm_ok(cur["end"], "저녁 끝", allow_24=True)
    if s < _hhmm_to_min(C.EVENING_EARLIEST):
        raise Invalid(f"저녁 시작은 {C.EVENING_EARLIEST} 이후여야 합니다 — 낮은 공강 배치(F8) 몫입니다")
    if e - s < 30:
        raise Invalid("저녁 끝은 저녁 시작보다 30분 이상 늦어야 합니다")
    cur = {"start": _min_to_hhmm(s), "end": "24:00" if e == 24 * 60 else _min_to_hhmm(e)}
    saved = {k: v for k, v in cur.items() if v != {"start": C.EVENING_START, "end": C.EVENING_END}[k]}
    store.set_meta(con, evening=store.jdump(saved))
    store.touch(con)
    return evening_view(con)


def course_settings_view(con: sqlite3.Connection, courses: dict[str, dict], today: date) -> list[dict]:
    """과목별 시험 유무 + 그 과목의 중간·기말이 지금 어떤 상태인지 (화면 '과목별 시험')."""
    settings = store.course_settings(con)
    out = []
    for cid, c in courses.items():
        st = settings.get(cid) or {"midterm": True, "final": True, "updatedAt": None}
        row: dict[str, Any] = {"courseId": cid, "course": c["short"], "courseName": c["name"], "color": c["color"],
                               "midterm": st["midterm"], "final": st["final"]}
        for kind in C.DEFAULT_EXAM_TYPES:
            e = store.exam(con, exam_id(cid, kind, ""))
            row[f"{kind}Exam"] = None if e is None else {
                "id": e["id"], "date": e["date"], "time": e["time"], "source": e["source"],
                "sourceLabel": SOURCE_LABEL.get(e["source"], e["source"]), "past": e["date"] < today.isoformat()}
        out.append(row)
    return out


def set_course_exams(con: sqlite3.Connection, course_id: str, body: dict,
                     get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None) -> dict:
    """과목별 시험 유무를 바꾼다 — 끄면 임의 일정을 치우고, 켜면 바로 다시 잡는다."""
    today = today or date.today()
    courses = course_map(get_courses)
    if courses and course_id not in courses:
        raise NotFound(f"그런 과목이 없습니다: {course_id}")
    unknown = set(body) - {"midterm", "final"}
    if unknown or not body:
        raise Invalid("midterm · final 중 하나 이상을 true/false 로 주세요")
    if any(not isinstance(v, bool) for v in body.values()):
        raise Invalid("midterm · final 은 true/false 입니다")
    setting = store.set_course_setting(con, course_id, **body)
    made = defaults.ensure(con, today, get_courses, force=True)
    store.touch(con)
    row = next((r for r in course_settings_view(con, courses, today) if r["courseId"] == course_id), None)
    return {"course": row, "setting": setting, "created": made["created"], "removed": made["removed"],
            "updatedAt": store.updated_at(con)}


def _scope_info(con: sqlite3.Connection, row: Any) -> dict:
    """시험 범위의 자료 — 공부 완료로 체크한 자료는 남은 분량(`pages`)에서 빠진다 (2026-10-06)."""
    return scope.measure(row["course_id"], store.jload(row["scope_weeks"], []), store.jload(row["scope_ids"], []),
                         store.material_done(con, row["course_id"]))


def source_block(con: sqlite3.Connection) -> dict:
    """어디서 온 시험인지 — 화면 상단 안내 (F5 9절 '신뢰')."""
    return {
        "eclass": {"available": C.ECLASS_MANIFEST.exists(), "manifest": str(C.ECLASS_MANIFEST),
                   "stamp": store.get_meta(con, "notice_stamp"),
                   "syncedAt": store.get_meta(con, "notice_synced_at"),
                   "note": "시험 일정은 e클래스 공지에서 찾습니다 (수집은 F6). 못 찾은 시험은 직접 추가하세요"},
        "materials": {"available": scope.available(), "error": scope.error(),
                      "note": "분량은 강의자료(F4)의 쪽수 합계를 기본값으로 씁니다"},
    }


def detail(con: sqlite3.Connection, exam_id_: str, get_courses: Optional[CoursesGetter] = None,
           today: Optional[date] = None) -> dict:
    """시험 하나 — 계획 옵션 기본값과 범위 후보(주차·자료)까지 (F5-S03·S04)."""
    today = today or date.today()
    row = _exam(con, exam_id_)
    courses = course_map(get_courses)
    p = store.active_plan(con, exam_id_)
    info = _scope_info(con, row)
    out = exam_view(row, courses, today, p, store.days(con, p["id"]) if p else None, info)
    out["options"] = default_options(con, row, today, info)
    out["scopeChoices"] = {"weeks": scope.weeks(row["course_id"]),
                           "materials": scope.materials(row["course_id"])}
    out["plans"] = [plan_view(r, store.days(con, r["id"]), row, today)
                    for r in store.plan_rows(con, exam_id_) if r["state"] != "active"]
    return out


def default_options(con: sqlite3.Connection, row: Any, today: date,
                    scope_info: Optional[dict] = None) -> dict:
    """계획 만들기 화면의 초기값 (F5-S04) — 진행 중 계획이 있으면 그 설정을 물려준다."""
    info = scope_info if scope_info is not None else _scope_info(con, row)
    cur = store.active_plan(con, row["id"])
    if cur is not None:
        left_dates = [d["date"] for d in store.days(con, cur["id"])
                      if d["kind"] == "study" and not d["done"] and d["date"] >= today.isoformat()]
        # 자료에서 자동으로 채운 분량이었으면(= source_pages) 지금 남은 분량으로 — 그새 공부 완료 체크를 했을 수 있다
        auto = cur["unit"] == "pages" and cur["source_pages"] is not None and cur["total_pages"] == cur["source_pages"]
        return {"unit": cur["unit"], "totalPages": info["pages"] if auto else cur["total_pages"],
                "totalMinutes": cur["total_minutes"],
                "difficulty": cur["difficulty"], "pageMinutes": cur["page_minutes"],
                "reviewDays": cur["review_days"], "excludedDates": store.jload(cur["excluded"], []),
                "includeQuiz": bool(cur["include_quiz"]),
                "quizCount": cur["quiz_count"], "scopeWeeks": store.jload(cur["scope_weeks"], []),
                "scopeMaterialIds": store.jload(cur["scope_ids"], []), "startDate": today.isoformat(),
                # 등록한 계획의 남은 학습 날짜 — 그대로 다시 계산하면 같은 날에 나뉜다
                "studyDays": None,
                "studyDates": left_dates,
                # 그 날들에 직접 정해 둔 공부 시간 (2026-10-06 D11) — 완료했거나 지난 날의 값은 버린다
                "dayMinutes": {d: m for d, m in _pins(cur).items() if d in set(left_dates)}}
    # 분량은 쪽수로만 받는다(2026-10-01 — 화면에서 '시간(분)' 단위를 뺐다). 자료가 없으면 0 → 화면이 직접 입력을 받는다
    # 학습일 기본 3일 — 마무리 복습 바로 앞 3일 (2026-10-02 사용자 요청). 남은 날이 3일보다 적으면 계산기가 줄인다
    return {"studyDays": C.DEFAULT_STUDY_DAYS, "studyDates": [], "dayMinutes": {},
            "unit": "pages",
            "totalPages": info["pages"], "totalMinutes": 0,
            "difficulty": C.DEFAULT_DIFFICULTY, "pageMinutes": None,     # 비워 두면 계산할 때 난이도 시간 설정 값을 넣는다
            "reviewDays": C.review_days_for(row["type"]), "excludedDates": [],
            "includeQuiz": False, "quizCount": 0,
            "scopeWeeks": store.jload(row["scope_weeks"], []),
            "scopeMaterialIds": store.jload(row["scope_ids"], []), "startDate": today.isoformat()}


# ---------------------------------------------------------------- 시험 추가·수정·삭제 (F5-R03)

_EXAM_FIELDS = {"type", "title", "date", "time", "endTime", "place", "scopeWeeks", "scopeMaterialIds",
                "scopeNote", "status", "courseId"}
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _check(body: dict, courses: dict[str, dict], require: bool) -> dict:
    out: dict[str, Any] = {}
    unknown = set(body) - _EXAM_FIELDS
    if unknown:
        raise Invalid(f"모르는 항목입니다: {', '.join(sorted(unknown))}")
    if require:
        for k in ("courseId", "date"):
            if not body.get(k):
                raise Invalid(f"{'과목' if k == 'courseId' else '날짜'}를 넣어 주세요")
    if "courseId" in body:
        cid = str(body["courseId"])
        if courses and cid not in courses:
            raise Invalid(f"그런 과목이 없습니다: {cid}")
        out["course_id"] = cid
        out["course"] = courses.get(cid, {}).get("name", "")
    if "type" in body:
        if body["type"] not in C.TYPES:
            raise Invalid(f"유형은 {', '.join(C.TYPES)} 중 하나입니다: {body['type']!r}")
        out["type"] = body["type"]
    if "date" in body:
        out["date"] = _date(body["date"], "시험 날짜")
    for key, col in (("time", "time"), ("endTime", "end_time")):
        if key in body:
            v = (body[key] or "").strip()
            if v and not _TIME_RE.match(v):
                raise Invalid(f"시각 형식이 잘못됐습니다: {v!r} (HH:MM · 비우면 '시각 미정')")
            out[col] = v
    if out.get("time") and out.get("end_time") and out["end_time"] <= out["time"]:
        raise Invalid("끝 시각이 시작보다 빠릅니다")
    if "place" in body:
        out["place"] = str(body["place"] or "").strip()[:120]
    if "title" in body:
        out["title"] = str(body["title"] or "").strip()[:80]
    if "scopeNote" in body:
        out["scope_note"] = str(body["scopeNote"] or "").strip()[:300]
    if "scopeWeeks" in body:
        weeks = sorted({int(w) for w in (body["scopeWeeks"] or [])})
        if any(not 1 <= w <= 30 for w in weeks):
            raise Invalid("주차는 1~30 사이입니다")
        out["scope_weeks"] = store.jdump(weeks)
    if "scopeMaterialIds" in body:
        out["scope_ids"] = store.jdump([str(x) for x in (body["scopeMaterialIds"] or [])])
    if "status" in body:
        if body["status"] not in STATUS_LABEL:
            raise Invalid(f"상태는 {', '.join(STATUS_LABEL)} 중 하나입니다")
        out["status"] = body["status"]
    return out


def add_exam(con: sqlite3.Connection, body: dict, get_courses: Optional[CoursesGetter] = None,
             today: Optional[date] = None) -> dict:
    """시험 직접 추가 (F5-R03 · S03). 같은 과목·날짜·유형이 이미 있으면 거절한다."""
    today = today or date.today()
    courses = course_map(get_courses)
    fields = _check(body, courses, require=True)
    cid, when = fields["course_id"], fields["date"]
    etype = fields.get("type", "etc")
    stamp = store.now()
    if etype in C.SINGLETON_TYPES:
        # 중간·기말은 과목마다 하나다(id 가 (과목, 유형)) — 임의 일정·지운 줄이면 그 자리를 쓰고, 진짜 일정이 있으면 거절한다
        eid = exam_id(cid, etype, when)
        cur = store.exam(con, eid, include_removed=True)
        if cur is not None and cur["source"] != "auto" and not cur["removed_at"]:
            raise Conflict(f"이 과목의 {C.type_label(etype)}이(가) 이미 있습니다 ({cur['date']}) — 그 시험을 고치세요")
        store.set_course_setting(con, cid, **{etype: True})       # 직접 넣었다 = 이 과목은 이 시험을 본다
    else:
        same = [r for r in store.exam_rows(con) if r["course_id"] == cid and r["date"] == when and r["type"] == etype]
        if same:
            raise Conflict(f"같은 날짜의 {C.type_label(etype)} 시험이 이미 있습니다")
        eid = _free_id(con, cid, etype, when)
    row = {"id": eid, "course_id": cid, "course": fields.get("course", ""), "type": etype,
           "title": fields.get("title") or C.type_label(etype), "date": when,
           "time": fields.get("time", ""), "end_time": fields.get("end_time", ""),
           "place": fields.get("place", ""),
           "scope_weeks": fields.get("scope_weeks", "[]"), "scope_ids": fields.get("scope_ids", "[]"),
           "scope_note": fields.get("scope_note", ""), "source": "manual", "evidence": "[]",
           "confidence": 1.0, "status": "confirmed", "notice_key": "", "notice_url": "", "posted_at": "",
           "edited": 1, "changed": "", "removed_at": None, "note": "", "added_at": stamp, "seen_at": stamp}
    store.upsert_exam(con, row)
    store.touch(con)
    saved = store.exam(con, eid)
    p = store.active_plan(con, eid)                            # 임의 일정에 등록해 둔 계획이 있었을 수 있다
    out = exam_view(saved, courses, today, p, store.days(con, p["id"]) if p else None, _scope_info(con, saved))
    out["planStale"] = _plan_stale(con, saved, p)
    return out


def _free_id(con: sqlite3.Connection, cid: str, etype: str, when: str) -> str:
    """수기 시험의 id — 공지 추출분과 같은 규칙으로 만들고, 겹치면 꼬리를 붙인다."""
    base = exam_id(cid, etype, when)
    eid, n = base, 1
    while store.exam(con, eid, include_removed=True) is not None:
        n += 1
        eid = f"{base}-{n}"
    return eid


def patch_exam(con: sqlite3.Connection, exam_id_: str, body: dict,
               get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None) -> dict:
    """승인·수정 (F5-S02·S03). 손대면 `edited` 가 서서 재수집이 덮어쓰지 않는다 (F5-R03)."""
    today = today or date.today()
    row = _exam(con, exam_id_)
    courses = course_map(get_courses)
    fields = _check(body, courses, require=False)
    if not fields:
        raise Invalid("바꿀 항목이 없습니다")
    if "course_id" in fields and fields["course_id"] != row["course_id"]:
        raise Invalid("과목은 바꿀 수 없습니다 — 지우고 새로 추가하세요")
    fields["seen_at"] = store.now()
    if row["source"] == "auto":
        # 날짜·시각을 고쳤다 = 사용자가 일정을 안다 → 직접 넣은 일정(공지가 덮어쓰지 않는다).
        # 범위·장소만 고쳤으면 날짜는 아직 추측이다 → 임의 일정으로 두어 공지가 날짜를 채울 수 있게 한다.
        if any(k in fields for k in ("date", "time", "end_time")):
            fields.update(source="manual", note="", edited=1)
    else:
        fields["edited"] = 1
    if "status" not in fields and row["status"] == "review":
        fields["status"] = "confirmed"                  # 고쳤다 = 확인했다 (승인 큐에서 내려간다)
    if "date" in fields and fields["date"] != row["date"]:
        fields["changed"] = ""                          # 사용자가 직접 고친 날짜에는 '바뀜' 배지를 달지 않는다
    store.update_exam(con, exam_id_, fields)
    store.touch(con)
    updated = _exam(con, exam_id_)
    p = store.active_plan(con, exam_id_)
    out = exam_view(updated, courses, today, p, store.days(con, p["id"]) if p else None, _scope_info(con, updated))
    # 범위·날짜가 바뀌면 이미 등록된 계획의 전제가 달라진다 (F5 8절)
    out["planStale"] = _plan_stale(con, updated, p)
    return out


def _plan_stale(con: sqlite3.Connection, row: Any, plan_row: Optional[Any]) -> Optional[dict]:
    """등록된 계획이 지금 시험·자료와 어긋나는지 — 재계산을 권하는 쪽지 (F5 8절)."""
    if plan_row is None:
        return None
    reasons = []
    info = _scope_info(con, row)
    if plan_row["source_pages"] is not None and info["pages"] and info["pages"] != plan_row["source_pages"]:
        reasons.append(f"공부할 자료가 {plan_row['source_pages']}쪽 → {info['pages']}쪽으로 바뀌었습니다")
    if store.jload(row["scope_weeks"], []) != store.jload(plan_row["scope_weeks"], []):
        reasons.append("시험 범위가 바뀌었습니다")
    days = store.days(con, plan_row["id"])
    if days and days[-1]["date"] >= row["date"]:
        reasons.append("학습 블록이 시험일 뒤까지 잡혀 있습니다")
    if not reasons:
        return None
    return {"reasons": reasons, "message": " · ".join(reasons) + " — 계획을 다시 만드세요"}


def delete_exam(con: sqlite3.Connection, exam_id_: str) -> dict:
    """시험 삭제 (F5-R03). 등록된 계획·학습 블록도 함께 사라진다(완료 기록까지 — 시험 자체를 지웠으므로)."""
    row = _exam(con, exam_id_)
    plans = store.plan_rows(con, exam_id_)
    if row["source"] == "auto":
        # 임의로 잡아 둔 시험을 지웠다 = 이 과목은 이 시험을 안 본다 → 과목 설정을 끈다(켜면 다시 잡힌다)
        store.hard_delete_exam(con, exam_id_)
        store.set_course_setting(con, row["course_id"], **{row["type"]: False})
        store.touch(con)
        return {"deleted": exam_id_, "plansRemoved": len(plans),
                "note": f"이 과목은 {C.type_label(row['type'])}이(가) 없는 것으로 둡니다 — '과목별 시험'에서 다시 켤 수 있습니다",
                "courseSetting": store.course_setting(con, row["course_id"])}
    store.delete_exam(con, exam_id_, hard=row["source"] == "manual")
    if row["source"] != "manual":
        for p in plans:                                 # 소프트 삭제라 CASCADE 가 안 걸린다 — 계획은 직접 지운다
            store.delete_days(con, p["id"])
            con.execute("DELETE FROM plans WHERE id = ?", (p["id"],))
    store.touch(con)
    return {"deleted": exam_id_, "plansRemoved": len(plans),
            "note": "공지에서 다시 찾아도 되살아나지 않습니다" if row["source"] != "manual" else ""}


# ---------------------------------------------------------------- 공부 완료 체크 (2026-10-06)

def study_materials(con: sqlite3.Connection, exam_id_: str, get_courses: Optional[CoursesGetter] = None,
                    today: Optional[date] = None) -> dict:
    """시험 범위의 강의자료 + 공부 완료 체크 — '자료 체크' 창.

    체크는 **과목 단위**다(같은 자료를 중간·기말에서 따로 체크하지 않는다). 범위 밖이지만 과목에 있는
    자료(`others`)도 같이 보여 준다 — 범위를 좁혀 둔 시험에서도 공부한 것을 적어 둘 수 있게.
    """
    today = today or date.today()
    row = _exam(con, exam_id_)
    _study_only(row)
    courses = course_map(get_courses)
    p = store.active_plan(con, exam_id_)
    info = _scope_info(con, row)
    done = store.material_done(con, row["course_id"])
    in_scope = {m["id"] for m in info["materials"]}
    others = [{"id": m["id"], "title": m["title"], "week": m["week"], "pages": m["pages"], "kind": m["kind"],
               "ext": m["ext"], "done": m["id"] in done, "doneAt": done.get(m["id"])}
              for m in scope.materials(row["course_id"]) if m["id"] not in in_scope]
    exam = exam_view(row, courses, today, p, store.days(con, p["id"]) if p else None, info)
    return {"exam": exam, "materials": info["materials"], "others": others,
            "available": info["available"], "note": info["note"],
            "planStale": _plan_stale(con, row, p), "updatedAt": store.updated_at(con)}


def set_study_materials(con: sqlite3.Connection, exam_id_: str, body: dict,
                        get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None) -> dict:
    """{ids: [...], done: true|false} — 서비스 밖에서 공부한 자료 체크·해제.

    과목에 없는 자료 id 는 거절한다(엉뚱한 줄이 쌓이지 않게). 등록된 계획은 **바꾸지 않는다** —
    남은 분량이 달라졌으면 `planStale` 로 다시 만들기를 권한다(자동 변경 없음, F5 8절).
    """
    row = _exam(con, exam_id_)
    _study_only(row)
    ids = body.get("ids")
    if isinstance(ids, str):
        ids = [ids]
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) and i for i in ids):
        raise Invalid("체크할 자료 id 를 ids 로 주세요")
    if not isinstance(body.get("done"), bool):
        raise Invalid("done 은 true 또는 false 입니다")
    known = {m["id"] for m in scope.materials(row["course_id"])}
    unknown = [i for i in ids if i not in known]
    if unknown:
        raise NotFound(f"이 과목의 강의자료가 아닙니다: {', '.join(unknown[:3])}")
    changed = store.set_material_done(con, row["course_id"], ids, body["done"])
    if changed:
        store.touch(con)
    out = study_materials(con, exam_id_, get_courses, today)
    out["changed"] = changed
    return out


def _exam(con: sqlite3.Connection, exam_id_: str) -> Any:
    row = store.exam(con, exam_id_)
    if row is None:
        raise NotFound(f"그런 시험이 없습니다: {exam_id_}")
    return row


# ---------------------------------------------------------------- 미리보기 · 등록 (F5-R30·R31)

def _exam_for_plan(row: Any, courses: dict[str, dict]) -> dict:
    c = _course_of(row, courses)
    return {"id": row["id"], "courseId": row["course_id"], "courseName": c["short"],
            "type": row["type"], "date": row["date"], "time": row["time"]}


def _fill_scope(con: sqlite3.Connection, row: Any, options: dict) -> dict:
    """옵션에 쪽수가 없으면 범위 안 F4 자료에서 채운다 (F5-R10). 범위도 안 주면 시험의 범위를 쓴다.
    쪽당 시간을 따로 주지 않았으면 사용자의 '난이도 시간 설정' 값을 넣는다 (2026-10-02)."""
    o = dict(options or {})
    if o.get("pageMinutes") in (None, "", 0):
        o["pageMinutes"] = difficulty_minutes(con).get(o.get("difficulty") or C.DEFAULT_DIFFICULTY,
                                                       C.page_minutes_for(C.DEFAULT_DIFFICULTY))
    if "scopeWeeks" not in o:
        o["scopeWeeks"] = store.jload(row["scope_weeks"], [])
    if "scopeMaterialIds" not in o:
        o["scopeMaterialIds"] = store.jload(row["scope_ids"], [])
    info = scope.measure(row["course_id"], o.get("scopeWeeks"), o.get("scopeMaterialIds"),
                         store.material_done(con, row["course_id"]))
    if (o.get("unit") or "pages") == "pages" and not o.get("totalPages"):
        o["totalPages"] = info["pages"]
        if not info["pages"] and o.get("totalMinutes"):
            o["unit"] = "minutes"                        # 자료가 없고 사용자가 시간을 넣었다 (F5-R11)
    return {"options": o, "scope": info}


def _study_only(row: Any) -> None:
    """발표는 공부 계획·자료 체크가 없다 — '준비 완료'만 누른다 (2026-10-06 사용자 요청)."""
    if row["type"] in C.PREP_ONLY_TYPES:
        raise Invalid(f"{C.type_label(row['type'])}는 공부 계획을 만들지 않습니다 — '준비 완료'만 체크하세요")


def set_ready(con: sqlite3.Connection, exam_id_: str, body: dict,
              get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None) -> dict:
    """{ready: true|false} — 발표 준비 완료 체크·해제. 날짜·범위는 건드리지 않으므로 `edited` 를 세우지 않는다
    (공지에서 날짜가 바뀌면 그대로 따라온다)."""
    today = today or date.today()
    row = _exam(con, exam_id_)
    if row["type"] not in C.PREP_ONLY_TYPES:
        raise Invalid(f"준비 완료는 발표에만 있습니다 — {C.type_label(row['type'])}는 공부 계획으로 진도를 봅니다")
    ready = body.get("ready")
    if not isinstance(ready, bool):
        raise Invalid("ready 는 true 또는 false 입니다")
    store.update_exam(con, exam_id_, {"ready_at": store.now() if ready else None})
    store.touch(con)
    return exam_view(_exam(con, exam_id_), course_map(get_courses), today)


def preview(con: sqlite3.Connection, exam_id_: str, options: Optional[dict] = None,
            today: Optional[date] = None, get_courses: Optional[CoursesGetter] = None,
            carry: Optional[dict] = None) -> dict:
    """계획 계산만 — 저장하지 않는다 (F5-R30 · S05). 화면은 이 결과를 표로 그린다.

    **이미 등록된 계획이 있으면 완료한 분량을 빼고 계산한다** — 등록(`create_plan`)이 그렇게 하기 때문이다.
    여기서 빼지 않으면 사용자가 본 표와 실제로 등록되는 계획이 어긋난다.
    """
    today = today or date.today()
    row = _exam(con, exam_id_)
    _study_only(row)
    courses = course_map(get_courses)
    current = store.active_plan(con, exam_id_)
    if carry is None and current is not None:
        carry = _carry(con, current)
    filled = _fill_scope(con, row, options or {})
    try:
        out = P.compute(_exam_for_plan(row, courses), filled["options"], today, carry)
    except P.Invalid as e:
        raise Invalid(str(e))
    out["scope"] = filled["scope"]
    out["exam"] = exam_view(row, courses, today, None, None, filled["scope"])
    return out


def create_plan(con: sqlite3.Connection, exam_id_: str, options: Optional[dict] = None,
                today: Optional[date] = None, get_courses: Optional[CoursesGetter] = None,
                keep_done: bool = True) -> dict:
    """미리보기를 캘린더에 등록한다 (F5-R31). 같은 시험의 진행 중 계획은 대체된다.

    keep_done: 이미 완료한 블록은 그대로 두고 남은 분량만 다시 나눈다(재조정 적용, F5 5절).
    """
    today = today or date.today()
    row = _exam(con, exam_id_)
    _study_only(row)
    courses = course_map(get_courses)
    current = store.active_plan(con, exam_id_)
    carry = _carry(con, current) if (current is not None and keep_done) else None

    filled = _fill_scope(con, row, options or {})
    try:
        result = P.compute(_exam_for_plan(row, courses), filled["options"], today, carry)
    except P.Invalid as e:
        raise Invalid(str(e))
    if not result["canRegister"]:
        raise Conflict("등록할 학습 블록이 없습니다 — " +
                       (result["warnings"][0]["message"] if result["warnings"] else "분량과 날짜를 확인하세요"))

    if current is not None:                              # 옛 계획은 닫고 미완료 블록만 치운다 (F5-R35)
        store.delete_days(con, current["id"], undone_only=True)
        store.update_plan(con, current["id"], {"state": "canceled", "closed_at": store.now()})

    o = result
    stamp = store.now()
    plan_id = store.insert_plan(con, {
        "exam_id": exam_id_, "unit": o["unit"], "total_pages": o["totalPages"], "total_minutes": o["totalMinutes"],
        "page_minutes": o["pageMinutes"], "difficulty": o["difficulty"], "review_days": o["reviewDays"],
        "excluded": store.jdump(o["excludedDates"]),
        "include_quiz": int(o["includeQuiz"]), "quiz_count": o["quizCount"],
        "scope_weeks": store.jdump(o["scopeWeeks"]), "scope_ids": store.jdump(o["scopeMaterialIds"]),
        "day_minutes": store.jdump(o["dayMinutes"]),
        "source_pages": filled["scope"]["pages"] or None,
        "state": "active", "created_at": stamp,
        "rebalanced_at": stamp if carry else None, "closed_at": None,
    })
    store.put_days(con, plan_id, [
        {"date": d["date"], "pages": d["pages"], "minutes": d["minutes"], "kind": d["kind"],
         "quiz": d["quiz"], "done": int(d["done"]), "done_at": d.get("doneAt"), "moved": int(d["moved"])}
        for d in o["days"] if d["kind"] != "excluded" and (d["pages"] or d["minutes"] or d["done"])])
    store.touch(con)
    saved = store.plan(con, plan_id)
    days = store.days(con, plan_id)
    return {
        "plan": plan_view(saved, days, row, today),
        "exam": exam_view(row, courses, today, saved, days, filled["scope"]),
        "verdict": o["verdict"], "verdictLabel": o["verdictLabel"], "warnings": o["warnings"],
        "message": f"{len([d for d in days if not d['done']])}일치 학습 계획을 공부 캘린더에 넣었습니다",
        "updatedAt": store.updated_at(con),
    }


def _pins(plan_row: Any) -> dict[str, int]:
    """계획에 저장된 '날마다 직접 정한 공부 시간' {날짜: 분} (2026-10-06 D11). 옛 계획에는 없다."""
    raw = plan_row["day_minutes"] if "day_minutes" in plan_row.keys() else None
    return {k: int(v) for k, v in (store.jload(raw, {}) or {}).items()}


def _carry(con: sqlite3.Connection, plan_row: Any) -> dict:
    """재조정에서 넘겨받는 것 — 이미 완료한 블록과 그 분량 (과거는 건드리지 않는다, F5 5절)."""
    done = [d for d in store.days(con, plan_row["id"]) if d["done"]]
    return {
        "pages": sum(d["pages"] for d in done),
        "minutes": sum(d["minutes"] for d in done),
        "days": [{"date": d["date"], "weekday": WEEKDAYS[date.fromisoformat(d["date"]).weekday()],
                  "pages": d["pages"], "minutes": d["minutes"], "kind": d["kind"], "quiz": d["quiz"],
                  "done": True, "doneAt": d["done_at"], "moved": bool(d["moved"])} for d in done],
    }


# ---------------------------------------------------------------- 진도 · 재조정 (F5-R32~R35)

def plan_detail(con: sqlite3.Connection, plan_id: int, today: Optional[date] = None,
                get_courses: Optional[CoursesGetter] = None) -> dict:
    today = today or date.today()
    p = _plan(con, plan_id)
    row = _exam(con, p["exam_id"])
    courses = course_map(get_courses)
    days = store.days(con, plan_id)
    out = plan_view(p, days, row, today)
    out["exam"] = exam_view(row, courses, today, None, None, _scope_info(con, row))
    out["materials"] = scope.measure(row["course_id"], store.jload(p["scope_weeks"], []),
                                     store.jload(p["scope_ids"], []),
                                     store.material_done(con, row["course_id"]))["materials"]
    return out


def day_detail(con: sqlite3.Connection, plan_id: int, when: str,
               get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None) -> dict:
    """학습 블록 하나 — 그날 볼 자료 목록과 완료 체크 (F5-S08 · 캘린더 팝업)."""
    today = today or date.today()
    p = _plan(con, plan_id)
    row = _exam(con, p["exam_id"])
    d = store.day(con, plan_id, _date(when, "날짜"))
    if d is None:
        raise NotFound(f"그 날짜의 학습 블록이 없습니다: {when}")
    info = scope.measure(row["course_id"], store.jload(p["scope_weeks"], []), store.jload(p["scope_ids"], []),
                         store.material_done(con, row["course_id"]))
    return {**day_view(d), "planId": plan_id, "examId": row["id"],
            "exam": exam_view(row, course_map(get_courses), today, None, None, info),
            "materials": info["materials"], "materialsNote": info["note"],
            "pageMinutes": p["page_minutes"]}


def patch_day(con: sqlite3.Connection, plan_id: int, when: str, body: dict,
              today: Optional[date] = None, get_courses: Optional[CoursesGetter] = None) -> dict:
    """완료 체크(F5-R33) · 다른 날로 옮기기(F5-R32). 옮긴 날은 재조정이 건드리지 않는다."""
    today = today or date.today()
    p = _plan(con, plan_id)
    when = _date(when, "날짜")
    d = store.day(con, plan_id, when)
    if d is None:
        raise NotFound(f"그 날짜의 학습 블록이 없습니다: {when}")
    unknown = set(body) - {"done", "date"}
    if unknown:
        raise Invalid(f"모르는 항목입니다: {', '.join(sorted(unknown))}")
    if not body:
        raise Invalid("바꿀 항목이 없습니다")

    if "done" in body:
        done = bool(body["done"])
        store.update_day(con, plan_id, when, {"done": int(done), "done_at": store.now() if done else None})
    if "date" in body:
        new = _date(body["date"], "옮길 날짜")
        if new != when:
            row = _exam(con, p["exam_id"])
            if new >= row["date"]:
                raise Invalid(f"시험일({row['date']}) 이후로는 옮길 수 없습니다")
            target = store.day(con, plan_id, new)
            if target is not None and target["done"]:
                raise Conflict(f"{_md(new)} 은 이미 완료한 날입니다 — 다른 날로 옮기세요")
            if target is not None:
                # 이미 분량이 있는 날로 옮기면 **그 날에 합친다** (블록이 둘 생기지도, 사라지지도 않는다).
                # 학습+복습이 겹치면 학습일로 둔다 — 새 진도를 보는 날이 되기 때문이다.
                store.update_day(con, plan_id, new, {
                    "pages": target["pages"] + d["pages"], "minutes": target["minutes"] + d["minutes"],
                    "quiz": target["quiz"] + d["quiz"], "moved": 1,
                    "kind": "study" if "study" in (target["kind"], d["kind"]) else target["kind"]})
                store.delete_day(con, plan_id, when)
            else:
                store.move_day(con, plan_id, when, new)
            when = new
    store.touch(con)

    row = _exam(con, p["exam_id"])
    days = store.days(con, plan_id)
    if p["state"] == "active" and days and all(x["done"] for x in days):
        store.update_plan(con, plan_id, {"state": "done", "closed_at": store.now()})
        p = _plan(con, plan_id)
        days = store.days(con, plan_id)
    elif p["state"] == "done" and any(not x["done"] for x in days) and row["date"] >= today.isoformat():
        # 다 끝내서 닫혔던 계획인데 체크를 풀었다 — 다시 진행 중으로 연다 (2026-10-02: 체크 해제가 안 되던 것).
        # 시험일이 지나 닫힌 계획(close_past)은 열지 않는다.
        store.update_plan(con, plan_id, {"state": "active", "closed_at": None})
        p = _plan(con, plan_id)
    out = plan_view(p, days, row, today)
    return {"plan": out, "day": next((x for x in out["days"] if x["date"] == when), None),
            "exam": exam_view(row, course_map(get_courses), today, p, days, _scope_info(con, row)),
            "updatedAt": store.updated_at(con)}


def delete_day(con: sqlite3.Connection, plan_id: int, when: str) -> dict:
    """학습 블록 하나를 지운다 — 완료한 것도 지운다(공부 캘린더의 '삭제', 2026-10-02).
    그 계획에 블록이 하나도 남지 않으면 계획도 지운다(빈 계획이 진도·목록에 남지 않게)."""
    p = _plan(con, plan_id)
    when = _date(when, "날짜")
    if store.day(con, plan_id, when) is None:
        raise NotFound(f"그 날짜의 학습 블록이 없습니다: {when}")
    store.delete_day(con, plan_id, when)
    left = store.days(con, plan_id)
    removed_plan = False
    if not left:
        con.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        removed_plan = True
    elif p["state"] == "active" and all(x["done"] for x in left):
        store.update_plan(con, plan_id, {"state": "done", "closed_at": store.now()})
    store.touch(con)
    return {"deleted": f"st:{plan_id}:{when}", "planRemoved": removed_plan, "blocksLeft": len(left),
            "updatedAt": store.updated_at(con)}


def rebalance(con: sqlite3.Connection, plan_id: int, options: Optional[dict] = None,
              today: Optional[date] = None, get_courses: Optional[CoursesGetter] = None) -> dict:
    """밀린 진도를 남은 날로 다시 나눈 **미리보기**를 돌려준다 (F5-R34).

    캘린더를 바꾸지 않는다 — 사용자가 `등록하기`(create_plan)를 누르면 그때 적용된다 (F5 5절)."""
    today = today or date.today()
    p = _plan(con, plan_id)
    row = _exam(con, p["exam_id"])
    base = default_options(con, row, today)
    merged = {**base, **(options or {})}
    merged["startDate"] = today.isoformat()
    out = preview(con, row["id"], merged, today, get_courses, carry=_carry(con, p))
    days = store.days(con, plan_id)
    before = plan_view(p, days, row, today)
    out["rebalanceOf"] = {"planId": plan_id, "id": f"pl:{plan_id}", "progress": before["progress"],
                          "behindMessage": before["behindMessage"]}
    out["note"] = ("확인을 누르면 미완료 블록이 이 계획으로 바뀝니다 (완료한 날은 그대로 둡니다)")
    return out


def cancel_plan(con: sqlite3.Connection, plan_id: int, today: Optional[date] = None) -> dict:
    """계획 취소 (F5-R35) — 미완료 블록만 캘린더에서 지운다. 완료한 것은 남긴다."""
    today = today or date.today()
    p = _plan(con, plan_id)
    if p["state"] == "canceled":
        raise Conflict("이미 취소된 계획입니다")
    removed = store.delete_days(con, plan_id, undone_only=True)
    kept = len(store.days(con, plan_id))
    store.update_plan(con, plan_id, {"state": "canceled", "closed_at": store.now()})
    store.touch(con)
    return {"canceled": f"pl:{plan_id}", "blocksRemoved": removed, "blocksKept": kept,
            "message": f"학습 블록 {removed}개를 지웠습니다" + (f" (완료한 {kept}개는 남겼습니다)" if kept else ""),
            "updatedAt": store.updated_at(con)}


def close_past(con: sqlite3.Connection, today: Optional[date] = None) -> int:
    """시험일이 지난 계획을 `done` 으로 닫는다 (F5 8절). 목록을 부를 때마다 한 번.

    블록 줄을 지우지는 않는다 — 캘린더는 끝난 계획의 **완료한 블록만** 그리므로(calendar_events)
    안 한 블록은 그것만으로 캘린더에서 사라지고, '무엇을 못 했는지'는 진도 화면에 남는다."""
    today = today or date.today()
    t = today.isoformat()
    closed = 0
    for p in store.plan_rows(con, state="active"):
        row = store.exam(con, p["exam_id"], include_removed=True)
        if row is None or row["date"] >= t:
            continue
        store.update_plan(con, p["id"], {"state": "done", "closed_at": store.now()})
        closed += 1
    if closed:
        store.touch(con)
    return closed


def behind_alerts(con: sqlite3.Connection, today: Optional[date] = None,
                  notify: Optional[Notify] = None, get_courses: Optional[CoursesGetter] = None) -> list[dict]:
    """진도가 밀린 계획을 알림 센터로 (F5-R34 — '밀린 다음 날 배너·알림').

    하루에 한 번만 보낸다(알림 id 에 날짜가 들어간다). 캘린더는 건드리지 않는다."""
    today = today or date.today()
    courses = course_map(get_courses)
    out = []
    for p in store.plan_rows(con, state="active"):
        row = store.exam(con, p["exam_id"])
        if row is None:
            continue
        view = plan_view(p, store.days(con, p["id"]), row, today)
        if not view["behind"]:
            continue
        c = _course_of(row, courses)
        alert = {"kind": "exam", "refId": row["id"],
                 "title": f"{c['short']} 학습 계획이 밀렸습니다",
                 "body": view["behindMessage"],
                 "href": f"/exams?exam={row['id']}&step=progress",
                 "at": today.isoformat(), "planId": p["id"]}
        out.append(alert)
        _safe_notify(notify, alert)
    return out


def _plan(con: sqlite3.Connection, plan_id: int) -> Any:
    row = store.plan(con, plan_id)
    if row is None:
        raise NotFound(f"그런 학습 계획이 없습니다: pl:{plan_id}")
    return row


def parse_plan_id(raw: str) -> int:
    """`pl:3` · `3` → 3."""
    s = str(raw)
    s = s[3:] if s.startswith("pl:") else s
    if not s.isdigit():
        raise NotFound(f"학습 계획 id 가 아닙니다: {raw}")
    return int(s)


# ---------------------------------------------------------------- 캘린더 (F5-R05·R31)

def calendar_events(con: sqlite3.Connection, start: Optional[str] = None, end: Optional[str] = None,
                    get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None) -> list[dict]:
    """/api/events(전체 캘린더)에 섞는 것 — **날짜가 확정된 시험(kind=exam)만** (C1 3절).

    학습 블록(공부 계획)은 전체 캘린더에 넣지 않는다 — 시험 공부 일정 캘린더(/study-calendar)에만 있다
    (2026-10-01 사용자 요청: "공부 계획은 시험 공부 일정 캘린더에만"). 블록 데이터는 study_calendar() 가 준다."""
    today = today or date.today()
    courses = course_map(get_courses)
    out: list[dict] = []
    for row in store.exam_rows(con):
        if (start and row["date"] < start) or (end and row["date"] > end):
            continue
        if not is_confirmed(row):
            continue                                     # 날짜가 확정되지 않은 시험은 전체 캘린더에 넣지 않는다 (2026-10-01)
        out.append(_exam_event(row, courses, today))
    return out


def is_confirmed(row: Any) -> bool:
    """날짜가 확정된 시험인가 — 임의 일정(auto)과 확인 안 한 공지 추출분(review)은 아니다.
    전체 캘린더(/api/events)에는 확정된 것만 넣고, 시험 화면·공부 캘린더에는 표시를 달아 모두 보여 준다."""
    return row["source"] != "auto" and row["status"] != "review"


def _exam_event(row: Any, courses: dict[str, dict], today: date) -> dict:
    c = _course_of(row, courses)
    d = date.fromisoformat(row["date"])
    all_day = not row["time"]
    start = row["date"] if all_day else f"{row['date']}T{row['time']}:00"
    if all_day:                                          # 종일 일정의 end 는 exclusive (C1-R14)
        end = (d + timedelta(days=1)).isoformat()
    elif row["end_time"]:
        end = f"{row['date']}T{row['end_time']}:00"
    else:
        end = None
    return {
        "id": row["id"], "title": f"{c['short']} {row['title'] or C.type_label(row['type'])}",
        "start": start, "end": end, "allDay": all_day, "editable": False,
        "extendedProps": {
            "kind": "exam", "examId": row["id"], "courseId": row["course_id"], "courseName": c["name"],
            "course": c["short"], "courseColor": c["color"], "color": C.EXAM_COLOR,
            "type": row["type"], "typeLabel": C.type_label(row["type"]),
            "place": row["place"], "timeUnknown": all_day,
            "status": row["status"], "needsReview": row["status"] == "review",
            "confidence": round(row["confidence"], 2), "source": row["source"],
            "noticeUrl": row["notice_url"], "evidence": store.jload(row["evidence"], []),
            "isAuto": row["source"] == "auto", "note": row["note"],
            "dday": (d - today).days, "href": f"/exams?exam={row['id']}",
        },
    }


def _hhmm_to_min(v: str) -> int:
    h, _, m = v.partition(":")
    return int(h) * 60 + int(m or 0)


def _min_to_hhmm(v: int) -> str:
    return f"{v // 60:02d}:{v % 60:02d}"


# ---------------------------------------------------------------- 공부 캘린더 (2026-10-01)

def study_calendar(con: sqlite3.Connection, start: str, end: str,
                   get_courses: Optional[CoursesGetter] = None, today: Optional[date] = None,
                   extra: Optional[Callable[[str, str], list[dict]]] = None) -> dict:
    """시험 공부만 보는 캘린더 — 날짜마다 과목 · 시간 · 분량, 그리고 그날의 시험.

    전체 캘린더(/api/events)와 달리 **날짜가 확정되지 않은 시험도** '임의'·'확인 필요' 표시를 달아 보여 준다
    (그 시험에 맞춰 공부하고 있기 때문이다). 등록된 계획의 블록만 싣는다 — 끝난·취소된 계획은 완료한 블록만.

    시각 (2026-10-07): 계획의 하루 분량은 **저녁 시간대(기본 19:00~24:00)에 시험이 가까운 과목부터 차례로** 놓인다.
    저녁 끝을 넘는 분량은 24:00 에서 끊어 보이고, 자정 뒤에 시작할 몫은 시각 없이(`time: null`) 둔다 — 경고는 하지 않는다.
    extra(start, end) = F8 공강 공부 블록(09:00~18:00) — 백엔드가 넘겨주면 같은 날 칸에 시각 순으로 섞는다(kind='gap').
    """
    today = today or date.today()
    s, e = _date(start, "시작"), _date(end, "끝")
    if e < s or (date.fromisoformat(e) - date.fromisoformat(s)).days > 92:
        raise Invalid("기간은 92일 이내로 주세요")
    courses = course_map(get_courses)
    rows = {r["id"]: r for r in store.exam_rows(con)}
    days: dict[str, dict] = {}

    def slot(d: str) -> dict:
        return days.setdefault(d, {"date": d, "blocks": [], "exams": []})

    ev = evening(con)
    for p in store.plan_rows(con):
        row = rows.get(p["exam_id"])
        if row is None:
            continue
        c = _course_of(row, courses)
        for d in store.days(con, p["id"]):
            if not s <= d["date"] <= e or (p["state"] != "active" and not d["done"]):
                continue
            slot(d["date"])["blocks"].append({
                "source": "plan", "planId": p["id"], "examId": row["id"], "course": c["short"], "color": c["color"],
                "time": None, "endTime": None,                 # 아래에서 저녁 시간대에 차례로 채운다
                "pages": d["pages"], "minutes": d["minutes"], "quiz": d["quiz"], "kind": d["kind"],
                "kindLabel": DAY_KIND_LABEL.get(d["kind"], d["kind"]), "done": bool(d["done"]),
                "examType": C.type_label(row["type"]), "examDate": row["date"],
                "text": _block_text(c["short"], d),
                # 체크: 진행 중·다 끝낸 계획(풀면 다시 열린다). 취소된 계획의 남은 완료 기록은 체크 대신 삭제만
                "editable": p["state"] in ("active", "done") and row["date"] >= today.isoformat(),
                "deletable": True,
            })
    for row in rows.values():
        if not s <= row["date"] <= e:
            continue
        c = _course_of(row, courses)
        slot(row["date"])["exams"].append({
            "examId": row["id"], "course": c["short"], "color": c["color"], "type": row["type"],
            "typeLabel": C.type_label(row["type"]), "title": row["title"] or C.type_label(row["type"]),
            "time": row["time"], "endTime": row["end_time"], "place": row["place"],
            "isAuto": row["source"] == "auto", "needsReview": row["status"] == "review",
            "confirmed": is_confirmed(row), "timeFromClass": bool(row["time_auto"]),
            "prepOnly": row["type"] in C.PREP_ONLY_TYPES, "ready": bool(_ready_at(row)),
        })
    ev_s, ev_e = _hhmm_to_min(ev["start"]), _hhmm_to_min(ev["end"])
    for d in days.values():
        # 저녁 시간대에 차례로 — 시험이 가까운 과목부터. 완료 여부로 순서를 바꾸지 않는다(체크해도 시각이 움직이지 않게)
        d["blocks"].sort(key=lambda b: (b["examDate"], b["course"], b["planId"]))
        cursor = ev_s
        for b in d["blocks"]:
            stop = cursor + max(b["minutes"], 10)
            b["time"] = _min_to_hhmm(cursor) if cursor < 24 * 60 else None
            b["endTime"] = (_min_to_hhmm(stop) if stop < 24 * 60 else "24:00") if b["time"] else None
            b["slot"] = "evening"
            b["late"] = stop > ev_e                    # 저녁 끝을 넘었다 — 표시만 (하루 기준 경고는 없다, 2026-10-07)
            cursor = stop
    if extra is not None:
        try:
            gap = extra(s, e) or []
        except Exception:                                # noqa: BLE001 — F8 을 못 읽어도 계획 블록은 보여 준다
            gap = []
        for g in gap:
            if s <= g["date"] <= e:
                slot(g["date"])["blocks"].append({**g, "source": "gap", "kind": "gap", "kindLabel": "공강 공부",
                                                  "pages": 0, "quiz": 0, "slot": "gap"})
    for d in days.values():
        d["blocks"].sort(key=lambda b: (b["time"] or "99", b["course"]))
        d["exams"].sort(key=lambda x: (x["time"] or "99", x["course"]))
        d["totalMinutes"] = sum(b["minutes"] for b in d["blocks"])
        d["totalPages"] = sum(b["pages"] for b in d["blocks"])
    return {"start": s, "end": e, "today": today.isoformat(), "evening": ev,
            "days": sorted(days.values(), key=lambda d: d["date"]),
            "todayBlock": today_block(con, today, courses), "updatedAt": store.updated_at(con)}


# ---------------------------------------------------------------- 공강 공부 대상 (F8, 2026-10-07)

def study_targets(con: sqlite3.Connection, get_courses: Optional[CoursesGetter] = None,
                  today: Optional[date] = None, with_progress: bool = True) -> list[dict]:
    """F8 이 남는 공강(09~18시)에 넣을 공부 과목 후보 — 다가오는 시험(발표 제외)과 **남은 진도율**.

    진도율 = 과목 카드의 공부 진도(체크한 자료 + 계획에서 완료한 블록, D10). 계산 대상은 시험일이 오늘부터
    STUDY_TARGET_DAYS 일 안인 것. with_progress=False 면 자료를 세지 않는다(충돌 확인처럼 id·날짜만 필요할 때).
    고르는 규칙(남은 진도율 ÷ 남은 날수)은 F8 몫이다 — 여기서는 재료만 준다."""
    today = today or date.today()
    last = (today + timedelta(days=C.STUDY_TARGET_DAYS)).isoformat()
    ov = overview(con, get_courses, None, today, with_scope=with_progress)
    out = []
    for x in ov["exams"]:
        if x["prepOnly"] or not today.isoformat() <= x["date"] <= last:
            continue
        study = x.get("study") or {}
        if with_progress:
            pct = study.get("percent") if study.get("total") else (x["plan"]["progress"]["percent"] if x["plan"] else 0)
        else:
            pct = None
        out.append({
            "examId": x["id"], "course": x["course"], "courseName": x["courseName"], "color": x["color"],
            "type": x["type"], "typeLabel": x["typeLabel"], "title": x["title"],
            "date": x["date"], "time": x["time"] or "", "dday": x["dday"],
            "isAuto": x["isAuto"], "needsReview": x["needsReview"], "confirmed": x["confirmed"],
            "percent": pct, "planned": x["planState"] == "active",
            "href": f"/exams?exam={x['id']}",
        })
    return out


# ---------------------------------------------------------------- 브리핑 · 상태

def today_block(con: sqlite3.Connection, today: Optional[date] = None,
                courses: Optional[dict[str, dict]] = None) -> dict:
    """'오늘 공부: 운영체제 15쪽 (38분)' + 가장 가까운 시험 (F5-R36 · S09 — F10 브리핑·F9 대화가 읽는다)."""
    today = today or date.today()
    t = today.isoformat()
    courses = courses if courses is not None else course_map()
    blocks, next_exam = [], None
    rows = {r["id"]: r for r in store.exam_rows(con)}
    for p in store.plan_rows(con, state="active"):
        row = rows.get(p["exam_id"])
        if row is None:
            continue
        d = store.day(con, p["id"], t)
        if d is None:
            continue
        c = _course_of(row, courses)
        blocks.append({"planId": p["id"], "examId": row["id"], "course": c["short"], "color": c["color"],
                       "pages": d["pages"], "minutes": d["minutes"], "quiz": d["quiz"], "kind": d["kind"],
                       "kindLabel": DAY_KIND_LABEL.get(d["kind"], d["kind"]), "done": bool(d["done"]),
                       "examDate": row["date"], "dday": (date.fromisoformat(row["date"]) - today).days,
                       "text": _block_text(c["short"], d)})
    upcoming = sorted((r for r in rows.values() if r["date"] >= t), key=lambda r: (r["date"], r["time"]))
    if upcoming:
        r = upcoming[0]
        c = _course_of(r, courses)
        dd = (date.fromisoformat(r["date"]) - today).days
        next_exam = {"examId": r["id"], "course": c["short"], "type": r["type"],
                     "typeLabel": C.type_label(r["type"]), "date": r["date"], "time": r["time"],
                     "place": r["place"], "dday": dd, "ddayLabel": _dday(dd)}
    blocks.sort(key=lambda b: (b["done"], -b["minutes"]))
    return {
        "date": t, "blocks": blocks,
        "totalPages": sum(b["pages"] for b in blocks), "totalMinutes": sum(b["minutes"] for b in blocks),
        "remainingMinutes": sum(b["minutes"] for b in blocks if not b["done"]),
        "text": " · ".join(b["text"] for b in blocks) if blocks else "",
        "nextExam": next_exam,
    }


def _block_text(short: str, d: Any) -> str:
    if d["kind"] == "review":
        return f"{short} 전체 복습" + (f" + 문제 {d['quiz']}개" if d["quiz"] else "")
    return f"{short} {d['pages']}쪽 ({d['minutes']}분)" if d["pages"] else f"{short} {d['minutes']}분"


def status_summary(con: sqlite3.Connection, get_courses: Optional[CoursesGetter] = None,
                   today: Optional[date] = None, notify: Optional[Notify] = None) -> dict:
    """/api/status 의 exams 칸 — 기능 타일 숫자 (F5-S09).

    대시보드가 1분마다 부른다 → 여기서 **지난 계획 닫기**와 **밀림 알림 배달**을 같이 한다
    (따로 도는 스케줄러가 없다 — F1 알림이 그렇게 되어 있다). 알림은 id 에 날짜가 들어가 하루 한 번만 쌓인다."""
    today = today or date.today()
    ensure_sync(con, today, notify, get_courses)
    made = defaults.ensure(con, today, get_courses)             # 중간고사가 지난 과목은 여기서 기말고사가 생긴다
    _notify_created(made.get("created", []), notify)
    close_past(con, today)
    if notify:
        behind_alerts(con, today, notify, get_courses)
    t = today.isoformat()
    rows = store.exam_rows(con)
    upcoming = [r for r in rows if r["date"] >= t]
    plans = store.plan_rows(con, state="active")
    behind = 0
    for p in plans:
        row = store.exam(con, p["exam_id"])
        if row is not None and plan_view(p, store.days(con, p["id"]), row, today)["behind"]:
            behind += 1
    block = today_block(con, today, course_map(get_courses))
    return {
        "available": True, "updatedAt": store.updated_at(con),
        "exams": len(rows), "upcoming": len(upcoming),
        "review": sum(1 for r in rows if r["status"] == "review"),
        "activePlans": len(plans), "behind": behind,
        "todayPages": block["totalPages"], "todayMinutes": block["totalMinutes"],
        "todayText": block["text"], "nextExam": block["nextExam"],
        "eclassAvailable": C.ECLASS_MANIFEST.exists(),
        "materialsAvailable": scope.available(),
        "noticeSyncedAt": store.get_meta(con, "notice_synced_at"),
        "auto": sum(1 for r in upcoming if r["source"] == "auto"),
    }
