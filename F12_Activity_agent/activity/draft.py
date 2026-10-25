"""신청서 초안 — F11 초안(요구사항정의서 F11 6절)과 같은 7단 구성을 대외활동에 맞게. 표준 라이브러리만.

    1. 기본 정보        이름 · 학번 · 소속 · 학년·학적 · 연락처 · (이메일) · 작성일  ← 초안 재료의 기본 정보(F11 basicinfo — 2026-10-25
                        사용자 결정), 모르는 값은 {{빈칸}}. LLM 에는 보내지 않고 다 만든 뒤 이 PC 에서 채운다
    2. 모집 정보 정리    주관 · 분류 · 대상(내 학년) · 신청 기간 · 활동 기간 · 장소 · 혜택 · 참가비 · 인원 · 걸린 관심사
    3·4. 문단 두 개     분류마다 제목이 다르다 — 공모전 '참가 동기 / 아이디어·준비 계획', 기자재 대여 '사용 목적 / 사용 계획',
                        취업·인턴 '지원 동기 / 직무 관련 경험·포부', 그 밖 '지원 동기 / 참여 계획·포부'
    5. 제출 서류        체크리스트
    6. 신청 방법·마감    링크 · 방법 · 마감
    7. 확인 사항        "제출은 시스템이 하지 않습니다" 고정 문구

문단 규칙 (F11 6절 AI팀 계약 그대로): 재료(진로·활동·보유 역량·강조점)와 내가 고른 관심사에 있는 사실만 쓴다.
없는 경험·수상·숫자를 지어내지 않고 `{{무엇을 채울지}}` 빈칸으로 둔다. LLM 이 있으면 문단을 다듬고(같은 규칙을 프롬프트로),
없거나 실패하면 재료 문장을 그대로 잇는 템플릿 + 빈칸. 이전 초안을 가져오면 3·4절 문단을 옮기고 출처를 적는다 (F11-R46).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Callable, Optional

from . import llm as L
from scholarship import basicinfo

HEADINGS = {
    "rental": ("사용 목적", "사용 계획 (품목·기간·장소)"),
    "contest": ("참가 동기", "아이디어·준비 계획"),
    "career": ("지원 동기", "직무 관련 경험·포부"),
    "startup": ("창업 동기", "아이템·추진 계획"),
    "global": ("지원 동기", "연수 계획·기대 효과"),
    "research": ("지원 동기", "관심 연구 분야·참여 계획"),
}
DEFAULT_HEADINGS = ("지원 동기", "참여 계획·포부")

SYSTEM = """너는 대학생이 교내 프로그램·공모전·대외활동·기자재 대여에 내는 신청서 문단을 돕는다. 반드시 지킬 것:
1. 학생이 준 '재료'와 '관심사'에 있는 사실만 쓴다. 재료에 없는 경험·수상·봉사·자격증·숫자를 지어내지 않는다.
2. 근거가 없는 자리는 {{무엇을 채울지 적은 빈칸}} 으로 남긴다. 예: {{구체적인 활동 경험을 적어 주세요}}
3. 이름·학번·연락처는 쓰지 않는다(받지도 않는다). 필요하면 {{이름}} 으로 둔다 — 학생의 PC 가 나중에 채운다.
4. 두 문단을 쓴다. 각 250~450자, 존댓말 1인칭('저는'). 공지가 분량을 정했으면 그에 맞춘다.
5. 출력 형식: 첫 줄 '### <첫 문단 제목>', 문단, 빈 줄, '### <둘째 문단 제목>', 문단. 다른 말은 쓰지 않는다."""


def headings(category: Optional[str]) -> tuple[str, str]:
    return HEADINGS.get(category or "", DEFAULT_HEADINGS)


def _section(body: str, n: int) -> Optional[str]:
    m = re.search(rf"^## {n}\.[^\n]*\n(.*?)(?=^## \d+\.|\Z)", body, re.S | re.M)
    return m.group(1).strip() if m else None


def _interest_text(d: dict) -> str:
    labels = [h["label"] for h in d.get("hits") or [] if h.get("type") in ("tag", "keyword")]
    return "·".join(dict.fromkeys(labels))


def _paragraphs_template(d: dict, p: dict, m: dict) -> tuple[str, str]:
    name = d["title"]
    who = " ".join(x for x in (p.get("department") or p.get("college"), f"{p['grade']}학년" if p.get("grade") else None) if x)
    career = (m.get("careerGoal") or "").strip()
    acts = (m.get("activities") or "").strip()
    skills = (m.get("skills") or "").strip()
    high = (m.get("highlights") or "").strip()
    interest = _interest_text(d)
    me = f"저는 {who or '{{소속·학년}}'} {{{{이름}}}}입니다."
    if d.get("category") == "rental":
        s1 = [me, "{{빌리려는 기자재·공간과 쓰려는 곳(수업·과제·프로젝트 이름)을 적어 주세요}}",
              "{{왜 이 기자재·공간이 필요한지 한두 문장으로 적어 주세요}}"]
        s2 = ["- 품목·수량: {{빌릴 품목과 수량}}", "- 사용 기간: {{시작일 ~ 반납일}}", "- 사용 장소: {{어디서 쓰는지}}",
              "- 함께 쓰는 인원: {{없으면 이 줄을 지우세요}}", "대여 규정(반납 기한·파손 책임)을 확인했고 지키겠습니다."]
        return " ".join(s1), "\n".join(s2)
    s1 = [me]
    if interest:
        s1.append(f"평소 {interest}에 관심을 두고 있습니다.")
    s1.append(f"제 목표는 {career}입니다." if career else "{{진로 목표를 한 문장으로 적어 주세요}}")
    s1.append(f"그동안 {acts} 경험을 쌓아 왔습니다." if acts else "{{이 활동과 이어지는 내 경험을 적어 주세요}}")
    s1.append(f"{name}에 지원하는 이유는 {{{{이 활동의 내용과 내 관심·목표가 맞닿는 점을 적어 주세요}}}}.")
    s2: list[str] = []
    if d.get("category") == "contest":
        s2.append("{{제출할 아이디어·작품의 핵심을 한두 문장으로 적어 주세요}}")
        s2.append(f"{skills}을(를) 살려 준비하겠습니다." if skills else "{{준비에 쓸 수 있는 내 역량(도구·기술)을 적어 주세요}}")
        s2.append("{{팀이면 역할 분담, 혼자면 마감까지의 준비 일정을 적어 주세요}}")
    elif d.get("category") == "career":
        s2.append(f"{skills}을(를) 바탕으로 {{{{지원 직무에서 하고 싶은 일을 적어 주세요}}}}." if skills
                  else "{{지원 직무와 관련된 내 역량(전공 과목·도구·프로젝트)을 적어 주세요}}")
        s2.append("{{이 경험을 진로에 어떻게 이어 갈지 적어 주세요}}")
    else:
        s2.append("참여하게 되면 {{이 활동에서 해 보고 싶은 것을 구체적으로 적어 주세요}}.")
        if skills:
            s2.append(f"{skills}을(를) 살려 적극적으로 참여하겠습니다.")
        s2.append(f"특히 {high}" + ("" if high.endswith((".", "다")) else "을(를) 보여 드리겠습니다.") if high
                  else "{{강조하고 싶은 강점이나 다짐을 적어 주세요}}")
        s2.append(f"이 경험을 {career}(으)로 이어 가겠습니다." if career else "{{활동 뒤 학업·진로에 어떻게 이어 갈지 적어 주세요}}")
    return " ".join(s1), " ".join(s2)


def _paragraphs_llm(d: dict, p: dict, m: dict, chat: Callable[[str, str], str]) -> tuple[str, str]:
    h1, h2 = headings(d.get("category"))
    facts = [f"- 공지: {d['title']}", f"- 분류: {d.get('categoryLabel') or '?'} · 주관: {d.get('org') or '?'}"]
    for k, label in (("target", "모집 대상"), ("eventPeriod", "활동·교육 기간"), ("benefit", "혜택"), ("place", "장소")):
        if d.get(k):
            facts.append(f"- {label}: {d[k]}")
    mine = [f"- 소속·학년: {p.get('college') or ''} {p.get('department') or ''} {p.get('grade') or '?'}학년".strip()]
    if _interest_text(d):
        mine.append(f"- 내가 고른 관심사 중 이 공지에 걸린 것: {_interest_text(d)}")
    for k, label in (("careerGoal", "진로 목표"), ("activities", "활동 경험"), ("skills", "보유 역량·도구"), ("highlights", "강조하고 싶은 점")):
        v = (m.get(k) or "").strip()
        mine.append(f"- {label}: {v if v else '(없음 — 빈칸으로 남길 것)'}")
    out = chat(SYSTEM, f"[공지]\n" + "\n".join(facts) + f"\n\n[재료]\n" + "\n".join(mine)
               + f"\n\n[문단 제목]\n1. {h1}\n2. {h2}")
    parts = re.split(r"^###\s*[^\n]*\n", out, flags=re.M)
    paras = [x.strip() for x in parts if x.strip()]
    if len(paras) < 2:
        raise L.LLMError("문단 형식이 맞지 않습니다")
    return paras[0], paras[1]


def build(d: dict, p: dict, m: dict, *, borrowed: Optional[dict] = None,
          llm: Optional[Callable[[str, str], str]] = None, today: Optional[date] = None) -> tuple[str, str]:
    """→ (마크다운 본문, generated_by: template | llm | borrowed). m['basic'] = 기본 정보(service.materials 가 채운 것)."""
    h1, h2 = headings(d.get("category"))
    by = "template"
    note = None
    if borrowed:
        para1 = _section(borrowed["body"], 3) or ""
        para2 = _section(borrowed["body"], 4) or ""
        para1 = f"> {borrowed['title']} 초안에서 가져옴 — 이 공지에 맞게 고치세요\n\n{para1}"
        by = "borrowed"
    else:
        chat = llm or (L.chat if L.available() else None)
        para1 = para2 = ""
        if chat:
            try:
                para1, para2 = _paragraphs_llm(d, p, m, chat)
                by = "llm"
            except Exception as e:                 # noqa: BLE001 — LLM 이 실패해도 나머지(1·2·5·6)는 만든다
                note = f"문단 자동 작성에 실패해 골격만 넣었습니다 ({str(e)[:60]})"
        if by != "llm":
            para1, para2 = _paragraphs_template(d, p, m)

    basic = m.get("basic") or basicinfo.resolve(None, p)[0]
    grade_note = ""
    if d.get("grades") and p.get("grade"):
        grade_note = f" (내 {p['grade']}학년 {'포함' if p['grade'] in d['grades'] else '— 대상 학년이 아닐 수 있습니다'})"
    target = d.get("target") or ("·".join(map(str, d["grades"])) + "학년" if d.get("grades") else None)
    rows = [("주관", d.get("org")), ("분류", d.get("categoryLabel")), ("모집 대상", f"{target}{grade_note}" if target else None),
            ("신청 기간", (d.get("period") or {}).get("raw")), ("활동·교육 기간", d.get("eventPeriod")), ("장소", d.get("place")),
            ("혜택", d.get("benefit")), ("참가비", d.get("fee")), ("모집 인원", d.get("capacity")),
            ("내 관심사", _interest_text(d) or None)]
    table = "\n".join(f"| {k} | {str(v).replace('|', '/')} |" for k, v in rows if v)
    docs = "\n".join(f"- [ ] {x}" for x in d.get("documents") or []) or "- [ ] {{공지·첨부 양식에서 제출 서류를 확인해 적어 주세요}}"
    dl = (d.get("deadline") or "").replace("T", " ")[:16] or "공지 확인"
    parts = [
        f"# [신청서 초안] {d['title']}",
        "",
        "> 초안입니다. 어디에도 제출되지 않았습니다 — 확인·수정한 뒤 **본인이 직접** 신청하세요.",
        *(["> " + note] if note else []),
        "",
        "## 1. 기본 정보",
        *basicinfo.lines(basic, p, today),
        "",
        "## 2. 모집 정보 정리",
        "| 항목 | 공지 |",
        "|---|---|",
        table or "| (자동으로 읽은 정보 없음) | 원문 확인 |",
        "",
        f"## 3. {h1}",
        para1,
        "",
        f"## 4. {h2}",
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
        "- {{ }} 로 남은 빈칸을 모두 채웠는지, 공지의 신청 양식(HWP·구글폼 등)이 따로 있으면 그 양식에 옮겨 적었는지 확인하세요.",
    ]
    return basicinfo.fill("\n".join(parts).strip() + "\n", basic), by
