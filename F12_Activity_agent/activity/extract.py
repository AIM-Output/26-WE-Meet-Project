"""공지 → 대외활동 기본 정보 (F12-R25 'F11 과 같은 추출기'). 표준 라이브러리만, LLM 없이 돈다.

F11 추출기(scholarship.extract)를 그대로 불러 신청 기간·제출 서류·신청 방법·링크·문의·선발 인원·학년·대학원 전용·이미지 공지를 얻고,
대외활동에 필요한 것을 더한다:
  - 말머리(boardCategory)   대표 공지 '[모집공고]·[공모전]·[취업정보]·[학사안내]…' · K2Web '[취업]' · COSS 분류
  - 분류(category)          기자재·공간 대여 · 공모전 · 창업 · 취업·인턴 · 해외 · 봉사 · 대외활동 · 연구 · 교육·프로그램 · 행사 · 기타
                            (학사 행정 안내 — 학사과·재무과 등 부서 글이나 정규학기 행정 제목 — 는 대외활동에서 뺀다. 학점교류는 남긴다)
  - 주관(host)              제목의 [기관] (말머리는 빼고) → 사업단 (없으면 service 가 작성 부서·원천 기관으로)
  - 대상 · 장소 · 활동/교육 기간 · 혜택(상금·활동비) · 참가비
  - 모집 글인가(participation) · 결과 발표 글인가(result)
모든 값에 근거(원문 한 줄)를 붙인다.
"""
from __future__ import annotations

import re
from datetime import timedelta
from typing import Optional

from . import interests as I
from scholarship import extract as sx           # F11 추출기 — 기간·서류·방법·링크 규칙을 그대로 쓴다
from scholarship.textutil import lines, nfkc, to_date

# 대표 공지·학과 게시판 말머리 — 제목 앞 [ ] 가 이것이면 주관이 아니라 분류다
BOARD_CATEGORIES = {"모집공고", "학사안내", "공모전", "대학생활", "채용공고", "취업정보", "행정공고", "입찰공고", "장학안내", "일반공지",
                    "공지", "공지사항", "안내", "행사", "특강", "학사", "취업", "장학", "일반", "모집", "교육", "대학원", "학부", "학과",
                    "기타", "홍보", "알림", "학생지원", "경진대회", "비교과", "프로그램", "학과공지", "학부공지", "행사안내", "채용"}
PARTICIPATION = re.compile(r"모집|신청|참가|참여|접수|선발|지원(?!금)|공모|대여|예약|수강생|교육생|등록\s*안내|선착순")
RESULT = re.compile(r"결과\s*(?:안내|발표|공지|공고|알림|공개)|(?:합격|선정|수상|당첨|최종\s*선발)자\s*(?:발표|공고|안내|명단)?|"
                    r"(?:합격|선정|수상|당첨|진출)\s*(?:팀|인원|과제)?\s*(?:발표|공고|명단)|(?:선발|합격|선정|수상)\s*(?:자\s*)?명단|"
                    r"명단\s*(?:발표|공고)|선발\s*결과|과제\s*선정\s*안내")
# 제목에 '(마감)' · '[마감]' — 게시판이 끝난 모집에 붙이는 표시 (AICOSS '(마감)글로벌 AI 역량강화 교육과정 …', 2026-10-10 실측)
CLOSED = re.compile(r"^\s*[(\[]\s*마감\s*[)\]]|[(\[]\s*마감\s*[)\]/,]|모집\s*마감\s*$|조기\s*마감")
_BULLET = r"^\s*(?:\d+\s*[.)]|[가-힣]\s*[.)]|[○●□■▶▷◦•\-*※◎◆◇▪]|\(\d+\)|[①-⑳])?\s*"
TARGET = r"(?:모집|참가|참여|신청|지원|교육|선발|활동)?\s*대\s*상(?:\s*자)?|(?:신청|지원|참가|참여)\s*자격|자격\s*(?:요건|조건)"
PLACE = r"(?:교육|운영|행사|대회|활동|실습)?\s*장\s*소|위\s*치"
EVENT = r"(?:교육|행사|활동|운영|대회|연수|프로그램|실습|캠프|파견|특강|과정|대여|사용|이용)\s*(?:기간|일시|일정)|일\s*시|기\s*간"
BENEFIT = r"혜\s*택|시상(?:\s*(?:내역|내용|규모|금))?|상\s*금|(?:지원|참가자?)\s*(?:내용|사항|혜택)|활동\s*(?:혜택|비)|특\s*전|수료\s*혜택"
FEE = r"참가비|수강료|참여비|교육비|이용료|대여료|비\s*용"


def _labeled(text: str, header: str, max_len: int = 160) -> tuple[Optional[str], Optional[str]]:
    """'모집대상: 재학생' · '□ 대상 | 학부 재학생'(표 한 행) · '2. 장소' 다음 줄 → (값, 근거 줄)."""
    ls = lines(text)
    # 머리 다음에는 ':' · '|'(표 칸) · 줄 끝만 — '대상자 선정 방법' 같은 문장을 값으로 집지 않게
    pat = re.compile(_BULLET + rf"(?:{header})\s*(?:[:：|]\s*|$)(.*)$")
    for i, ln in enumerate(ls):
        if len(ln) > 260:
            continue
        m = pat.match(ln)
        if not m:
            continue
        val = m.group(1).strip(" :：|-")
        if len(val) < 2 and i + 1 < len(ls):
            val = re.sub(_BULLET, "", ls[i + 1]).strip()
            if re.match(_BULLET + r"[가-힣 ]{1,8}\s*[:：]", ls[i + 1]):
                continue                          # 다음 줄이 또 다른 항목 머리 — 값이 비어 있다
        if 2 <= len(val):
            return val[:max_len], ln[:300]
    return None, None


