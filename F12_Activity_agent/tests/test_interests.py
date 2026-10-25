"""관심사 등급 (요구사항정의서 F12 5절) — 제외어 > 키워드 > 태그(제목/본문) > LLM > 소속 · 짧은 영문 단어 경계."""
from activity import interests as I

MINE = {"tags": ["AI·SW", "공모전·경진대회"], "keywords": ["반도체", "공정실습"], "exclude": ["대학원생"]}


def g(title, body="", i=MINE, **kw):
    return I.grade(I.Text(title, body), i, **kw)


def test_short_english_word_boundary():
    assert I.Text("AICOSS 해커톤").where("AI") == "title"           # 뒤에 붙은 영문은 괜찮다
    assert I.Text("RAIN water festival").where("AI") is None         # 앞에 영문이 붙으면 아니다
    assert I.Text("the ai class").where("AI") == "title"             # 대소문자 무시
    assert I.Text("반도체 공정 실습 교육").where("공정실습") == "title"  # 공백 무시
    assert I.Text("East Asian Iron Club: Biology").where("IR") is None   # 'Iron' 의 Ir 은 IR 이 아니다 (2026-10-25 실측)
    assert I.Text("2026 IR 데모데이").where("IR") == "title" and I.Text("SW중심대학").where("SW") == "title"


def test_exclude_wins():
    r = g("반도체 공정실습 교육생 모집", "대상: 학부생 및 대학원생")
    assert r["grade"] == "other" and r["by"] == "exclude" and r["hits"][0]["label"] == "대학원생"


def test_keyword_title_or_body_is_match():
    assert g("반도체 설계 특강")["grade"] == "match"
    r = g("미래 산업 특강 안내", "반도체 소자 공정을 다룹니다")
    assert r["grade"] == "match" and r["hits"][0] == {"type": "keyword", "label": "반도체", "where": "body"}


def test_tag_title_match_body_related():
    r = g("2026 AI 아이디어 경진대회")
    assert r["grade"] == "match" and {h["label"] for h in r["hits"]} == {"AI·SW", "공모전·경진대회"}
    assert I.chips(r["hits"]) == ["AI·SW", "공모전·경진대회"]
    r = g("2026 청년 정책 포럼 참가자 모집", "발표 주제: 데이터로 본 청년 일자리")
    assert r["grade"] == "related" and I.chips(r["hits"]) == ["AI·SW (본문)"]


def test_informational_tag_hit_is_related():
    assert g("2026년도 9월호 AICOSS 레터", informational=True)["grade"] == "related"         # 소식지 — 알림 가지 않게
    assert g("반도체 소식지", informational=True)["grade"] == "match"                        # 내 키워드는 그대로


def test_nothing_hit_llm_then_affiliation_then_other():
    assert g("교내 합창단 단원 모집")["grade"] == "other"
    r = g("교내 합창단 단원 모집", llm={"grade": "related", "reason": "문화 활동"})
    assert r["grade"] == "related" and r["by"] == "llm"
    r = g("학과 MT 참가 신청", affiliated=True)
    assert r["grade"] == "related" and r["by"] == "affiliation"
    assert g("학과 소식지", affiliated=True, participation=False)["grade"] == "other"


def test_no_interests_no_grade():
    empty = {"tags": [], "keywords": [], "exclude": ["대학원생"]}
    assert g("2026 AI 경진대회", i=empty) == {"grade": None, "hits": [], "by": None}


def test_normalize_shapes():
    assert I.normalize(None) == {"tags": [], "keywords": [], "exclude": []}
    assert I.normalize(["AI·SW", "반도체", "x"]) == {"tags": ["AI·SW"], "keywords": ["반도체"], "exclude": []}   # 예전 목록 모양
    n = I.normalize({"tags": ["창업", "없는태그"], "keywords": ["  공정  실습 ", "a", "공정 실습"], "exclude": ["대학원생"]})
    assert n == {"tags": ["창업"], "keywords": ["공정 실습"], "exclude": ["대학원생"]}
    assert I.ihash(n) == I.ihash({"tags": ["창업"], "keywords": ["공정 실습"], "exclude": ["대학원생"]})
    assert I.ihash(n) != I.ihash({**n, "tags": []})
