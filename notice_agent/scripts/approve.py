"""5단계 승인 — 신청서 초안 승인 대기 큐 (Human-in-the-loop).  (기능명세서 F11 제약: 최종 제출은 사용자 승인 후)

    python -m scripts.approve list                 # 승인 대기 목록 (마감 임박순)
    python -m scripts.approve show   <notice_id>   # 초안 내용 출력
    python -m scripts.approve approve <notice_id> [--note "..."]
    python -m scripts.approve reject  <notice_id> [--note "..."]
    python -m scripts.approve open   <notice_id>   # 초안 .md 를 기본 편집기로 연다 (Windows)

'승인'은 **기록**이다. 이 도구는 어떤 사이트에도 제출하지 않는다.
승인 후 화면에 신청 경로(학사정보시스템 메뉴 / 재단 사이트 / 학과 사무실)를 다시 보여주며, 제출은 사용자가 직접 한다.
BE 가 붙으면 이 큐가 역할별 분해서 5장의 `승인 대기 객체` 계약(조회·수정·승인·거절 API)에 대응한다.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

from . import config as C
from .draft import STATUS_LABEL, VERDICT_LABEL, draft_paths, load_draft
from .schemas import Draft
from .textutil import days_until


def all_drafts() -> list[Draft]:
    out = []
    for p in sorted(C.DRAFT_DIR.glob("*.json")):
        try:
            out.append(Draft.model_validate_json(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def _sort_key(d: Draft):
    left = days_until(d.deadline)
    return (0 if left is not None and left >= 0 else 1, left if left is not None else 10**6, d.created_at)


def cmd_list(status: str | None = "pending_approval") -> int:
    ds = [d for d in all_drafts() if status is None or d.status == status]
    if not ds:
        print("승인 대기 중인 초안이 없습니다." if status else "초안이 없습니다.")
        return 0
    print(f"{'상태':8s} {'판정':8s} {'마감':>8s}  {'notice_id':34s} 장학명")
    for d in sorted(ds, key=_sort_key):
        left = days_until(d.deadline)
        dl = f"D-{left}" if left is not None and left >= 0 else ("지남" if left is not None else "-")
        print(f"{STATUS_LABEL[d.status][:6]:8s} {VERDICT_LABEL.get(d.verdict, d.verdict)[:6]:8s} {dl:>8s}  {d.notice_id:34s} {d.scholarship_name[:40]}")
    return 0


def cmd_show(nid: str) -> int:
    d = load_draft(nid)
    if d is None:
        print("초안이 없습니다:", nid); return 1
    md_path, _ = draft_paths(nid)
    print(md_path.read_text(encoding="utf-8"))
    return 0


def _decide(nid: str, status: str, note: str | None) -> int:
    d = load_draft(nid)
    if d is None:
        print("초안이 없습니다:", nid); return 1
    d.status = status                      # type: ignore[assignment]
    d.decided_at = datetime.now().isoformat(timespec="seconds")
    d.user_note = note
    md_path, json_path = draft_paths(nid)
    json_path.write_text(d.model_dump_json(indent=2), encoding="utf-8")
    # .md 머리글의 상태 표기도 갱신
    md = md_path.read_text(encoding="utf-8")
    for k, v in STATUS_LABEL.items():
        md = md.replace(f"상태: **{v}**", f"상태: **{STATUS_LABEL[status]}**")
    md_path.write_text(md, encoding="utf-8")
    if status == "approved":
        print(f"승인 기록됨: {d.scholarship_name}")
        print("이제 아래 경로로 **직접** 제출하세요 (이 도구는 제출하지 않습니다):")
        print(f"  · 신청 경로: {d.apply_method or '공지 원문 확인'}")
        if d.apply_url:
            print(f"  · URL: {d.apply_url}")
        if d.deadline:
            left = days_until(d.deadline)
            print(f"  · 마감: {d.deadline}" + (f" (D-{left})" if left is not None and left >= 0 else " (지남!)"))
        print(f"  · 초안 파일: {md_path}")
    else:
        print(f"반려 기록됨: {d.scholarship_name}" + (f" — {note}" if note else ""))
    return 0


def cmd_open(nid: str) -> int:
    md_path, _ = draft_paths(nid)
    if not md_path.exists():
        print("초안이 없습니다:", nid); return 1
    if os.name == "nt":
        os.startfile(str(md_path))     # type: ignore[attr-defined]
    else:
        print(md_path)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list"); p.add_argument("--all", action="store_true", help="승인·반려 포함 전부")
    for name in ("show", "approve", "reject", "open"):
        p = sub.add_parser(name); p.add_argument("notice_id"); p.add_argument("--note", default=None)
    a = ap.parse_args(argv)
    if a.cmd == "list":
        return cmd_list(None if a.all else "pending_approval")
    if a.cmd == "show":
        return cmd_show(a.notice_id)
    if a.cmd == "approve":
        return _decide(a.notice_id, "approved", a.note)
    if a.cmd == "reject":
        return _decide(a.notice_id, "rejected", a.note)
    if a.cmd == "open":
        return cmd_open(a.notice_id)
    return 1


if __name__ == "__main__":
    sys.exit(main())
