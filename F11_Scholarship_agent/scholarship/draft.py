"""신청서 초안 — 요구사항정의서 F11 6절 구성 그대로. 표준 라이브러리만.

    1. 기본 정보        {{이름}} / {{학번}} / 학과 · 학년 · 학적     ← 자리표시자 + 프로필 값 (이름·학번은 넣지 않는다, F11-R44)
    2. 지원 자격 정리    이 장학의 조건과 내 값 대조표                ← 판정 근거 그대로
    3. 지원 동기        문단                                        ← 재료(진로·활동·형편·강조점)만 근거로
    4. 학업 계획·포부    문단
    5. 제출 서류        체크리스트
    6. 신청 방법·마감    링크 · 방법 · 마감
    7. 확인 사항        "제출은 본인이 직접 합니다" 고정 문구

문단 규칙 (F11-D2 · 6절 AI팀 계약): 재료에 없는 경험·수상·봉사·가족 사항을 지어내지 않는다. 근거가 없으면
`{{구체적인 활동 경험을 적어 주세요}}` 처럼 무엇을 채울지 적은 빈칸. LLM 이 있으면 문단을 다듬고(같은 규칙을 프롬프트로),
없거나 실패하면 재료 문장을 그대로 잇는 템플릿 문단 + 빈칸 (F11-R48). 이전 초안을 가져오면 3·4절 문단을 옮기고 출처를 적는다 (F11-R46).
"""
from __future__ import annotations

import re
from typing import Callable, Optional

from . import llm as L

NEEDS_HARDSHIP = re.compile(r"생활|복지|가계|형편|저소득|희망|응원|창조|근로|주거|기초생활|차상위|소득")

SYSTEM = """너는 대학생의 장학금 신청서 문단을 돕는다. 반드시 지킬 것:
1. 학생이 준 '재료'에 있는 사실만 쓴다. 재료에 없는 경험·수상·봉사·가족 사항·숫자를 지어내지 않는다.
2. 근거가 없는 자리는 {{무엇을 채울지 적은 빈칸}} 으로 남긴다. 예: {{구체적인 활동 경험을 적어 주세요}}
3. 이름·학번은 쓰지 않는다. 필요하면 {{이름}} 으로 둔다.
4. 두 문단을 쓴다: '지원 동기' 와 '학업 계획·포부'. 각 300~500자, 존댓말 1인칭('저는').
5. 출력 형식: 첫 줄 '### 지원 동기', 문단, 빈 줄, '### 학업 계획·포부', 문단. 다른 말은 쓰지 않는다."""


def _section(body: str, n: int) -> Optional[str]:
    m = re.search(rf"^## {n}\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)", body, re.S | re.M)
    return m.group(1).strip() if m else None


def _paragraphs_template(d: dict, p: dict, m: dict) -> tuple[str, str]:
    name = d["title"]
    who = " ".join(x for x in (p.get("department") or p.get("college"), f"{p['grade']}학년" if p.get("grade") else None) if x)
    career = (m.get("careerGoal") or "").strip()
    acts = (m.get("activities") or "").strip()
    hard = (m.get("hardship") or "").strip()
    high = (m.get("highlights") or "").strip()
    need_hard = bool(NEEDS_HARDSHIP.search(f"{name} {d.get('scholarshipKind') or ''}")) or any(
        r["field"] in ("incomeMax", "groups") for r in d.get("reasons", []))
    s1 = [f"저는 {who or '{{소속·학년}}'} {{{{이름}}}}입니다."]
    s1.append(f"제 목표는 {career}입니다." if career else "{{진로 목표를 한 문장으로 적어 주세요}}")
    s1.append(f"그동안 {acts} 경험을 쌓아 왔습니다." if acts else "{{이 목표를 위해 해 온 구체적인 활동 경험을 적어 주세요}}")
    if need_hard:
        s1.append(hard if hard else "{{장학금이 필요한 사정(가정 형편 등)을 적어 주세요 — 쓰고 싶지 않으면 이 줄을 지우세요}}")
    s1.append(f"{name}에 지원하는 이유는 {{{{이 장학의 취지와 내 상황이 맞닿는 점을 적어 주세요}}}}.")
    s2 = []
    s2.append(f"장학금을 받게 되면 {career}을(를) 향해 {{{{다음 학기에 할 구체적인 공부·활동 계획을 적어 주세요}}}}."
              if career else "{{장학금을 받으면 어떤 공부·활동에 쓸지 구체적으로 적어 주세요}}")
    s2.append(f"특히 {high}" + ("" if high.endswith((".", "다")) else "을(를) 살리겠습니다.") if high
              else "{{강조하고 싶은 강점이나 다짐을 적어 주세요}}")
    s2.append("{{졸업 후 이 경험을 어떻게 이어 갈지 적어 주세요}}")
    return " ".join(s1), " ".join(s2)


