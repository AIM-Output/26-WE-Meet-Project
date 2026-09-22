"""2단계 추출 — 공지 원문 → 자격 요건 JSON (+근거·신뢰도).  (기능명세서 DF-5 ③, AI_MODULES `notice` 완료기준 1)

    python -m scripts.extract                 # data/notices/ 의 모든 공지 중 아직 추출 안 된 것
    python -m scripts.extract --all           # 전부 다시 (프롬프트 바꾼 뒤)
    python -m scripts.extract --id aisw_dept:945245 --show

동작
  1. 규칙 추출 (rules_extract.py) — 항상 실행. LLM 이 없어도 여기까지는 나온다.
  2. LLM 구조화 추출 (assets/prompts/extract_requirements.md) — LLM_MAIN 슬롯이 설정된 경우.
  3. 병합 + 근거 검증
       - LLM 이 준 evidence.quote 가 원문에 실제로 있는지 확인 (textutil.is_grounded). 없으면 그 필드 값은 버린다.
       - 규칙과 LLM 이 같은 값이면 신뢰도 ↑, 다르면 ↓ (+ notes 에 기록).
       - 본문이 이미지뿐이면 needs_ocr, 신뢰도 0 → 매칭 단계에서 자동으로 '확인 필요'.
  결과: data/extracted/<id>.json (ExtractionRecord)
"""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from pydantic import BaseModel, Field

from . import config as C
from .collect import iter_notices, load_notice
from .llm import LLM, LLMError, load_prompt
from .rules_extract import extract_rules
from .schemas import GPA, Evidence, ExtractionRecord, Notice, Period, Requirements
from .textutil import is_grounded, sanitize_filename

MAX_TEXT_CHARS = 14_000       # LLM 입력 상한 (긴 PDF 는 앞부분이 요강, 뒤는 서식인 경우가 대부분)
STRUCT_FIELDS = ("grades_allowed", "min_semesters_completed", "min_gpa", "min_credits_total",
                 "min_credits_last_semester", "major_include", "major_exclude", "enrollment_status",
                 "income_bracket_max", "nationality", "residency", "application_period")

# 근거 문장이 원문에 있더라도 그 필드와 '무관한' 문장이면 근거로 치지 않는다.
# (실측: '2학기 이상 재학' 을 근거로 학년 [2,3,4] 를 만든 사례 — 학기 문장은 학년 근거가 될 수 없다)
FIELD_HINT = {
    "grades_allowed": r"학년|신입생|재학생\s*전체|전\s*학년",
    "min_semesters_completed": r"학기",
    "min_gpa": r"\d",
    "min_credits_total": r"학점",
    "min_credits_last_semester": r"학점",
    "income_bracket_max": r"구간|소득|기초|차상위|수급",
    "enrollment_status": r"재학|휴학|복학|재적",
    "nationality": r"국적|대한민국|내국인|외국인",
    "application_period": r"\d",
    "major_include": r"학과|학부|전공|계열|대학",
    "major_exclude": r"학과|학부|전공|계열|대학|제외",
}
MIN_TEXT_FOR_TRUSTED_BODY = 300     # 이보다 긴 본문이면 LLM 이 needs_ocr 라고 해도 믿지 않는다


class LLMRequirements(BaseModel):
    """LLM 에게 요구하는 출력. Requirements 에서 시스템이 계산하는 필드(confidence/extractor)만 뺐다."""
    scholarship_name: Optional[str] = None
    provider: Optional[str] = None
    kind: Optional[str] = None
    grades_allowed: Optional[list[int]] = None
    min_semesters_completed: Optional[int] = None
    min_gpa: Optional[GPA] = None
    min_credits_total: Optional[int] = None
    min_credits_last_semester: Optional[int] = None
    major_include: Optional[list[str]] = None
    major_exclude: Optional[list[str]] = None
    enrollment_status: Optional[list[str]] = None
    income_bracket_max: Optional[int] = None
    nationality: Optional[str] = None
    residency: Optional[str] = None
    other_conditions: list[str] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    application_period: Optional[Period] = None
    apply_method: Optional[str] = None
    apply_url: Optional[str] = None
    required_documents: list[str] = Field(default_factory=list)
    amount: Optional[str] = None
    selection_count: Optional[str] = None
    contact: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)
    needs_ocr: bool = False
    notes: list[str] = Field(default_factory=list)


