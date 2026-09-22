# 입출력 계약 (JSON) — AI → BE 인터페이스

Pydantic 정의는 `scripts/schemas.py` 가 원본이다. 이 문서는 BE·FE 와 합의할 때 읽는 요약본.
역할별 분해서 5장의 `추출 출력 스키마`, `승인 대기 객체`, `알림 페이로드` 계약에 대응한다.
필드를 바꾸면 여기와 `scripts/schemas.py` 를 같이 고치고 이슈로 공유한다.

## 파일 배치 (파일 기반 → BE 가 붙으면 그대로 테이블/API 로)

| 단계 | 파일 | 스키마 | BE 대응 |
|---|---|---|---|
| 수집 | `data/notices/<source>/<id>.json` | `Notice` | `notices` 엔티티 |
| 추출 | `data/extracted/<id>.json` | `ExtractionRecord{notice_id, requirements, prompt_version}` | `notices.requirements` (구조화 자격 요건) |
| 판정 | `data/matches/<id>.json` | `MatchResult` | 해당자 산출 결과 |
| 초안 | `data/drafts/<id>.md` + `.json` | `Draft` | 승인 대기 큐 |
| 알림 | `data/alerts/YYYY-MM-DD.md`, `--json` | `Alert[]` | 알림 발송기 입력 |
| 프로필 | `data/profile.json` | `Profile` | `users/profiles` |

`<id>` = `"<source_key>:<게시글 고유번호>"` (파일명에서는 `:` → `_`). 예: `jnu_home_scholarship:70193`, `aisw_dept:945245`, `hakstd_catalog:국가근로장학`.

## Notice (수집 원문)

```json
{
  "id": "jnu_home_scholarship:70193",
  "source": "jnu_home_scholarship",
  "source_name": "전남대 홈페이지 공지사항 › 장학안내",
  "title": "[장학안내][두을장학재단] 제29기 두을장학생 모집 안내",
  "url": "https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx?boardID=5&bbsMode=view&key=70193&cate=8",
  "posted_at": "2026-09-01", "writer": "학생과", "category": "장학안내",
  "body_text": "", "body_is_image_only": true,
  "images": ["https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/byteToImage.aspx?key=…"],
  "attachments": [{"name": "1. 제29기 두을장학생 선발요강.pdf", "url": "…", "local_path": "data/attachments/…", "text_extracted": true}],
  "attachment_text": "[첨부: …]\n--- p.1 ---\n제29기 두을장학생 선발요강 …",
  "content_hash": "3f9a…", "fetched_at": "2026-09-13T04:39:00", "is_result_notice": false
}
```

## Requirements (자격 요건 — 추출 출력 스키마)

| 필드 | 타입 | 뜻 |
|---|---|---|
| `scholarship_name`, `provider`, `kind` | str, str, `교내\|교외\|국가\|사업단\|기타` | 장학명 · 주관 · 유형 |
| `grades_allowed` | int[] \| null | 지원 가능 학년. "3학년 이상" → `[3,4]` |
| `min_semesters_completed` | int \| null | 이수(재학) 학기 하한 |
| `min_gpa` | `{value, scale(4.5\|4.3\|4.0\|100), basis("전체"\|"직전학기")}` \| null | 성적 하한 |
| `min_credits_total`, `min_credits_last_semester` | int \| null | 누적 / 직전학기 이수학점 하한 |
| `major_include`, `major_exclude` | str[] \| null | 학과·학부·전공·계열 (원문 표기) |
| `enrollment_status` | str[] \| null | `["재학"]`, `["재학","휴학"]` |
| `income_bracket_max` | int \| null | 학자금 지원구간 상한 (기초·차상위만 → 0) |
| `nationality`, `residency` | str \| null | 국적 / 지역 조건 원문 |
| `other_conditions`, `exclusions` | str[] | 구조화 못 한 조건 / 제외 사유 (한 항목 = 한 조건) |
| `application_period` | `{start, end, raw}` \| null | ISO 8601 (`YYYY-MM-DD` 또는 `…THH:MM`) |
| `apply_method`, `apply_url` | str \| null | 신청 경로 |
| `required_documents` | str[] | 제출 서류 |
| `amount`, `selection_count`, `contact` | str \| null | 원문 한 줄 |
| `evidence` | `[{field, quote, grounded}]` | **필드별 원문 근거**. `grounded=false` 면 원문에서 못 찾은 인용 (값은 버려짐) |
| `unknown_fields` | str[] | 공지에 언급 없음 |
| `confidence` | 0~1 | 근거 검증·규칙 교차확인 결과. `< 0.6` 이면 자동 판정 안 함 |
| `needs_ocr` | bool | 본문이 이미지뿐 |
| `extractor` | `rules` \| `llm+rules` | |
| `notes` | str[] | 사람이 볼 메모 (불일치, 첨부 HWP 등) |

