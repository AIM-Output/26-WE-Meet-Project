"""수집·추출 단계가 주고받는 객체. 저장 형식(SQLite)은 store.py, 화면으로 나가는 형식은 service.py."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Optional

# 요구사항정의서 F1 6절 `type` + 시험(exam). 색·아이콘은 프론트 lib/academic.ts 에 있다.
TYPES = ("registration", "tuition", "course_reg", "grade", "exam", "vacation", "holiday", "event", "etc")


@dataclass
class Audience:
    """대상 조건. 전부 비어 있으면 '전교생'."""
    grades: Optional[list[int]] = None          # [1] 신입생, [4] 졸업(예정)자 …
    colleges: Optional[list[str]] = None        # 단과대 이름
    departments: Optional[list[str]] = None     # 학과(부)·전공 이름
    enrollment: Optional[list[str]] = None      # 재학 · 휴학 · 졸업유예
    roles: Optional[list[str]] = None           # faculty(교원) · graduate(대학원생). None 이면 학부생 포함
    raw: str = ""                               # 사람이 읽는 대상 문구 ('재학생', '4학년' …)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: Optional[dict]) -> "Audience":
        d = d or {}
        return cls(**{k: d.get(k) for k in ("grades", "colleges", "departments", "enrollment", "roles")},
                   raw=d.get("raw") or "")

    def merged(self, other: "Audience") -> "Audience":
        """다른 조건(원천이 정한 학과 등)을 덧붙인다."""
        def pick(a, b):
            return a if a else b
        return Audience(grades=pick(self.grades, other.grades), colleges=pick(self.colleges, other.colleges),
                        departments=pick(self.departments, other.departments),
                        enrollment=pick(self.enrollment, other.enrollment), roles=pick(self.roles, other.roles),
                        raw=self.raw or other.raw)


@dataclass
class Candidate:
    """원천 하나에서 뽑은 일정 하나 (병합 전)."""
    title: str
    start: Optional[date]                       # None 이면 날짜를 못 읽은 것(이미지 공지) → 확인 필요
    start_time: Optional[str] = None            # 'HH:MM'
    end: Optional[date] = None                  # 마지막 날(포함). 하루짜리면 None
    end_time: Optional[str] = None
    type: str = "etc"
    audience: Audience = field(default_factory=Audience)
    evidence: list[dict] = field(default_factory=list)   # [{field, quote}]
    confidence: float = 0.5
    semester: str = ""
    url: str = ""                               # 원문 (공지 글 주소 · 학사일정 페이지)
    post_id: Optional[str] = None               # 공지 글 번호 (학사일정 표는 None)
    posted_at: Optional[str] = None
    action_url: Optional[str] = None            # '수강신청 바로가기' 같은 바로 가는 링크
    action_label: Optional[str] = None
    flags: list[str] = field(default_factory=list)   # needs_ocr · year_guessed · attachment · llm · derived · split
