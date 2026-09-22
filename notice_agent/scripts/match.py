"""3단계 판정 — 자격 요건 vs 사용자 프로필 규칙 매칭 (순수 함수).  (기능명세서 DF-5 ④, AI_MODULES `notice` 완료기준 2~5)

    python -m scripts.match                    # data/extracted/*.json 전부 판정 → data/matches/
    python -m scripts.match --profile data/profile.json --id aisw_dept:945245

원칙 (역할별 분해서 1장 "판단과 계산을 섞지 않는다")
  - 여기서는 LLM 을 부르지 않는다. "18학점 이상" 은 계산의 영역이다. 같은 입력 → 항상 같은 출력.
  - 판정마다 근거를 남긴다: "3학년 이상 조건 미충족 (현재 2학년)".
  - 프로필에 없는 항목은 '모름(unknown)' 이지 '불충족' 이 아니다 → needs_review.
  - 추출 신뢰도가 문턱(config.CONFIDENCE_THRESHOLD) 미만이면 결과가 어떻게 나오든 needs_review.
    (놓치는 것이 잘못 알리는 것보다 나쁘다 — 애매하면 사람에게 보낸다)

규칙 표와 경계값 정의는 references/matching-rules.md, 테스트는 scripts/tests/test_match.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from typing import Optional

from . import config as C
from .collect import load_notice
from .extract import load_extraction
from .schemas import GPA, MatchResult, Profile, Reason, Requirements, Verdict
from .textutil import days_until, sanitize_filename

RECENT_EXPIRY_DAYS = 21     # 저신뢰 추출에서 이 일수 안에 '지난' 마감은 expired 대신 needs_review

FIELD_GROUP_ALIASES = {
    "공학계열": ("공학", "이공", "공대", "이공계", "자연과학 및 공학", "이공·상경·인문사회", "전 계열"),
    "자연과학계열": ("자연", "이공", "이공계", "자연과학 및 공학", "이공·상경·인문사회", "전 계열"),
    "인문사회계열": ("인문", "사회", "인문사회", "상경·인문사회", "이공·상경·인문사회", "전 계열"),
    "상경계열": ("상경", "경영", "경제", "이공·상경·인문사회", "전 계열"),
    "예체능계열": ("예체능", "예능", "체육", "전 계열"),
    "의약계열": ("의학", "보건", "의약", "전 계열"),
}


# ── 도우미 ──────────────────────────────────────────────────

def _r(field: str, status: str, message: str, evidence: Optional[str] = None) -> Reason:
    return Reason(field=field, status=status, message=message, evidence=evidence)   # type: ignore[arg-type]


def evidence_for(req: Requirements, field: str) -> Optional[str]:
    for e in req.evidence:
        if e.field == field and e.quote:
            return e.quote
    return None


def gpa_on_scale(prof: Profile, target: GPA, basis_last: bool) -> tuple[Optional[float], str]:
    """프로필 평점을 요건 척도로. 척도가 다르면 (None, 이유). 임의 환산은 하지 않는다 — 학교마다 환산표가 달라 틀리면 손해가 크다."""
    if basis_last:
        g, pct, label = prof.last_semester_gpa, prof.last_semester_gpa_percent, "직전학기"
        if g is None and pct is None:
            g, pct, label = prof.gpa, prof.gpa_percent, "전체(직전학기 값 없음)"
    else:
        g, pct, label = prof.gpa, prof.gpa_percent, "전체"
    if target.scale == 100:
        return (pct, label) if pct is not None else (None, f"{label} 백분위 점수(gpa_percent) 가 프로필에 없음")
    if g is None:
        return None, f"{label} 평점이 프로필에 없음"
    if abs(g.scale - target.scale) < 1e-6:
        return g.value, label
    return None, f"척도 불일치 (요건 {target.scale} 만점, 프로필 {g.scale} 만점) — 환산 필요"


# ── 개별 규칙 ──────────────────────────────────────────────

def check_grade(req: Requirements, prof: Profile) -> Optional[Reason]:
    if req.grades_allowed is None:
        return None
    ev = evidence_for(req, "grades_allowed")
    allowed = sorted(set(req.grades_allowed))
    label = ",".join(map(str, allowed)) + "학년"
    if prof.grade is None:
        return _r("grades_allowed", "unknown", f"학년 조건({label}) — 프로필에 학년 없음", ev)
    if prof.grade in allowed:
        return _r("grades_allowed", "pass", f"학년 조건 충족 ({label} / 현재 {prof.grade}학년)", ev)
    return _r("grades_allowed", "fail", f"학년 조건 미충족 ({label} / 현재 {prof.grade}학년)", ev)


def check_semesters(req: Requirements, prof: Profile) -> Optional[Reason]:
    if req.min_semesters_completed is None:
        return None
    ev = evidence_for(req, "min_semesters_completed")
    need = req.min_semesters_completed
    if prof.semesters_completed is None:
        return _r("min_semesters_completed", "unknown", f"{need}학기 이상 재학 조건 — 프로필에 이수 학기 수 없음", ev)
    if prof.semesters_completed >= need:
        return _r("min_semesters_completed", "pass", f"재학 학기 조건 충족 ({need}학기 이상 / 현재 {prof.semesters_completed}학기)", ev)
    return _r("min_semesters_completed", "fail", f"재학 학기 조건 미충족 ({need}학기 이상 / 현재 {prof.semesters_completed}학기)", ev)


def check_gpa(req: Requirements, prof: Profile) -> Optional[Reason]:
    if req.min_gpa is None:
        return None
    ev = evidence_for(req, "min_gpa")
    t = req.min_gpa
    basis_last = (t.basis or "").startswith("직전")
    val, label = gpa_on_scale(prof, t, basis_last)
    need = f"{t.value:g}/{t.scale:g} 이상" + (f" ({t.basis})" if t.basis else "")
    if val is None:
        return _r("min_gpa", "unknown", f"성적 조건 {need} — {label}", ev)
    if val + 1e-9 >= t.value:
        return _r("min_gpa", "pass", f"성적 조건 충족 ({need} / {label} {val:g})", ev)
    return _r("min_gpa", "fail", f"성적 조건 미충족 ({need} / {label} {val:g})", ev)


def check_credits(req: Requirements, prof: Profile) -> list[Reason]:
    out = []
    if req.min_credits_total is not None:
        ev = evidence_for(req, "min_credits_total")
        need = req.min_credits_total
        if prof.earned_credits is None:
            out.append(_r("min_credits_total", "unknown", f"누적 {need}학점 이상 조건 — 프로필에 취득학점 없음", ev))
        elif prof.earned_credits >= need:
            out.append(_r("min_credits_total", "pass", f"누적 학점 조건 충족 ({need}학점 이상 / 현재 {prof.earned_credits}학점)", ev))
        else:
            out.append(_r("min_credits_total", "fail", f"누적 학점 조건 미충족 ({need}학점 이상 / 현재 {prof.earned_credits}학점)", ev))
    if req.min_credits_last_semester is not None:
        ev = evidence_for(req, "min_credits_last_semester")
        need = req.min_credits_last_semester
        if prof.last_semester_credits is None:
            out.append(_r("min_credits_last_semester", "unknown", f"직전학기 {need}학점 이상 조건 — 프로필에 직전학기 이수학점 없음", ev))
        elif prof.last_semester_credits >= need:
            out.append(_r("min_credits_last_semester", "pass", f"직전학기 학점 조건 충족 ({need}학점 이상 / {prof.last_semester_credits}학점)", ev))
        else:
            out.append(_r("min_credits_last_semester", "fail", f"직전학기 학점 조건 미충족 ({need}학점 이상 / {prof.last_semester_credits}학점)", ev))
    return out


def _norm(s: str) -> str:
    return re.sub(r"[\s·,()\[\]]+", "", s or "")


def _major_hit(term: str, prof: Profile) -> Optional[bool]:
    """term(요건의 학과/계열 표기)가 프로필과 맞는가. True/False/None(판단 불가)."""
    t = _norm(term)
    if not t:
        return None
    if t in ("전체", "전학과", "전공무관", "제한없음", "모든학과", "전계열"):
        return True
    names = [_norm(x) for x in (prof.department, prof.major, prof.college) if x]
    for nm in names:
        if nm and (nm in t or t in nm):
            return True
    if prof.field_group:
        fg = _norm(prof.field_group)
        if fg in t or t in fg:
            return True
        for alias in FIELD_GROUP_ALIASES.get(prof.field_group, ()):
            if _norm(alias) in t:
                return True
    # 학과/학부/전공 이름이 명시돼 있는데 우리 이름과 다르면 '불일치'로 볼 수 있다
    if re.search(r"(학부|학과|전공)$", t) and names:
        return False
    return None      # 계열·모호한 표현인데 프로필 계열 정보로도 못 가림


def check_major(req: Requirements, prof: Profile) -> Optional[Reason]:
    reasons = []
    if req.major_include:
        ev = evidence_for(req, "major_include")
        hits = [_major_hit(t, prof) for t in req.major_include]
        label = "/".join(req.major_include)
        if any(h is True for h in hits):
            reasons.append(_r("major_include", "pass", f"전공 조건 충족 ({label})", ev))
        elif all(h is False for h in hits):
            reasons.append(_r("major_include", "fail", f"전공 조건 미충족 ({label} / 현재 {prof.department or prof.major or '?'})", ev))
        else:
            reasons.append(_r("major_include", "unknown", f"전공 조건 확인 필요 ({label} / 프로필 계열 정보로 판단 불가)", ev))
    if req.major_exclude:
        ev = evidence_for(req, "major_exclude")
        hits = [_major_hit(t, prof) for t in req.major_exclude]
        if any(h is True for h in hits):
            reasons.append(_r("major_exclude", "fail", f"제외 전공에 해당 ({'/'.join(req.major_exclude)})", ev))
        elif any(h is None for h in hits):
            reasons.append(_r("major_exclude", "unknown", f"제외 전공 확인 필요 ({'/'.join(req.major_exclude)})", ev))
        else:
            reasons.append(_r("major_exclude", "pass", "제외 전공에 해당하지 않음", ev))
    if not reasons:
        return None
    # fail > unknown > pass 순으로 하나를 대표로 (여러 개면 전부 붙인다)
    return reasons if len(reasons) > 1 else reasons[0]     # type: ignore[return-value]


def check_enrollment(req: Requirements, prof: Profile) -> Optional[Reason]:
    if not req.enrollment_status:
        return None
    ev = evidence_for(req, "enrollment_status")
    if not prof.enrollment_status:
        return _r("enrollment_status", "unknown", f"학적 조건({'/'.join(req.enrollment_status)}) — 프로필에 학적 상태 없음", ev)
    if prof.enrollment_status in req.enrollment_status:
        return _r("enrollment_status", "pass", f"학적 조건 충족 ({prof.enrollment_status})", ev)
    return _r("enrollment_status", "fail", f"학적 조건 미충족 ({'/'.join(req.enrollment_status)} / 현재 {prof.enrollment_status})", ev)


def check_income(req: Requirements, prof: Profile) -> Optional[Reason]:
    if req.income_bracket_max is None:
        return None
    ev = evidence_for(req, "income_bracket_max")
    need = req.income_bracket_max
    if prof.income_bracket is None:
        return _r("income_bracket_max", "unknown", f"학자금 지원구간 {need}구간 이하 조건 — 프로필에 구간 정보 없음 (한국장학재단에서 확인)", ev)
    if prof.income_bracket <= need:
        return _r("income_bracket_max", "pass", f"소득구간 조건 충족 ({need}구간 이하 / 현재 {prof.income_bracket}구간)", ev)
    return _r("income_bracket_max", "fail", f"소득구간 조건 미충족 ({need}구간 이하 / 현재 {prof.income_bracket}구간)", ev)


def check_nationality(req: Requirements, prof: Profile) -> Optional[Reason]:
    if not req.nationality:
        return None
    ev = evidence_for(req, "nationality")
    if not prof.nationality:
        return _r("nationality", "unknown", f"국적 조건({req.nationality}) — 프로필에 국적 없음", ev)
    if _norm(prof.nationality) in _norm(req.nationality) or _norm(req.nationality) in _norm(prof.nationality):
        return _r("nationality", "pass", f"국적 조건 충족 ({req.nationality})", ev)
    return _r("nationality", "fail", f"국적 조건 미충족 ({req.nationality} / 현재 {prof.nationality})", ev)


def check_residency(req: Requirements, prof: Profile) -> Optional[Reason]:
    if not req.residency:
        return None
    ev = evidence_for(req, "residency") or req.residency
    for region in (prof.residence_region, prof.high_school_region):
        if region and _norm(region) and _norm(region) in _norm(req.residency):
            return _r("residency", "pass", f"지역 조건에 해당 ({region})", ev)
    return _r("residency", "unknown", f"지역 조건 확인 필요: {req.residency[:80]}", ev)


def check_others(req: Requirements) -> list[Reason]:
    """봉사·추천·수상 같은 비정형 조건은 자동으로 못 가린다. 사람이 볼 수 있게 unknown 으로 남긴다."""
    return [_r("other_conditions", "unknown", f"추가 조건 확인 필요: {c[:100]}", c) for c in req.other_conditions[:6]]


# ── 판정 ────────────────────────────────────────────────────

def decide(req: Requirements, prof: Profile, today: Optional[date] = None,
           is_result_notice: bool = False, threshold: float = C.CONFIDENCE_THRESHOLD) -> MatchResult:
    today = today or date.today()
    reasons: list[Reason] = []
    for r in (check_grade(req, prof), check_semesters(req, prof), check_gpa(req, prof), check_enrollment(req, prof),
              check_income(req, prof), check_nationality(req, prof), check_residency(req, prof)):
        if r is not None:
            reasons.append(r)
    reasons += check_credits(req, prof)
    mj = check_major(req, prof)
    if isinstance(mj, list):
        reasons += mj
    elif mj is not None:
        reasons.append(mj)
    reasons += check_others(req)
    for ex in req.exclusions[:6]:
        reasons.append(_r("exclusions", "unknown", f"제외 사유에 해당하지 않는지 확인: {ex[:100]}", ex))

    deadline = req.application_period.end if req.application_period else None
    left = days_until(deadline, today) if deadline else None
    unknown = [r.field for r in reasons if r.status == "unknown"]
    fails = [r for r in reasons if r.status == "fail"]

    verdict: Verdict
    if is_result_notice:
        verdict = "not_applicable"
        reasons.insert(0, _r("notice_type", "unknown", "선발 결과·홍보성 공지 — 신청 대상이 아님"))
    elif deadline and left is not None and left < 0 and (req.confidence >= threshold or left < -RECENT_EXPIRY_DAYS):
        # 저신뢰 추출의 마감일은 틀릴 수 있다 — 최근 며칠 안에 '지난' 것으로 나온 건은 버리지 않고 확인으로 보낸다
        verdict = "expired"
        reasons.insert(0, _r("deadline", "fail", f"신청 마감 지남 ({deadline[:16]})", req.application_period.raw if req.application_period else None))
    elif deadline and left is not None and left < 0:
        verdict = "needs_review"
        reasons.insert(0, _r("deadline", "unknown", f"마감 지났을 수 있음 ({deadline[:16]}, 추출 신뢰도 {req.confidence:.2f}) — 원문 확인",
                             req.application_period.raw if req.application_period else None))
    elif req.needs_ocr or req.confidence < threshold:
        verdict = "needs_review"
        why = "본문이 이미지라 요건을 읽지 못함" if req.needs_ocr else f"추출 신뢰도 {req.confidence:.2f} < {threshold} (자동 판정 보류)"
        reasons.insert(0, _r("extraction", "unknown", why))
    elif fails:
        verdict = "ineligible"
    elif unknown:
        verdict = "needs_review"
    else:
        verdict = "eligible"
    return MatchResult(notice_id="", verdict=verdict, reasons=reasons,
                       unknown_fields=list(dict.fromkeys(unknown)), deadline=deadline, days_left=left,
                       confidence=req.confidence)


# ── 파일 입출력 / CLI ────────────────────────────────────────

def load_profile(path: Optional[Path] = None) -> Profile:
    p = Path(path) if path else C.PROFILE_FILE
    if not p.exists():
        raise FileNotFoundError(
            f"프로필 파일이 없습니다: {p}\n  assets/profile.example.json 을 data/profile.json 으로 복사해 채우거나 "
            f"`python -m scripts.profile_from_hakstd` 로 학사정보시스템에서 가져오세요.")
    return Profile.model_validate(json.loads(p.read_text(encoding="utf-8")))


def match_path(notice_id: str) -> Path:
    return C.MATCH_DIR / f"{sanitize_filename(notice_id.replace(':', '_'))}.json"


def load_match(notice_id: str) -> Optional[MatchResult]:
    p = match_path(notice_id)
    return MatchResult.model_validate_json(p.read_text(encoding="utf-8")) if p.exists() else None


def run(profile_path: Optional[Path] = None, ids: Optional[list[str]] = None, quiet: bool = False) -> list[MatchResult]:
    C.ensure_dirs()
    prof = load_profile(profile_path)
    paths = [C.EXTRACT_DIR / f"{sanitize_filename(i.replace(':', '_'))}.json" for i in ids] if ids else sorted(C.EXTRACT_DIR.glob("*.json"))
    results = []
    for p in paths:
        if not p.exists():
            continue
        rec = load_extraction(json.loads(p.read_text(encoding="utf-8"))["notice_id"])
        if rec is None:
            continue
        n = load_notice(rec.notice_id)
        mr = decide(rec.requirements, prof, is_result_notice=bool(n and n.is_result_notice))
        mr.notice_id = rec.notice_id
        match_path(rec.notice_id).write_text(mr.model_dump_json(indent=2), encoding="utf-8")
        results.append(mr)
        if not quiet:
            title = (n.title if n else rec.notice_id)[:48]
            top = next((r.message for r in mr.reasons if r.status == "fail"), None) or \
                  next((r.message for r in mr.reasons if r.status == "unknown"), "") or ""
            dl = f"D-{mr.days_left}" if mr.days_left is not None and mr.days_left >= 0 else (mr.deadline or "")
            print(f"  {mr.verdict:13s} {dl:>6s}  {title:48s} {top[:60]}")
    if not quiet:
        from collections import Counter
        c = Counter(r.verdict for r in results)
        print("\n판정 요약:", ", ".join(f"{k}={v}" for k, v in sorted(c.items())) or "없음")
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--profile", type=Path, default=None)
    ap.add_argument("--id", action="append")
    a = ap.parse_args(argv)
    run(a.profile, a.id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