def extraction_path(notice_id: str):
    return C.EXTRACT_DIR / f"{sanitize_filename(notice_id.replace(':', '_'))}.json"


def load_extraction(notice_id: str) -> Optional[ExtractionRecord]:
    p = extraction_path(notice_id)
    if not p.exists():
        return None
    return ExtractionRecord.model_validate_json(p.read_text(encoding="utf-8"))


def _user_message(n: Notice) -> str:
    text = n.full_text
    if len(text) > MAX_TEXT_CHARS:
        text = text[:MAX_TEXT_CHARS] + "\n…(이하 생략)"
    return (f"[출처] {n.source_name}\n[게시일] {n.posted_at or '미상'}\n[제목] {n.title}\n[URL] {n.url}\n\n"
            f"[원문]\n{text}")


def _same(a, b) -> bool:
    if isinstance(a, GPA) and isinstance(b, GPA):
        return abs(a.value - b.value) < 1e-6 and abs(a.scale - b.scale) < 1e-6
    if isinstance(a, Period) and isinstance(b, Period):
        return (a.end or "")[:10] == (b.end or "")[:10]
    if isinstance(a, list) and isinstance(b, list):
        return sorted(map(str, a)) == sorted(map(str, b))
    return a == b


def merge(rules: Requirements, llm_out: LLMRequirements, source_text: str) -> Requirements:
    """LLM 결과를 근거 검증으로 거르고 규칙 결과와 합친다."""
    req = Requirements(**{k: v for k, v in llm_out.model_dump().items() if k in Requirements.model_fields})
    req.extractor = "llm+rules"
    notes = list(llm_out.notes)

    # 1) 근거 검증
    grounded_fields: set[str] = set()
    checked: list[Evidence] = []
    import re as _re
    for ev in llm_out.evidence:
        ok = is_grounded(ev.quote, source_text)
        hint = FIELD_HINT.get(ev.field)
        if ok and hint and not _re.search(hint, ev.quote):
            ok = False
            notes.append(f"{ev.field}: 근거 문장이 해당 항목과 무관해 보여 무시 ({ev.quote[:40]}…)")
        checked.append(Evidence(field=ev.field, quote=ev.quote[:300], grounded=ok))
        if ok:
            grounded_fields.add(ev.field)
    rules_fields = {e.field for e in rules.evidence}

    agree = conflict = dropped = 0
    for f in STRUCT_FIELDS:
        lv, rv = getattr(llm_out, f), getattr(rules, f, None)
        if lv is None:
            if rv is not None:                      # LLM 이 놓친 것을 규칙이 잡음
                setattr(req, f, rv)
            continue
        if f in grounded_fields:
            if rv is not None:
                if _same(lv, rv):
                    agree += 1
                else:
                    conflict += 1
                    notes.append(f"{f}: 규칙({rv!r}) 과 LLM({lv!r}) 불일치 — LLM 값 채택, 확인 권장")
            continue
        # 근거가 원문에 없다
        if rv is not None and _same(lv, rv):
            agree += 1                                # 규칙이 같은 값을 독립적으로 찾았으니 인정
        elif rv is not None:
            setattr(req, f, rv); dropped += 1
            notes.append(f"{f}: LLM 값의 근거를 원문에서 찾지 못해 규칙 값으로 대체")
        else:
            setattr(req, f, None); dropped += 1
            notes.append(f"{f}: LLM 값의 근거를 원문에서 찾지 못해 제외 ({lv!r})")

    # 2) 목록·문자열 필드는 합집합 / LLM 우선
    for f in ("other_conditions", "exclusions", "required_documents"):
        merged = list(dict.fromkeys(list(getattr(llm_out, f)) + list(getattr(rules, f))))
        setattr(req, f, merged[:12])
    for f in ("scholarship_name", "provider", "kind", "apply_method", "apply_url", "amount", "selection_count", "contact"):
        if getattr(req, f) is None and getattr(rules, f) is not None:
            setattr(req, f, getattr(rules, f))
    if req.kind not in ("교내", "교외", "국가", "사업단", "기타"):
        req.kind = rules.kind
    req.evidence = checked + [e for e in rules.evidence if e.field not in grounded_fields]
    req.unknown_fields = list(dict.fromkeys(llm_out.unknown_fields))
    # 본문이 충분히 길면 '이미지뿐' 이라는 LLM 의 판단은 믿지 않는다 (실측: 전문이 있는 공지에 needs_ocr=true 를 준 사례)
    req.needs_ocr = rules.needs_ocr or (llm_out.needs_ocr and len(source_text) < MIN_TEXT_FOR_TRUSTED_BODY)

    # 3) 신뢰도
    n_struct = sum(getattr(req, f) is not None for f in STRUCT_FIELDS)
    total_ev = max(len(llm_out.evidence), 1)
    grounded_ratio = sum(e.grounded for e in checked) / total_ev if llm_out.evidence else 0.5
    conf = 0.45 + 0.35 * grounded_ratio + 0.04 * min(agree, 4) - 0.12 * conflict - 0.08 * dropped
    if n_struct == 0 and not req.other_conditions:
        conf -= 0.2
        notes.append("구조화된 자격 요건을 찾지 못함")
    if len(source_text) < 200:
        conf -= 0.2
    if req.needs_ocr:
        conf = min(conf, 0.2)
    req.confidence = round(max(0.0, min(conf, 0.98)), 2)
    req.notes = list(dict.fromkeys(notes + rules.notes))[:12]
    return req