def board_category(title: str, category: Optional[str] = None) -> Optional[str]:
    if category:
        return category.strip()[:20]
    m = re.match(r"^\s*\[([^\]]{1,14})\]", nfkc(title))
    return m.group(1).strip() if m else None


def clean_title(title: str) -> str:
    """제목 앞의 말머리 [모집공고] 같은 것만 떼고, [KIA] · [제주대학교] 같은 기관 괄호는 둔다."""
    t = nfkc(title).strip()
    while True:
        m = re.match(r"^\[([^\]]{1,14})\]\s*", t)
        if not m or m.group(1).strip() not in BOARD_CATEGORIES:
            return t
        t = t[m.end():]


def host_from_title(title: str) -> Optional[str]:
    for m in re.finditer(r"\[([^\]]{2,30})\]", nfkc(title)):
        s = m.group(1).strip()
        if s in BOARD_CATEGORIES or re.fullmatch(r"[~∼～]?[\d./()월일 ~∼～화수목금토월요]+(?:까지)?", s) or "마감" in s:
            continue
        return s
    return None


def _fix_year(period: Optional[dict], posted: Optional[str]) -> None:
    """연도 없는 '1. 5.(월)까지' 를 게시 연도로 읽어 게시일보다 한참 앞서면 다음 해로 (F11 collect._fix_year 와 같은 규칙)."""
    p = period or {}
    pd = to_date(posted)
    if not pd or not p.get("end") or (p.get("raw") and str(pd.year) in p["raw"]):
        return
    end = to_date(p["end"])
    if end and end < pd - timedelta(days=30):
        p["end"] = p["end"].replace(str(end.year), str(end.year + 1), 1)
        if p.get("start"):
            p["start"] = p["start"].replace(str(end.year), str(end.year + 1), 1)


def extract(title: str, text: str, *, unit: Optional[dict] = None, category: Optional[str] = None,
            writer: Optional[str] = None, image_only: bool = False, attachments_unread: int = 0, posted_at: Optional[str] = None,
            ocr: bool = False) -> dict:
    """제목 + 본문(+첨부 글자) → 대외활동 정보. unit = 이 글을 올린 사업단·부서(registry.unit_for).
    ocr = 글자 일부를 이미지에서 OCR 로 읽었다 — 'OCR 로 읽음' 안내(F11 extract 의 노트)와 화면 표시."""
    title = nfkc(title)
    text = nfkc(text)
    pd = to_date(posted_at)
    base = sx.extract(title, text, unit=unit, image_only=image_only, attachments_unread=attachments_unread,
                      default_year=pd.year if pd else None, ocr=ocr)
    _fix_year(base.get("period"), posted_at)
    bc = board_category(title, category)
    name = clean_title(title)
    if I.is_academic(title, writer):                  # 학사과·재무과 등의 정규학기 행정 — 대외활동에서 뺀다 (service · collect)
        key, label = "academic", I.academic_label()
    else:
        key, label = I.categorize(f"{bc or ''} {title}")
        if key == "other" and text:
            key, label = I.categorize(" ".join(lines(text)[:4])[:300])
    ev: dict[str, str] = {}
    if base.get("evidence", {}).get("period"):
        ev["period"] = base["evidence"]["period"]
    out: dict = {
        "extractor": "rules", "title": name, "boardCategory": bc, "category": key, "categoryLabel": label,
        "host": host_from_title(title) or (unit or {}).get("org"),        # 없으면 화면이 작성 부서·원천 기관으로 (service)
        "period": base.get("period"), "documents": base.get("documents") or [], "applyMethod": base.get("applyMethod"),
        "applyUrl": base.get("applyUrl"), "contact": base.get("contact"), "capacity": base.get("selectionCount"),
        "grades": base.get("grades"), "gradOnly": bool(base.get("gradOnly")), "foreignOnly": bool(base.get("foreignOnly")),
        "needsOcr": bool(base.get("needsOcr")), "ocr": bool(ocr), "attachmentsUnread": attachments_unread,
        "notes": base.get("notes") or [],
        "participation": bool(PARTICIPATION.search(title)) or bool(PARTICIPATION.search(" ".join(lines(text)[:6]))),
        "result": bool(RESULT.search(title)), "closedMark": bool(CLOSED.search(title)),
    }
    for field, header, n in (("target", TARGET, 160), ("place", PLACE, 120), ("eventPeriod", EVENT, 140),
                             ("benefit", BENEFIT, 160), ("fee", FEE, 100)):
        val, quote = _labeled(text, header, n)
        if field == "eventPeriod" and val and out["period"] and out["period"].get("raw") and val in out["period"]["raw"]:
            val = quote = None                    # 신청 기간 줄을 다시 집은 것
        out[field] = val
        if quote:
            ev[field] = quote
    if not out["capacity"]:
        m = re.search(r"(\d{1,4})\s*(?:명|팀)\s*(?:내외|이내|선발|모집|선착순)|선착순\s*(\d{1,4})\s*(?:명|팀)", text)
        out["capacity"] = (m.group(1) or m.group(2)) + ("팀" if "팀" in m.group(0) else "명") if m else None
    if not text.strip() and not image_only:
        out["notes"] = [*out["notes"], "본문을 읽지 못했습니다(로그인이 필요한 게시판이거나 외부 링크 글) — 제목으로만 분류했습니다. 원문에서 확인하세요"]
    if out["documents"]:
        ev["documents"] = out["documents"][0]
    out["evidence"] = ev
    return out
