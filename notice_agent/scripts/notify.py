"""알림 — 해당자에게만, 새로 생긴 것만.  (기능명세서 DF-5 ⑤, 1.3 "선별 알림", 4장 "알림 정책")

    python -m scripts.notify              # 아직 알리지 않은 eligible / needs_review 건 → 다이제스트 출력 + 파일
    python -m scripts.notify --deadline 3 # D-3 이내 마감 리마인더도 포함
    python -m scripts.notify --json       # Alert 페이로드 JSON 만 출력 (BE 알림 발송기에 넘기는 용도)

산출물
    data/alerts/YYYY-MM-DD.md      사람이 읽는 다이제스트 (같은 날 여러 번 돌면 이어 붙임)
    data/alerts/sent.json          이미 알린 notice_id → 마지막 알림 종류 (중복 알림 억제)
전량 알림은 하지 않는다: ineligible / expired / not_applicable 은 절대 알리지 않는다.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from . import config as C
from .collect import load_notice
from .draft import VERDICT_LABEL, load_draft
from .match import load_match
from .schemas import Alert, MatchResult

SENT_FILE = C.ALERT_DIR / "sent.json"


def _load_sent() -> dict:
    return json.loads(SENT_FILE.read_text(encoding="utf-8")) if SENT_FILE.exists() else {}


def _save_sent(d: dict) -> None:
    SENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    SENT_FILE.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def build_alerts(deadline_days: Optional[int] = None, today: Optional[date] = None) -> list[Alert]:
    today = today or date.today()
    sent = _load_sent()
    alerts: list[Alert] = []
    for p in sorted(C.MATCH_DIR.glob("*.json")):
        mr = MatchResult.model_validate_json(p.read_text(encoding="utf-8"))
        if mr.verdict not in ("eligible", "needs_review"):
            continue
        n = load_notice(mr.notice_id)
        if n is None:
            continue
        d = load_draft(mr.notice_id)
        reasons = [r.message for r in mr.reasons if r.status != "pass"][:4] or [r.message for r in mr.reasons][:3]
        kind = "scholarship_match" if mr.verdict == "eligible" else "scholarship_review"
        key = f"{kind}:{n.content_hash}"
        fresh = False
        if sent.get(mr.notice_id, {}).get("key") != key:
            alerts.append(Alert(type=kind, notice_id=n.id, title=n.title, url=n.url, verdict=mr.verdict,
                                deadline=mr.deadline, days_left=mr.days_left, reasons=reasons,
                                draft_path=d.markdown_path if d else None))
            sent[mr.notice_id] = {**sent.get(mr.notice_id, {}), "key": key, "at": datetime.now().isoformat(timespec="seconds")}
            fresh = True
        # 마감 임박 리마인더 (승인 전 초안이 있고, D-n 이내, 아직 리마인드 안 함). 방금 첫 알림을 보낸 건은 D-day 가 이미 붙어 있으니 생략
        if not fresh and deadline_days is not None and mr.days_left is not None and 0 <= mr.days_left <= deadline_days:
            dkey = f"deadline:{mr.deadline}"
            if sent.get(mr.notice_id, {}).get("deadline_key") != dkey and (d is None or d.status == "pending_approval"):
                alerts.append(Alert(type="scholarship_deadline", notice_id=n.id, title=n.title, url=n.url,
                                    verdict=mr.verdict, deadline=mr.deadline, days_left=mr.days_left,
                                    reasons=[f"D-{mr.days_left} — 초안 승인·제출 여부 확인"],
                                    draft_path=d.markdown_path if d else None))
                sent.setdefault(mr.notice_id, {})["deadline_key"] = dkey
    _save_sent(sent)
    return alerts


def digest_md(alerts: list[Alert]) -> str:
    if not alerts:
        return ""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"## {now} — 장학 알림 {len(alerts)}건", ""]
    order = {"scholarship_deadline": 0, "scholarship_match": 1, "scholarship_review": 2}
    for a in sorted(alerts, key=lambda x: (order[x.type], x.days_left if x.days_left is not None else 999)):
        tag = {"scholarship_match": "✅ 해당", "scholarship_review": "❓ 확인 필요", "scholarship_deadline": "⏰ 마감 임박"}[a.type]
        dl = f" · D-{a.days_left}" if a.days_left is not None and a.days_left >= 0 else ""
        lines.append(f"### {tag}{dl} — [{a.title}]({a.url})")
        for r in a.reasons:
            lines.append(f"- {r}")
        if a.draft_path:
            lines.append(f"- 초안: `{a.draft_path}` → `python -m scripts.approve show {a.notice_id}`")
        lines.append("")
    return "\n".join(lines)


def run(deadline_days: Optional[int] = None, as_json: bool = False) -> list[Alert]:
    C.ensure_dirs()
    alerts = build_alerts(deadline_days)
    if as_json:
        print(json.dumps([a.model_dump() for a in alerts], ensure_ascii=False, indent=2))
        return alerts
    md = digest_md(alerts)
    if not md:
        print("새로 알릴 항목이 없습니다.")
        return alerts
    out = C.ALERT_DIR / f"{date.today().isoformat()}.md"
    with open(out, "a", encoding="utf-8") as f:
        f.write(md + "\n")
    print(md)
    print(f"(저장: {out})")
    return alerts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deadline", type=int, default=None, metavar="N", help="D-N 이내 마감 리마인더 포함")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    run(a.deadline, a.json)
    return 0


if __name__ == "__main__":
    sys.exit(main())
