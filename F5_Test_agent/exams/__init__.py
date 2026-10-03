"""F5 시험 공부 일정 자동 추천 — 시험일과 자료 분량을 보고 '오늘 몇 쪽'을 역산한다. 구조는 ../README.md.

전부 표준 라이브러리 (+ api.py 만 fastapi) — config · store · notices · scope · plan · service · api

  notices  e클래스 공지에서 시험을 찾는다 (정규식 · 근거 원문 · 신뢰도)     F5-R01·R02
  scope    범위 안 F4 자료의 쪽수 합계                                    F5-R10·R11
  plan     역산 계산기 (순수 함수) — 날짜별 분량 · 경고 · 조정안             F5-R20~R26
  service  시험 목록 · 미리보기 · 등록 · 진도 · 재조정 · 캘린더 연동          F5-R30~R37
"""

__all__ = ["config", "store", "notices", "scope", "plan", "service", "api"]