def extract_notice(n: Notice, llm: Optional[LLM] = None) -> ExtractionRecord:
    text = n.full_text
    rules = extract_rules(n.title, (n.body_text + "\n\n" + n.attachment_text).strip())
    version = None

    if n.body_is_image_only and not any(a.text_extracted for a in n.attachments):
        rules.needs_ocr = True
        rules.confidence = 0.0
        rules.notes.append("본문이 이미지라 텍스트가 없음 — OCR(DOC_PARSER) 또는 사람 확인 필요")
        if any(a.local_path for a in n.attachments):
            rules.notes.append("첨부 파일은 내려받았으나 텍스트를 읽지 못함 (HWP 등)")
        return ExtractionRecord(notice_id=n.id, requirements=rules)

    if n.is_result_notice:
        rules.notes.append("선발 결과·홍보성 글로 보임 — 신청 대상 아님")

    llm = llm or LLM()
    if llm.available and text.strip():
        version, system = load_prompt("extract_requirements")
        try:
            out = llm.structured("extract_requirements", system, _user_message(n), LLMRequirements)
            req = merge(rules, out, text)
        except LLMError as e:
            rules.notes.append(f"LLM 추출 실패 → 규칙 결과만 사용: {str(e)[:120]}")
            req = rules
    else:
        req = rules
        if not llm.available:
            req.notes.append("LLM 미설정 — 규칙 추출만 수행 (자동 판정 문턱 미만, 확인 필요로 분류됨)")
    return ExtractionRecord(notice_id=n.id, requirements=req, prompt_version=version)


def run(ids: Optional[list[str]] = None, redo: bool = False, show: bool = False) -> list[ExtractionRecord]:
    C.ensure_dirs()
    llm = LLM()
    if not llm.available:
        print("(LLM_MAIN 미설정 — 규칙 추출만 수행합니다. .env 를 채우면 LLM 추출이 켜집니다)")
    notices = [load_notice(i) for i in ids] if ids else list(iter_notices())
    notices = [n for n in notices if n is not None]
    out: list[ExtractionRecord] = []
    for n in notices:
        p = extraction_path(n.id)
        if p.exists() and not redo and not ids:
            out.append(load_extraction(n.id))     # type: ignore[arg-type]
            continue
        rec = extract_notice(n, llm)
        p.write_text(rec.model_dump_json(indent=2), encoding="utf-8")
        out.append(rec)
        r = rec.requirements
        flags = ("OCR필요 " if r.needs_ocr else "") + f"conf={r.confidence:.2f} {r.extractor}"
        print(f"  {n.id:36s} {flags:24s} 학년={r.grades_allowed} 평점={r.min_gpa.value if r.min_gpa else None}"
              f"{'/' + str(r.min_gpa.scale) if r.min_gpa else ''} 구간≤{r.income_bracket_max} "
              f"마감={r.application_period.end if r.application_period else None}")
        if show:
            print(rec.model_dump_json(indent=2, exclude_none=True))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--id", action="append", help="특정 공지 id 만 (여러 번 가능)")
    ap.add_argument("--all", action="store_true", help="이미 추출된 것도 다시")
    ap.add_argument("--show", action="store_true", help="추출 JSON 을 출력")
    a = ap.parse_args(argv)
    run(a.id, a.all, a.show)
    return 0


if __name__ == "__main__":
    sys.exit(main())