신뢰도 규칙 (`scripts/extract.py: merge`)
- 규칙만: `0.3 + 0.06 × 구조화필드수 (+0.05 기간)`, 상한 **0.6** → 항상 '확인 필요'
- LLM+규칙: `0.45 + 0.35 × 근거일치율 + 0.04 × 일치필드(≤4) − 0.12 × 불일치 − 0.08 × 근거없음`, 본문 200자 미만 −0.2, `needs_ocr` 이면 ≤0.2

## Profile (사용자 프로필 — 최소 수집)

```json
{
  "grade": 3, "semesters_completed": 5, "enrollment_status": "재학",
  "college": "AI융합대학", "department": "인공지능학부", "major": null, "field_group": "공학계열",
  "gpa": {"value": 3.82, "scale": 4.5}, "gpa_percent": null,
  "last_semester_gpa": null, "last_semester_gpa_percent": null,
  "earned_credits": 90, "last_semester_credits": 15,
  "income_bracket": null, "nationality": "대한민국",
  "high_school_region": null, "residence_region": null,
  "interests": ["인공지능"], "flags": {"disability": false},
  "draft_context": {"career_goal": "…", "activities": "…", "strengths": "…", "hardship": "", "plan": "…"}
}
```
이름·학번·연락처는 **넣지 않는다.** 모르는 값은 `null` → 해당 조건은 '모름'으로 처리되어 확인 필요로 간다 (비해당 아님).

## MatchResult (판정)

```json
{
  "notice_id": "aisw_dept:945245",
  "verdict": "needs_review",
  "reasons": [
    {"field": "min_gpa", "status": "pass", "message": "성적 조건 충족 (3.5/4.5 이상 / 전체 3.82)", "evidence": "나. … 평점이 3.5/4.5 이상인 자"},
    {"field": "income_bracket_max", "status": "unknown", "message": "학자금 지원구간 5구간 이하 조건 — 프로필에 구간 정보 없음 (한국장학재단에서 확인)", "evidence": "다. … 5구간 이하인 자"},
    {"field": "other_conditions", "status": "unknown", "message": "추가 조건 확인 필요: 인공지능학부 재학생 동창회비 납부자", "evidence": "…"}
  ],
  "unknown_fields": ["income_bracket_max", "other_conditions"],
  "deadline": "2026-01-20", "days_left": -236, "confidence": 0.59, "matched_at": "2026-09-13T04:47:10"
}
```

`verdict` ∈ `eligible`(해당) · `ineligible`(비해당) · `needs_review`(확인 필요) · `expired`(마감 지남) · `not_applicable`(결과·홍보 공지)
`reasons[].status` ∈ `pass` · `fail` · `unknown`. FE 는 이 목록을 그대로 "자격 충족 여부" 표시에 쓴다.

## Draft (승인 대기 객체)

```json
{
  "notice_id": "jnu_home_scholarship:70193", "scholarship_name": "제29기 두을장학생 모집 안내",
  "status": "pending_approval",            // pending_approval | approved | rejected
  "verdict": "needs_review", "markdown_path": "data/drafts/jnu_home_scholarship_70193.md",
  "checklist": ["대학교 재학증명서 1부", "대학교 성적증명서 1부"],
  "apply_method": "www.dooeul.or.kr ▶ 지원신청 ▶ 지원서 작성", "apply_url": "https://www.dooeul.or.kr",
  "deadline": "2026-09-30T18:00", "generated_by": "template",   // template | llm (prompt vN)
  "created_at": "…", "decided_at": null, "user_note": null
}
```
상태 전이: `pending_approval → approved | rejected` (사용자만). **approved 는 '제출함' 이 아니라 '초안을 확인함'** 이다. 제출은 사용자가 외부 시스템에서 한다.

## Alert (알림 페이로드)

```json
{
  "type": "scholarship_match",             // scholarship_match | scholarship_review | scholarship_deadline
  "notice_id": "…", "title": "…", "url": "…", "verdict": "eligible",
  "deadline": "2026-09-30T18:00", "days_left": 17,
  "reasons": ["성적 조건 충족 (…)", "추가 조건 확인 필요: …"],
  "draft_path": "data/drafts/….md", "target_screen": "scholarship_detail", "created_at": "…"
}
```
발송 정책: `eligible`·`needs_review` 만, 공지당 1회(내용 해시 기준), 마감 D-N 리마인더는 승인 전 초안이 있을 때 1회. `ineligible`/`expired`/`not_applicable` 은 발송하지 않는다.