def _paragraphs_llm(d: dict, p: dict, m: dict, chat: Callable[[str, str], str]) -> tuple[str, str]:
    facts = [f"- 장학 이름: {d['title']}", f"- 주관: {d.get('org') or '?'} ({d.get('scholarshipKind') or '?'})"]
    if d.get("amount"):
        facts.append(f"- 지원 내용: {d['amount']}")
    cond = [r["message"] for r in d.get("reasons", []) if r["field"] not in ("other", "exclusion")][:6]
    if cond:
        facts.append("- 자격 조건: " + " / ".join(cond))
    mine = [f"- 소속·학년: {p.get('college') or ''} {p.get('department') or ''} {p.get('grade') or '?'}학년".strip()]
    for k, label in (("careerGoal", "진로 목표"), ("activities", "활동 경험"), ("hardship", "가정 형편 메모"), ("highlights", "강조하고 싶은 점")):
        v = (m.get(k) or "").strip()
        mine.append(f"- {label}: {v if v else '(없음 — 빈칸으로 남길 것)'}")
    out = chat(SYSTEM, "[장학]\n" + "\n".join(facts) + "\n\n[재료]\n" + "\n".join(mine))
    a = re.search(r"###\s*지원\s*동기\s*\n(.*?)(?=###|\Z)", out, re.S)
    b = re.search(r"###\s*학업\s*계획[^\n]*\n(.*)", out, re.S)
    if not a or not b:
        raise L.LLMError("문단 형식이 맞지 않습니다")
    return a.group(1).strip(), b.group(1).strip()


def build(d: dict, p: dict, m: dict, *, borrowed: Optional[dict] = None,
          llm: Optional[Callable[[str, str], str]] = None) -> tuple[str, str]:
    """→ (마크다운 본문, generated_by: template | llm | borrowed)."""
    by = "template"
    note = None
    if borrowed:
        para1 = _section(borrowed["body"], 3) or ""
        para2 = _section(borrowed["body"], 4) or ""
        para1 = f"> {borrowed['title']} 초안에서 가져옴 — 이 장학에 맞게 고치세요\n\n{para1}"
        by = "borrowed"
    else:
        chat = llm or (L.chat if L.available() else None)
        para1 = para2 = ""
        if chat:
            try:
                para1, para2 = _paragraphs_llm(d, p, m, chat)
                by = "llm"
            except Exception as e:                 # noqa: BLE001 — LLM 이 실패해도 나머지(1·2·5·6)는 만든다 (6절 실패 규칙)
                note = f"문단 자동 작성에 실패해 골격만 넣었습니다 ({str(e)[:60]})"
        if by != "llm":
            para1, para2 = _paragraphs_template(d, p, m)

    who = " · ".join(x for x in (p.get("college"), p.get("department"), p.get("major")) if x) or "{{소속}}"
    rows = [r for r in d.get("reasons", []) if r["field"] not in ("other", "exclusion", "notice", "extraction", "deadline")]
    icon = {"pass": "충족", "fail": "미달", "unknown": "확인 필요"}
    table = "\n".join(f"| {r['label']} | {r.get('need') or '-'} | {r.get('mine') or '-'} | {icon[r['status']]} |" for r in rows)
    docs = "\n".join(f"- [ ] {x}" for x in d.get("documents") or []) or "- [ ] {{공지·첨부 양식에서 제출 서류를 확인해 적어 주세요}}"
    dl = (d.get("deadline") or "").replace("T", " ")[:16] or "공지 확인"
    parts = [
        f"# [신청서 초안] {d['title']}",
        "",
        "> 초안입니다. 어디에도 제출되지 않았습니다 — 확인·수정한 뒤 **본인이 직접** 신청하세요.",
        *(["> " + d["warning"]] if d.get("warning") else []),
        *(["> " + note] if note else []),
        "",
        "## 1. 기본 정보",
        "- 이름: {{이름}}",
        "- 학번: {{학번}}",
        f"- 소속: {who}",
        f"- 학년·학적: {p.get('grade') or '{{학년}}'}학년 · {p.get('enrollmentStatus') or '{{학적}}'}",
        "",
        "## 2. 지원 자격 정리",
        "| 조건 | 공지 | 내 값 | 판정 |",
        "|---|---|---|---|",
        table or "| (자동으로 읽은 조건 없음) | - | - | 원문 확인 |",
        "",
        "## 3. 지원 동기",
        para1,
        "",
        "## 4. 학업 계획·포부",
        para2,
        "",
        "## 5. 제출 서류",
        docs,
        "",
        "## 6. 신청 방법·마감",
        f"- 신청 방법: {d.get('applyMethod') or '원문 확인'}",
        *([f"- 신청 링크: {d['applyUrl']}"] if d.get("applyUrl") else []),
        f"- 마감: {dl}",
        f"- 원문: {d['url']}",
        "",
        "## 7. 확인 사항",
        "- 제출은 시스템이 하지 않습니다. 확인 후 본인이 직접 제출하세요.",
        "- {{ }} 로 남은 빈칸을 모두 채웠는지, 첨부 양식(HWP 등)이 따로 있으면 그 양식에 옮겨 적었는지 확인하세요.",
    ]
    return "\n".join(parts).strip() + "\n", by
