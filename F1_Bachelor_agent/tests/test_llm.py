"""LLM 보조 추출 — 가짜 모델로. 원문에 없는 인용은 버리고, 날짜는 인용문에서 다시 읽는다."""
from datetime import date

from bachelor.llm import refine
from bachelor.models import Candidate
from bachelor.sources.base import Post

TEXT = "1. 기 간 : 2026. 10. 1.(목) ~ 10. 2.(금) 16:00\n2. 복수전공 신청: 2026. 11. 9.(월) 09:00 ~ 11. 13.(금) 18:00"
POST = Post(post_id="1", title="[학사안내] 최종 등록 공고", url="u", posted_at="2026-09-14", body=TEXT)


def fake(events):
    return lambda prompt: {"events": events}


def test_llm_adds_grounded_and_drops_invented():
    rule = [Candidate(title="최종 등록", start=date(2026, 10, 1), end=date(2026, 10, 2), confidence=0.8)]
    out = refine(POST, TEXT, rule, caller=fake([
        {"title": "최종 등록", "quote": "기 간 : 2026. 10. 1.(목) ~ 10. 2.(금) 16:00"},     # 규칙과 같음 → 신뢰도↑
        {"title": "복수전공 신청", "quote": "복수전공 신청: 2026. 11. 9.(월) 09:00 ~ 11. 13.(금) 18:00"},
        {"title": "지어낸 일정", "quote": "전과 신청: 2026. 12. 1. ~ 12. 5."},               # 원문에 없음 → 버림
    ]))
    titles = {c.title: c for c in out}
    assert titles["최종 등록"].confidence == 0.9 and "llm" in titles["최종 등록"].flags
    dm = titles["복수전공 신청"]
    assert (dm.start, dm.start_time, dm.end, dm.end_time) == (date(2026, 11, 9), "09:00", date(2026, 11, 13), "18:00")
    assert "지어낸 일정" not in titles


def test_llm_failure_keeps_rule_results():
    rule = [Candidate(title="최종 등록", start=date(2026, 10, 1), confidence=0.8)]
    assert refine(POST, TEXT, rule, caller=lambda p: None) == rule
