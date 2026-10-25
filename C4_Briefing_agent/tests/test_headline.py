"""맨 위 한 줄 요약 — 검증 규칙(한 줄 · 60자 · 격려 금지 · 지어낸 숫자 금지)과 실패하면 그 줄만 빠지는 것 (F10-R14 · 9절)."""
import urllib.error

from briefing import headline

FACTS = {"counts": {"deadlines": 3, "priority": 3, "classes": 2}, "deadlines": ["오늘 23:59 퀴즈 2회"], "priority": []}


def test_valid_line_passes():
    assert headline.validate("오늘은 마감 3건 중 퀴즈가 가장 급합니다.", FACTS) == "오늘은 마감 3건 중 퀴즈가 가장 급합니다."


def test_invented_number_is_dropped():
    assert headline.validate("오늘은 과제 5건이 급합니다.", FACTS) is None


def test_long_multiline_and_cheering_dropped():
    assert headline.validate("가" * 61, FACTS) is None
    assert headline.validate("수업 2개가 있습니다.\n마감 3건입니다.", FACTS) is None
    assert headline.validate("마감 3건, 화이팅", FACTS) is None
    assert headline.validate("마감 3건입니다!", FACTS) is None
    assert headline.validate("", FACTS) is None


def test_make_with_chat():
    line, model = headline.make(FACTS, chat=lambda s, u: '"수업 2개와 마감 3건이 있습니다."')
    assert line == "수업 2개와 마감 3건이 있습니다." and model


def test_make_failure_omits_line():
    def boom(s, u):
        raise urllib.error.URLError("timeout")
    assert headline.make(FACTS, chat=boom) == (None, None)
    assert headline.make(FACTS, chat=lambda s, u: "과제 9건!") == (None, None)


def test_nothing_to_summarize_or_no_llm():
    called = []
    assert headline.make({"counts": {}}, chat=lambda s, u: called.append(1) or "x") == (None, None)
    assert called == []
    assert headline.make(FACTS) == (None, None)        # conftest 가 C4_LLM=off — LLM 이 없으면 부르지 않는다
