"""프로필 항목 정의 — 요구사항정의서 C2 4절 `Profile`. 항목마다 종류·검사·쓰는 기능·(민감하면) 쓰는 이유.

이름·학번은 **항목이 없다** (C2-D5) — 보내면 거절한다.
소속은 학과 마스터에서 고른 코드로만 저장한다 (C2-D1 자유 입력 금지) — deptCode·majorCode 를 같이 받는다.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable

ENROLLMENT = ("재학", "휴학", "졸업유예", "수료")
TRACKS = ("single", "double", "minor")
GPA_SCALES = (4.5, 4.3, 4.0)
REGIONS = ("서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남",
           "전북", "전남", "경북", "경남", "제주")
FLAGS = {                                   # 장학 매칭용 해당 사항 (C2-D4, 선택)
    "disability": "장애",
    "veteranFamily": "국가보훈 대상",
    "multiChild": "다자녀 가정",
    "singleParent": "한부모 가정",
    "basicLivelihood": "기초생활수급·차상위",
}
DRAFT_KEYS = ("careerGoal", "activities", "hardship")
FORBIDDEN = {"name", "studentId", "studentNo", "이름", "학번", "phone", "email", "birth"}


class Invalid(ValueError):
    pass


def _int(lo: int, hi: int) -> Callable[[Any], int]:
    def f(v: Any) -> int:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or int(v) != v:
            raise Invalid(f"정수여야 합니다: {v!r}")
        if not lo <= int(v) <= hi:
            raise Invalid(f"{lo}~{hi} 사이여야 합니다: {v}")
        return int(v)
    return f


def _choice(options: tuple) -> Callable[[Any], Any]:
    def f(v: Any) -> Any:
        if v not in options:
            raise Invalid(f"다음 중 하나여야 합니다: {', '.join(map(str, options))}")
        return v
    return f


def _gpa(v: Any) -> dict:
    if not isinstance(v, dict):
        raise Invalid("평점은 {value, scale, basis} 입니다")
    scale = float(v.get("scale") or 4.5)
    if scale not in GPA_SCALES:
        raise Invalid(f"평점 만점은 {', '.join(map(str, GPA_SCALES))} 중 하나입니다")
    try:
        value = float(v["value"])
    except (KeyError, TypeError, ValueError) as e:
        raise Invalid("평점 값이 없습니다") from e
    if not 0 <= value <= scale:
        raise Invalid(f"평점은 0~{scale} 사이여야 합니다")
    basis = str(v.get("basis") or "전체")[:20]
    return {"value": round(value, 2), "scale": scale, "basis": basis}      # 임의 환산 금지 — 받은 척도 그대로


def _text(maxlen: int) -> Callable[[Any], str]:
    def f(v: Any) -> str:
        if not isinstance(v, str):
            raise Invalid("글자여야 합니다")
        v = v.strip()
        if len(v) > maxlen:
            raise Invalid(f"{maxlen}자 이내로 적어 주세요")
        return v
    return f


def _flags(v: Any) -> dict:
    if not isinstance(v, dict) or any(k not in FLAGS for k in v):
        raise Invalid(f"해당 사항은 {', '.join(FLAGS)} 만 받습니다")
    return {k: bool(x) for k, x in v.items() if x}


def _interests(v: Any) -> list:
    if not isinstance(v, list) or len(v) > 30:
        raise Invalid("관심사는 30개 이내의 목록입니다")
    return [str(x).strip()[:30] for x in v if str(x).strip()]


def _draft(v: Any) -> dict:
    if not isinstance(v, dict) or any(k not in DRAFT_KEYS for k in v):
        raise Invalid(f"초안 재료는 {', '.join(DRAFT_KEYS)} 만 받습니다")
    return {k: str(x).strip()[:2000] for k, x in v.items() if str(x or "").strip()}


def _year(v: Any) -> int:
    return _int(1990, date.today().year + 1)(v)


# key: (구역, 검사 함수, 쓰는 기능, 이름, 민감정보면 쓰는 이유)
FIELDS: dict[str, tuple[str, Callable[[Any], Any], tuple[str, ...], str, str]] = {
    "admissionYear": ("basic", _year, ("F2",), "입학년도", ""),
    "track": ("basic", _choice(TRACKS), ("F2",), "이수유형", ""),
    "grade": ("basic", _int(1, 6), ("F1", "F11"), "학년", ""),
    "enrollmentStatus": ("basic", _choice(ENROLLMENT), ("F1", "F11"), "학적", ""),
    "semestersCompleted": ("academic", _int(0, 20), ("F11",), "이수 학기", ""),
    "gpa": ("academic", _gpa, ("F2", "F11"), "평점", ""),
    "lastSemesterGpa": ("academic", _gpa, ("F3", "F11"), "직전 학기 평점", ""),
    "earnedCredits": ("academic", _int(0, 400), ("F2", "F11"), "취득 학점", ""),
    "lastSemesterCredits": ("academic", _int(0, 40), ("F11",), "직전 학기 학점", ""),
    "incomeBracket": ("sensitive", _int(0, 10), ("F11",), "학자금 지원구간",
                      "국가장학금·소득 연계 장학의 자격 판정에만 씁니다"),
    "residenceRegion": ("sensitive", _choice(REGIONS), ("F11",), "거주 지역", "지자체 장학(주소지 요건) 판정에만 씁니다"),
    "highSchoolRegion": ("sensitive", _choice(REGIONS), ("F11",), "출신 고교 지역", "지역인재 장학 판정에만 씁니다"),
    "flags": ("sensitive", _flags, ("F11",), "해당 사항", "장애·보훈 등 대상 장학 판정에만 씁니다"),
    "interests": ("extra", _interests, ("F12",), "관심사", ""),
    "draftContext": ("extra", _draft, ("F11",), "신청서 초안 재료", ""),
}
# 소속 — 코드 셋을 한 덩어리로 다룬다 (학과 마스터에서 고른 한 줄)
AFFILIATION = ("collegeCode", "deptCode", "majorCode")
USED_BY_AFFILIATION = ("F1", "F2", "F11")
REQUIRED = ("deptCode", "admissionYear", "track")          # 단과대는 학과에서 정해진다 (C2-D2 필수 4개)
SENSITIVE = tuple(k for k, f in FIELDS.items() if f[0] == "sensitive")
IMPORTABLE = ("grade", "enrollmentStatus", "gpa", "earnedCredits", "semestersCompleted", "lastSemesterCredits")


def describe() -> dict:
    """화면이 쓰는 항목 설명 (이름 · 구역 · 쓰는 기능 · 민감정보 이유 · 선택지)."""
    return {
        "fields": {k: {"section": s, "usedBy": list(u), "label": l, **({"reason": r} if r else {})}
                   for k, (s, _, u, l, r) in FIELDS.items()},
        "affiliation": {"usedBy": list(USED_BY_AFFILIATION)},
        "required": list(REQUIRED),
        "enrollment": list(ENROLLMENT),
        "tracks": list(TRACKS),
        "regions": list(REGIONS),
        "flags": FLAGS,
    }
