"""기능 간 공유 스키마 (AI → BE 인터페이스 계약).

역할별 분해서 5장의 `추출 출력 스키마` 계약에 해당한다. 필드를 바꾸면 BE·FE 화면이 같이 바뀌므로
바꿀 때는 references/schemas.md 도 함께 고치고 팀에 공유한다.

원칙
  - 모든 추출 값에는 **근거(evidence: 원문 문장)** 가 붙는다. 근거 없는 값은 신뢰도 0 취급.
  - 판정(MatchResult)은 LLM 이 아니라 match.py 의 규칙 코드가 만든다.
  - 확신이 없으면 needs_review. 자동으로 버리지(ineligible) 않는다.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ── 수집 ────────────────────────────────────────────────────

class Attachment(BaseModel):
    name: str
    url: str
    local_path: Optional[str] = None       # notice_agent/ 기준 상대경로 (내려받았을 때)
    text_extracted: bool = False           # PDF 에서 본문을 뽑아 추출기에 넣었는가


class Notice(BaseModel):
    id: str                                # "<source_key>:<게시글 고유번호>"
    source: str                            # config.SOURCES[].key
    source_name: str
    title: str
    url: str
    posted_at: Optional[str] = None        # YYYY-MM-DD
    writer: Optional[str] = None
    category: Optional[str] = None         # 게시판 말머리/카테고리 원문
    body_text: str = ""                    # 본문 텍스트 (HTML 제거)
    body_is_image_only: bool = False       # 본문이 이미지뿐 → OCR(DOC_PARSER) 없이는 추출 불가
    images: list[str] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    attachment_text: str = ""              # 첨부 PDF 에서 뽑은 텍스트
    content_hash: str = ""                 # 제목+본문 해시 (신규/수정 판별)
    fetched_at: str = Field(default_factory=_now)
    is_result_notice: bool = False         # 선발 결과·홍보 등 신청 대상이 아닌 글

    @property
    def full_text(self) -> str:
        parts = [self.title, self.body_text]
        if self.attachment_text:
            parts.append("[첨부 본문]\n" + self.attachment_text)
        return "\n\n".join(p for p in parts if p)


# ── 자격 요건 추출 ───────────────────────────────────────────

class Evidence(BaseModel):
    field: str                             # 어떤 필드의 근거인지
    quote: str                             # 원문 문장 (그대로)
    grounded: bool = True                  # 원문에서 실제로 찾았는가 (검증 후 채움)


class Period(BaseModel):
    start: Optional[str] = None            # ISO 8601 (YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM)
    end: Optional[str] = None
    raw: Optional[str] = None              # 원문 표기


class GPA(BaseModel):
    value: float
    scale: float = 4.5                     # 4.5 / 4.3 / 4.0 / 100
    basis: Optional[str] = None            # "직전학기" / "전체" / "전 학년" 등


class Requirements(BaseModel):
    """공지 1건에서 뽑은 자격 요건. 없는 항목은 None (제한 없음 또는 미확인 — 구분은 unknown_fields 로)."""
    scholarship_name: Optional[str] = None
    provider: Optional[str] = None                     # 주관 (학생과 / 재단명 / 사업단)
    kind: Optional[Literal["교내", "교외", "국가", "사업단", "기타"]] = None
    grades_allowed: Optional[list[int]] = None         # 예: [3, 4]. "3학년 이상" → [3, 4]
    min_semesters_completed: Optional[int] = None      # "2학기 이상 재학"
    min_gpa: Optional[GPA] = None
    min_credits_total: Optional[int] = None            # 누적 이수학점
    min_credits_last_semester: Optional[int] = None    # 직전학기 이수학점 (국가장학금 12학점 등)
    major_include: Optional[list[str]] = None          # 학과/학부/계열 (이 중 하나에 속해야)
    major_exclude: Optional[list[str]] = None
    enrollment_status: Optional[list[str]] = None      # ["재학"] / ["재학", "휴학"]
    income_bracket_max: Optional[int] = None           # 한국장학재단 학자금 지원구간 상한
    nationality: Optional[str] = None                  # "대한민국" 등
    residency: Optional[str] = None                    # 특정 지역 거주/출신 조건 원문
    other_conditions: list[str] = Field(default_factory=list)   # 구조화 못 한 조건 (봉사·추천·수상 등)
    exclusions: list[str] = Field(default_factory=list)         # 제외 사유
    application_period: Optional[Period] = None
    apply_method: Optional[str] = None                 # 신청 경로 (학사시스템 메뉴 / 재단 사이트 / 이메일 …)
    apply_url: Optional[str] = None
    required_documents: list[str] = Field(default_factory=list)
    amount: Optional[str] = None
    selection_count: Optional[str] = None
    contact: Optional[str] = None
    evidence: list[Evidence] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)     # 공지에 언급이 없어 알 수 없는 항목
    confidence: float = 0.0                            # 0~1. 근거 검증·규칙 교차확인 결과
    needs_ocr: bool = False                            # 본문이 이미지라 텍스트가 없음
    extractor: str = "rules"                           # "rules" | "llm+rules"
    notes: list[str] = Field(default_factory=list)     # 추출기가 남기는 메모 (사람이 볼 것)


class ExtractionRecord(BaseModel):
    notice_id: str
    requirements: Requirements
    extracted_at: str = Field(default_factory=_now)
    prompt_version: Optional[str] = None


# ── 사용자 프로필 ────────────────────────────────────────────

class Profile(BaseModel):
    """매칭에 필요한 최소 항목만. 이름·학번 같은 식별 정보는 넣지 않는다 (초안의 자리표시자로 대체)."""
    grade: Optional[int] = None                        # 학년 1~4
    semesters_completed: Optional[int] = None          # 이수(등록) 학기 수
    enrollment_status: Optional[str] = "재학"
    college: Optional[str] = None                      # 단과대학 (예: AI융합대학)
    department: Optional[str] = None                   # 학부/학과 (예: 인공지능학부)
    major: Optional[str] = None                        # 전공 (학부와 같으면 생략 가능)
    field_group: Optional[str] = None                  # 계열: 공학계열 / 자연과학계열 / 인문사회계열 …
    gpa: Optional[GPA] = None                          # 전체 평점
    gpa_percent: Optional[float] = None                # 백분위 환산 점수 (성적증명서 기준). 100점 척도 요건 비교용
    last_semester_gpa: Optional[GPA] = None
    last_semester_gpa_percent: Optional[float] = None
    earned_credits: Optional[int] = None               # 누적 취득학점
    last_semester_credits: Optional[int] = None
    income_bracket: Optional[int] = None               # 한국장학재단 학자금 지원구간 (모르면 None)
    nationality: Optional[str] = "대한민국"
    high_school_region: Optional[str] = None           # 출신 고교 지역 (지역인재 장학용)
    residence_region: Optional[str] = None             # 주소지 (지자체 장학용)
    interests: list[str] = Field(default_factory=list)
    flags: dict[str, bool] = Field(default_factory=dict)   # {"disability": False, "veteran_family": False, ...}
    # 초안 작성용 (선택). 비워두면 초안에 {{...}} 자리표시자가 남는다.
    draft_context: dict[str, str] = Field(default_factory=dict)   # {"career_goal": "...", "activities": "...", "hardship": "..."}


# ── 판정 ────────────────────────────────────────────────────

Verdict = Literal["eligible", "ineligible", "needs_review", "expired", "not_applicable"]


class Reason(BaseModel):
    field: str
    status: Literal["pass", "fail", "unknown"]
    message: str                                       # "3학년 이상 조건 미충족 (현재 2학년)"
    evidence: Optional[str] = None                     # 요건 근거 문장


class MatchResult(BaseModel):
    notice_id: str
    verdict: Verdict
    reasons: list[Reason] = Field(default_factory=list)
    unknown_fields: list[str] = Field(default_factory=list)   # 프로필에 없어 판단 못 한 항목
    deadline: Optional[str] = None
    days_left: Optional[int] = None
    confidence: float = 0.0                            # 추출 신뢰도를 그대로 넘긴다 (FE 표시용)
    matched_at: str = Field(default_factory=_now)


# ── 신청서 초안 (승인 대기 큐) ───────────────────────────────

DraftStatus = Literal["pending_approval", "approved", "rejected"]


class Draft(BaseModel):
    notice_id: str
    scholarship_name: str
    status: DraftStatus = "pending_approval"
    verdict: Verdict
    markdown_path: str                                 # data/drafts/<id>.md
    checklist: list[str] = Field(default_factory=list)  # 제출 서류 체크리스트
    apply_method: Optional[str] = None
    apply_url: Optional[str] = None
    deadline: Optional[str] = None
    generated_by: str = "template"                     # "template" | "llm"
    created_at: str = Field(default_factory=_now)
    decided_at: Optional[str] = None
    user_note: Optional[str] = None


# ── 알림 페이로드 (BE → FE 계약과 맞춤) ─────────────────────

class Alert(BaseModel):
    type: Literal["scholarship_match", "scholarship_review", "scholarship_deadline"]
    notice_id: str
    title: str
    url: str
    verdict: Verdict
    deadline: Optional[str] = None
    days_left: Optional[int] = None
    reasons: list[str] = Field(default_factory=list)
    draft_path: Optional[str] = None
    target_screen: str = "scholarship_detail"
    created_at: str = Field(default_factory=_now)
