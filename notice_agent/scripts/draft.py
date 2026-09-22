"""4단계 초안 — 해당(또는 확인 필요) 장학금의 신청서 초안 생성 → 승인 대기 큐.  (기능명세서 F11 출력, DF-5 ⑥)

    python -m scripts.draft                    # data/matches/ 중 eligible(+needs_review) 건의 초안 생성
    python -m scripts.draft --id aisw_dept:945245 --redo
    python -m scripts.draft --only-eligible

만드는 것
    data/drafts/<id>.md     사람이 읽고 고치는 초안 (assets/templates/application_draft.md 골격)
    data/drafts/<id>.json   Draft 레코드 (status=pending_approval) — approve.py 가 상태를 바꾼다

원칙
  - **제출하지 않는다.** 초안 생성까지가 이 도구의 일이다. 제출은 사용자가 승인 후 직접 한다 (기능명세서 F11 제약, 4장 승인 흐름).
  - 개인 식별 정보(이름·학번)는 프롬프트에 넣지 않고 {{이름}} 자리표시자로 남긴다 (4장 개인정보).
  - LLM 이 없으면 골격 + 안내문만 있는 초안을 만든다. 없는 사실을 지어내는 것보다 빈칸이 낫다.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from . import config as C
from .collect import load_notice
from .extract import load_extraction
from .llm import LLM, LLMError, load_prompt, render
from .match import load_match, load_profile
from .schemas import Draft, MatchResult, Notice, Profile, Requirements
from .textutil import sanitize_filename

STATUS_LABEL = {"pending_approval": "승인 대기", "approved": "승인됨 (제출은 본인이)", "rejected": "반려"}
VERDICT_LABEL = {"eligible": "해당", "needs_review": "확인 필요", "ineligible": "비해당", "expired": "마감 지남",
                 "not_applicable": "신청 대상 아님"}


def draft_paths(notice_id: str) -> tuple[Path, Path]:
    stem = sanitize_filename(notice_id.replace(":", "_"))
    return C.DRAFT_DIR / f"{stem}.md", C.DRAFT_DIR / f"{stem}.json"


def load_draft(notice_id: str) -> Optional[Draft]:
    _, jp = draft_paths(notice_id)
    return Draft.model_validate_json(jp.read_text(encoding="utf-8")) if jp.exists() else None


def _profile_context(prof: Profile) -> str:
    """LLM 에 넘기는 학생 정보 — 식별 정보 없이, 있는 것만."""
    lines = []
    if prof.college or prof.department:
        lines.append(f"- 소속: {prof.college or ''} {prof.department or ''} {prof.major or ''}".rstrip())
    if prof.grade:
        lines.append(f"- 학년: {prof.grade}학년 (이수 {prof.semesters_completed or '?'}학기)")
    if prof.gpa:
        lines.append(f"- 평점: {prof.gpa.value:g}/{prof.gpa.scale:g}")
    if prof.earned_credits:
        lines.append(f"- 취득학점: {prof.earned_credits}")
    if prof.interests:
        lines.append(f"- 관심 분야: {', '.join(prof.interests)}")
    for k, label in (("career_goal", "진로 목표"), ("activities", "활동·경험"), ("strengths", "강점"),
                     ("hardship", "가정 형편·지원 필요 사유"), ("plan", "학업 계획"), ("extra", "기타")):
        v = prof.draft_context.get(k)
        if v:
            lines.append(f"- {label}: {v}")
    return "\n".join(lines) or "- (제공된 정보 없음 — 모든 항목을 안내문으로 남길 것)"


def _notice_summary(n: Notice, req: Requirements) -> str:
    parts = [f"- 장학명: {req.scholarship_name or n.title}", f"- 주관/유형: {req.provider or '?'} / {req.kind or '?'}"]
    if req.other_conditions:
        parts.append("- 우대·추가 조건: " + " | ".join(req.other_conditions[:5]))
    if req.required_documents:
        parts.append("- 제출 서류: " + ", ".join(req.required_documents[:8]))
    if req.amount:
        parts.append(f"- 지원 내용: {req.amount}")
    body = n.full_text[:2500]
    parts.append(f"- 공지 본문(발췌):\n{body}")
    return "\n".join(parts)


def _skeleton_essay(req: Requirements) -> str:
    docs = "자기소개서" if any("자기소개" in d for d in req.required_documents) else "지원서"
    return "\n".join([
        "## 1. 자기소개",
        "[여기에 자기소개를 적어주세요: 소속·학년, 관심 분야, 이 분야를 택한 계기 3~5문장]",
        "",
        "## 2. 지원 동기",
        f"[여기에 지원 동기를 적어주세요: 이 장학금의 취지({req.kind or '장학'})와 본인 상황이 맞닿는 지점]",
        "",
        "## 3. 학업 및 진로 계획",
        "[여기에 수혜 후 계획을 적어주세요: 학기별 목표, 진로와의 연결]",
        "",
        "## 4. 검토 메모",
        f"- LLM 미설정 상태로 만든 골격 초안입니다. `.env` 에 LLM_MAIN 을 채우고 `--redo` 하면 {docs} 문안이 생성됩니다.",
    ])


def _reasons_md(mr: MatchResult) -> str:
    icon = {"pass": "✅", "fail": "❌", "unknown": "❓"}
    lines = []
    for r in mr.reasons:
        ev = f"  \n  > {r.evidence[:160]}" if r.evidence else ""
        lines.append(f"- {icon[r.status]} {r.message}{ev}")
    return "\n".join(lines) or "- (구조화된 자격 조건 없음)"


def build_draft(n: Notice, req: Requirements, mr: MatchResult, prof: Profile, llm: LLM) -> tuple[str, Draft]:
    essay = None
    generated_by = "template"
    if llm.available:
        version, system = load_prompt("draft_application")
        user = f"[장학 공지 요약]\n{_notice_summary(n, req)}\n\n[학생 정보]\n{_profile_context(prof)}"
        try:
            essay = llm.text("draft_application", system, user, temperature=0.4)
            generated_by = f"llm (prompt v{version})"
        except LLMError as e:
            essay = _skeleton_essay(req) + f"\n- LLM 호출 실패로 골격만 생성: {str(e)[:100]}"
    if essay is None:
        essay = _skeleton_essay(req)

    period = req.application_period
    period_s = (f"{(period.start or '?')[:16]} ~ {(period.end or '?')[:16]}" if period and (period.start or period.end) else "공지 확인")
    dday = ""
    if mr.days_left is not None:
        dday = f"(D-{mr.days_left})" if mr.days_left >= 0 else f"(마감 {-mr.days_left}일 지남)"
    checklist = "\n".join(f"- [ ] {d}" for d in req.required_documents) or "- [ ] (공지/첨부 양식에서 제출 서류 확인)"
    unknown_block = ""
    if mr.unknown_fields:
        unknown_block = ("### 확인이 필요한 항목\n" + "\n".join(f"- {f}" for f in dict.fromkeys(mr.unknown_fields)) +
                         "\n\n위 항목은 프로필에 정보가 없거나 공지가 모호해 자동 판정하지 못했습니다. 공지 원문으로 직접 확인하세요.")
    draft = Draft(
        notice_id=n.id, scholarship_name=req.scholarship_name or n.title, verdict=mr.verdict,
        markdown_path=str(draft_paths(n.id)[0].relative_to(C.ROOT)), checklist=req.required_documents,
        apply_method=req.apply_method, apply_url=req.apply_url, deadline=mr.deadline, generated_by=generated_by,
    )
    tmpl = (C.TEMPLATE_DIR / "application_draft.md").read_text(encoding="utf-8")
    md = render(
        tmpl,
        scholarship_name=draft.scholarship_name, status_label=STATUS_LABEL[draft.status], created_at=draft.created_at,
        verdict=f"{mr.verdict} · {VERDICT_LABEL.get(mr.verdict, '')}", confidence=f"{mr.confidence:.2f}",
        provider=req.provider or "-", kind=req.kind or "-", source_name=n.source_name, url=n.url,
        posted_at=n.posted_at or "-", period=period_s, dday=dday,
        apply_method=req.apply_method or "공지 확인", apply_url=f"<{req.apply_url}>" if req.apply_url else "",
        amount=req.amount or "-", selection_count=req.selection_count or "-", contact=req.contact or "-",
        reasons=_reasons_md(mr), unknown_block=unknown_block, checklist=checklist, essay=essay, notice_id=n.id,
        # 템플릿 안의 {{이름}} {{학번}} 은 사용자가 채울 자리표시자 — 치환하지 않고 그대로 남긴다
        이름="{{이름}}", 학번="{{학번}}",
    )
    return md, draft


def run(ids: Optional[list[str]] = None, redo: bool = False, only_eligible: bool = False,
        profile_path: Optional[Path] = None, force: bool = False) -> list[Draft]:
    """ids 는 처리 범위를 좁힐 뿐이다. 신청 기간 없는 '확인 필요' 건까지 만들려면 force=True (CLI --id 가 그렇게 한다)."""
    C.ensure_dirs()
    prof = load_profile(profile_path)
    llm = LLM()
    if not llm.available:
        print("(LLM_MAIN 미설정 — 골격 초안만 만듭니다)")
    wanted_verdicts = {"eligible"} if only_eligible or not C.DRAFT_FOR_NEEDS_REVIEW else {"eligible", "needs_review"}
    targets = ids or [p.stem for p in sorted(C.MATCH_DIR.glob("*.json"))]
    out: list[Draft] = []
    for t in targets:
        nid = t if ":" in t else None
        mr = None
        if nid:
            mr = load_match(nid)
        else:
            import json
            mr = MatchResult.model_validate(json.loads((C.MATCH_DIR / f"{t}.json").read_text(encoding="utf-8")))
            nid = mr.notice_id
        if mr is None or mr.verdict not in wanted_verdicts:
            continue
        # '확인 필요' 인데 신청 기간조차 없는 건(상시 카탈로그 등)은 자동 초안을 만들지 않는다 — 큐가 수십 건으로 불어나 정작 급한 것이 묻힌다.
        # 필요하면 --id 로 명시해 만든다.
        if mr.verdict == "needs_review" and not mr.deadline and not force:
            continue
        md_path, json_path = draft_paths(nid)
        if json_path.exists() and not redo:
            out.append(load_draft(nid))     # type: ignore[arg-type]
            continue
        n, rec = load_notice(nid), load_extraction(nid)
        if n is None or rec is None:
            continue
        md, d = build_draft(n, rec.requirements, mr, prof, llm)
        md_path.write_text(md, encoding="utf-8")
        json_path.write_text(d.model_dump_json(indent=2), encoding="utf-8")
        out.append(d)
        print(f"  초안 생성 [{VERDICT_LABEL[mr.verdict]}] {d.scholarship_name[:50]}  → {d.markdown_path}  ({d.generated_by})")
    print(f"\n승인 대기 초안 {sum(1 for d in out if d.status == 'pending_approval')}건 — `python -m scripts.approve list` 로 확인")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", action="append")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--only-eligible", action="store_true")
    ap.add_argument("--profile", type=Path, default=None)
    a = ap.parse_args(argv)
    run(a.id, a.redo, a.only_eligible, a.profile, force=bool(a.id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
