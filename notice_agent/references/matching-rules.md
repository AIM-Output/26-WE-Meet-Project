# 매칭 판정 규칙 — `scripts/match.py`

**판정은 코드, 추출은 모델.** (역할별 분해서 1장 "판단과 계산을 섞지 않는다", AI_MODULES `notice` "매칭 판정은 LLM 이 아니라 규칙 코드로")
같은 `Requirements` + `Profile` → 항상 같은 `MatchResult`. 테스트: `scripts/tests/test_match.py`.

## 판정 순서

```
1. 결과·홍보성 공지(is_result_notice)            → not_applicable
2. 마감 지남 (end < today)
     추출 신뢰도 ≥ 0.6  또는  21일 넘게 지남      → expired
     그 외 (저신뢰 + 최근)                        → needs_review  "마감 지났을 수 있음 — 원문 확인"
3. needs_ocr  또는  confidence < 0.6              → needs_review  (규칙이 fail 을 내도 자동 판정하지 않음)
4. 조건 중 하나라도 fail                          → ineligible
5. 조건 중 하나라도 unknown                       → needs_review
6. 전부 pass                                      → eligible
```
마감 **당일**은 유효(`days_left == 0`). 마감 시각(`THH:MM`)은 날짜 단위로만 비교한다 — 당일 시각 경과 여부는 사용자가 확인.

## 조건별 규칙

| 요건 필드 | 프로필 필드 | pass | fail | unknown |
|---|---|---|---|---|
| `grades_allowed` | `grade` | grade ∈ allowed | grade ∉ allowed | grade 없음 |
| `min_semesters_completed` | `semesters_completed` | ≥ | < | 없음 |
| `min_gpa` (scale 4.5/4.3/4.0) | `gpa` (basis 직전학기면 `last_semester_gpa`, 없으면 `gpa` 로 대체하고 문구에 표시) | value ≥ min (같은 척도) | value < min | 평점 없음 **또는 척도 불일치** |
| `min_gpa` (scale 100) | `gpa_percent` / `last_semester_gpa_percent` | ≥ | < | 백분위 값 없음 |
| `min_credits_total` | `earned_credits` | ≥ | < | 없음 |
| `min_credits_last_semester` | `last_semester_credits` | ≥ | < | 없음 |
| `major_include` | `department` / `major` / `college` / `field_group` | 항목 중 하나라도 이름 포함 일치 또는 계열 별칭 일치 | 모든 항목이 `…학부/학과/전공` 으로 끝나는 구체 이름인데 전부 불일치 | 계열·모호 표현인데 프로필 계열로도 못 가림 |
| `major_exclude` | 위와 같음 | 어느 항목에도 안 걸림 | 걸림 | 판단 불가 항목 있음 |
| `enrollment_status` | `enrollment_status` | ∈ | ∉ | 없음 |
| `income_bracket_max` | `income_bracket` | ≤ | > | 없음 (대부분 없음 → 확인 필요) |
| `nationality` | `nationality` | 포함 일치 | 불일치 | 없음 |
| `residency` | `residence_region` / `high_school_region` | 지역명이 요건 문장에 포함 | — | 그 외 전부 (자동 fail 없음) |
| `other_conditions[]` | — | — | — | 항상 unknown (봉사·추천·수상·성별·가정형편 등) |
| `exclusions[]` | — | — | — | 항상 unknown ("제외 사유에 해당하지 않는지 확인") |

계열 별칭표 (`FIELD_GROUP_ALIASES`): `공학계열` ← 공학·이공·공대·이공계·"자연과학 및 공학"·"이공·상경·인문사회"·전 계열 / `자연과학계열`, `인문사회계열`, `상경계열`, `예체능계열`, `의약계열` 도 같은 방식.

## 왜 이렇게 보수적인가

- **놓치는 것(false negative)이 잘못 알리는 것보다 나쁘다** (AI_MODULES `notice` 주의). 그래서 모르는 값은 fail 이 아니라 unknown 이고, 저신뢰 추출은 결과와 무관하게 확인 필요다.
- 평점 척도 환산(4.3↔4.5, 4.5↔100)은 학교마다 표가 달라 **임의 환산하지 않는다**. 100점 척도 요건이 흔하므로(국가근로 70점, 국가장학금 80점) 프로필에 `gpa_percent` 를 성적증명서 기준으로 채워 두면 자동 판정 범위가 넓어진다.
- 전공 조건은 오탐 시 곧바로 비해당이 되므로, 규칙 추출 단계에서는 구조화하지 않고 LLM+근거검증을 통과한 값만 쓴다.

## 경계값 테스트 목록 (test_match.py)

평점 딱 3.5 = 통과 · 3.49 = 불충족 · 척도 다르면 확인 · 학점 딱 84 = 통과 · 마감 당일 = 유효 · 마감 전날 = expired(days_left −1) · 저신뢰 fail = 확인 · 이미지 본문 = 확인 · 결과 공지 = not_applicable · 최근 지난 저신뢰 마감 = 확인, 오래 지난 = expired · 같은 입력 → 같은 출력

## 인수 기준과의 연결

기능명세서 6장 "공지 매칭 정밀도 — 오매칭률 10% 이하" 는 `eligible`/`ineligible` 판정 중 사람이 뒤집은 비율로 잰다. `needs_review` 는 분모에 넣지 않는다 (판정을 유보한 것이므로). 수동 검수 결과는 `data/matches/<id>.json` 옆에 `review.json` 으로 남기고 `eval_ai-agent` 가 집계한다 (MVP 이후).
