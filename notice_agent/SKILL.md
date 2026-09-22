---
name: notice-agent
description: 전남대 장학 공지를 자동 수집해 자격 요건을 구조화하고, 사용자 프로필(학년·평점·이수학점·소득구간·전공)과 규칙 매칭해 해당 여부·근거·마감을 알려주며, 해당(또는 확인 필요) 장학금의 신청서 초안을 만들어 승인 대기 큐에 넣는 Univ-Us F11(장학 공지 매칭·신청서 자동 작성) 스킬. 수집 대상은 전남대 홈페이지 장학안내, 인공지능학부·AI융합대학 공지, AICOSS 사업단, 국제협력과, 학사정보시스템 장학 카탈로그(SSO). 사용자가 "장학금", "장학 공지", "국가장학금", "근로장학", "내가 받을 수 있는 장학금", "장학 자격 되나", "신청서/자기소개서 초안", "장학 마감 언제", "학사시스템 장학 메뉴", "notice_ai-agent", "F11" 을 언급하거나, 공지 수집·자격 요건 추출·프로필 매칭·승인 대기 큐를 다루는 작업이면 — '스킬'이라는 말이 없어도 — 이 스킬을 쓴다. 공모전·대외활동(F12)·사업단 공지 통합(F13)도 같은 수집기로 확장하므로 그 논의에도 참고한다. 최종 제출은 절대 자동화하지 않는다.
---

# notice-agent — F11 장학 공지 매칭·신청서 자동 작성

## 1. 정의

기능명세서 3.4 **F11**: 수집된 장학 공지 + 사용자 프로필 → 자격 요건 구조화 추출 → 규칙 매칭 → 해당자 알림 + 신청서 초안.
**최종 제출은 반드시 사용자 확인·승인 후 사용자가 직접 한다(반자동).** 이 스킬은 어떤 사이트에도 제출하지 않고, 학사시스템의 신청 버튼도 누르지 않는다.

데이터 흐름은 DF-5 그대로다.

```
① 게시판 주기 수집 ─→ ② 신규 판별 ─→ ③ 자격요건 구조화 추출(+근거) ─→ ④ 프로필 규칙 매칭 ─→ ⑤ 해당자에게만 알림 ─→ ⑥ 신청서 초안 → 승인 대기
   scripts/collect.py      manifest.json     scripts/extract.py               scripts/match.py         scripts/notify.py       scripts/draft.py → approve.py
```

Univ-Us 저장소에서는 `notice_ai-agent` 브랜치(`src/notice/`)에 해당한다. 여기서는 **파일 기반으로 끝까지 한 번 도는 MVP** 를 만들었고, BE 가 붙으면 `data/` 의 JSON 이 그대로 테이블·API 가 된다 (`references/schemas.md`).

## 2. 언제 무엇을 실행하나

| 사용자가 말하면 | 실행 | 보여줄 것 |
|---|---|---|
| "새 장학 공지 있어?", "장학 공지 모아줘" | `run.cmd pipeline` (신규만) 또는 `run.cmd collect` | 신규/변경 목록, 알림 다이제스트 |
| "내가 받을 수 있는 장학금?", "이거 자격 돼?" | `run.cmd match` (프로필 바꿨으면 `pipeline --skip-collect`) | `eligible`/`needs_review` 건과 **근거 문장**, 마감 D-day, 원문 URL |
| "신청서 초안 써줘", "자기소개서 만들어줘" | `run.cmd draft --id <notice_id>` | `data/drafts/<id>.md` 내용, 채워야 할 `[여기에 …]` 위치 |
| "승인할게", "이건 안 할래" | `run.cmd approve approve\|reject <id> --note "..."` | 신청 경로·마감 재안내 (제출은 사용자가) |
| "학사시스템에서 내 학년·평점 가져와" | `run.cmd profile_from_hakstd` | 읽어온 항목 (이름·학번은 읽지 않음) |
| "몇 시간마다 자동으로" | `powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -IntervalHours 6` | 로그 위치 `data/logs/pipeline.log` |

답할 때는 항상 **판정 근거(reasons)** 와 **공지 URL** 을 같이 보여준다. 판정만 툭 던지면 사용자는 검증할 수 없다.
`needs_review` 는 "안 됨" 이 아니라 "사람이 봐야 함" 이다 — 그렇게 설명한다.

## 3. 빠른 시작

```powershell
cd <프로젝트 폴더>\notice_agent
.\setup.cmd                              # .venv + 패키지 (+ .env 복사)
.\run.cmd profile_from_hakstd            # 프로필 자동 채움 (SSO, eclass_agent 세션 재사용) — 또는 assets\profile.example.json 을 data\profile.json 으로 복사
notepad data\profile.json                # 소득구간·관심사·초안용 정보(draft_context) 채우기
notepad .env                             # LLM_MAIN_BASE_URL / API_KEY / MODEL (없으면 규칙 추출만 → 전부 '확인 필요')
.\run.cmd pipeline --pages 2             # 처음 한 번: 과거 글까지
.\run.cmd approve list                   # 승인 대기 초안
```

이후 주기 실행은 `.\run.cmd pipeline` (신규만 처리) 또는 작업 스케줄러(`register-task.ps1`).

## 4. 파이프라인 상세

### 4.1 수집 `scripts/collect.py`
- 소스는 `scripts/config.py: SOURCES` (key · kind · 게시판 파라미터 · 키워드 필터 · 로그인 필요 여부). 구조가 같은 게시판은 같은 `kind` 를 쓴다 — 셀렉터는 `references/site-structure.md`.
- 신규 판별: `data/manifest.json` 의 `id → content_hash`. 제목이 그대로면 본문을 다시 받지 않는다(요청 절약). 바뀌면 `UPD`.
- 첨부: PDF 는 텍스트를 뽑아 추출 입력에 붙인다. HWP/HWPX 는 못 읽는다 → `notes` 에 남기고 '확인 필요' 근거가 된다. 본문이 이미지뿐이면 `body_is_image_only`.
- SSO 소스(`hakstd_catalog`)는 `scripts/sso_session.py` 가 **eclass_agent 의 세션·무인 로그인을 빌려 쓴다**. 비밀번호는 이 스킬 코드가 다루지 않는다. 세션이 없으면 `--interactive` 로 창을 띄워 직접 로그인.
- 요청 간격 1.5초·동시성 1 (`REQUEST_INTERVAL` 줄이지 말 것).

### 4.2 추출 `scripts/extract.py` (+ `rules_extract.py`, `assets/prompts/extract_requirements.md`)
- 규칙 추출은 항상 돈다 (학년·학기·평점·학점·소득구간·국적·학적·신청기간·서류·연락처…). LLM 이 없어도 여기까지는 나온다.
- LLM 이 설정돼 있으면 스키마 지정 구조화 추출 후 **근거 검증**: LLM 이 인용한 문장이 원문에 없으면 그 값을 버린다. 근거가 항목과 무관하면(학기 문장으로 학년을 주장) 역시 버린다. 규칙과 일치하면 신뢰도 ↑, 불일치하면 ↓ 하고 `notes` 에 남긴다.
- 전공 조건은 규칙 단계에서 구조화하지 않는다(오탐 = 비해당 = 놓침). LLM+근거검증을 통과한 값만 `major_include` 로 간다.
- 프롬프트는 파일(`assets/prompts/*.md`, 버전 헤더). 바꿨으면 `run.cmd extract --all` 로 다시 돌리고, 정확도가 나아졌을 때만 반영한다. 응답 캐시는 `data/cache/`.

### 4.3 판정 `scripts/match.py` — 순수 함수
- 규칙 표와 경계값은 `references/matching-rules.md`. LLM 을 부르지 않는다.
- verdict: `eligible` · `ineligible` · `needs_review` · `expired` · `not_applicable`. 모든 판정에 `reasons[]` (pass/fail/unknown + 메시지 + 요건 근거 문장).
- 보수적 설계: 프로필에 없는 값은 unknown(→ 확인 필요), 추출 신뢰도 < 0.6 이면 결과와 무관하게 확인 필요, 저신뢰 추출의 '최근 지난 마감' 도 확인 필요. **놓치는 것이 잘못 알리는 것보다 나쁘다.**

### 4.4 초안 `scripts/draft.py` (+ `assets/prompts/draft_application.md`, `assets/templates/application_draft.md`)
- 대상: `eligible`, 그리고 신청 기간이 있는 `needs_review` (상시 카탈로그 항목은 `--id` 로만).
- 초안 = 공지 정보 표 + 자격 판정 근거 + 제출 서류 체크리스트 + 자기소개/지원동기/학업계획 문안 + 제출 전 확인 목록.
- LLM 에는 이름·학번을 넘기지 않는다(`{{이름}}` 자리표시자). 프로필에 없는 사실은 지어내지 않고 `[여기에 …]` 안내문으로 남긴다. LLM 이 없으면 골격만.
- 상태 `pending_approval` 로 큐에 들어간다. 초안을 만든 것이지 신청한 것이 아니다.

### 4.5 승인·알림 `scripts/approve.py`, `scripts/notify.py`
- `approve approve <id>` 는 **기록**이다. 승인 후 신청 경로(학사시스템 메뉴 / 재단 사이트 / 학과 사무실)와 마감을 다시 보여준다. 제출은 사용자가 그 경로에서 직접 한다.
- 알림은 `eligible`·`needs_review` 만, 공지당 1회, 마감 D-N 리마인더 1회. `ineligible`/`expired`/`not_applicable` 은 알리지 않는다 (전량 알림 금지).
- BE 알림 발송기에 넘길 때는 `run.cmd notify --json` (Alert 페이로드).

## 5. 입력·출력 계약 (요약)

- 프로필 `data/profile.json` ← `Profile` (학년·이수학기·학적·소속·계열·평점(척도)·백분위·이수학점·소득구간·국적·지역·관심사·초안용 문맥). 이름·학번 없음.
- 공지 → `Notice`, 자격요건 → `Requirements`(+`evidence[]`, `confidence`), 판정 → `MatchResult`, 초안 → `Draft`, 알림 → `Alert`.
- 필드 정의·예시 JSON 은 `references/schemas.md`. 바꾸면 `scripts/schemas.py` 와 함께 고치고 팀에 공유 (역할별 분해서 5장 계약).

## 6. 지키는 선

| 원칙 | 구현 |
|---|---|
| 근거 제시 | 모든 추출 값에 원문 인용, 모든 판정에 reasons + 근거 문장 |
| 저신뢰 분리 | confidence < 0.6 · 이미지 본문 · HWP 전용 → `needs_review`, 자동 판정·자동 제외 금지 |
| 승인 흐름 | 초안 → `pending_approval` → 사용자 승인 → **사용자가 직접 제출**. 코드 어디에도 제출 요청이 없다 |
| 개인정보 최소 | 프로필에 식별 정보 없음, LLM 프롬프트에 이름·학번 없음, `data/`·`state/` gitignore, 학사시스템은 조회만 |
| 서버 부담 | 요청 간격 1.5초, 목록 1~2페이지, 첨부 20MB 제한 |
| 모델 비종속 | `LLM_MAIN_*` 슬롯만 사용(OpenAI 호환). 모델명이 코드에 없다 |
| 인증 | SSO 비밀번호는 eclass_agent(DPAPI)만 다룬다. 이 스킬은 세션 파일만 빌린다 |

## 7. 실패 모드와 대처

| 증상 | 원인 / 대처 |
|---|---|
| `프로필 파일이 없습니다` | `profile_from_hakstd` 또는 예시 복사. 종료 코드 2 |
| `학사정보시스템 로그인 실패` | SSO 세션 만료 + 자격증명 없음. eclass_agent `login.cmd`(수동) / `setup-creds.cmd`(무인) 또는 `collect --source hakstd_catalog --interactive` |
| 2차 인증 패널이 뜸 | 신뢰기기 쿠키(~1년) 만료. eclass_agent `login.cmd` 한 번 수동 실행 |
| `CERTIFICATE_VERIFY_FAILED` | 중간 인증서 없는 서버(international). `truststore` 설치 여부 확인. `verify=False` 금지 |
| 목록 0건 / 파싱 오류 | 사이트 개편. `references/site-structure.md` 의 셀렉터와 대조 후 `scripts/sources/<kind>.py` 수정. K2Web 은 RSS 대안 |
| 전부 `needs_review` | LLM 미설정(규칙 추출 상한 0.6) — 의도된 동작. `.env` 채우고 `extract --all` |
| LLM 403/insufficient credit | 키 문제. 자동으로 규칙 결과로 후퇴하고 `notes` 에 기록 |
| 이미지 본문 공지가 많음 | 정상. OCR 은 `pic_ai-agent`/`DOC_PARSER` 슬롯 몫. 붙이면 `attachments.py`/`collect.py` 에서 `body_is_image_only` 건을 넘긴다 |
| 초안 큐가 너무 많음 | `--only-eligible`, 또는 `config.DRAFT_FOR_NEEDS_REVIEW=False` |

## 8. Univ-Us 연계 / 확장

- `scripts/llm.py` 는 `core_ai-agent` 가 나오면 그 호출로 교체한다 (구조화 출력·캐시·토큰 로그 인터페이스 동일).
- **F12 맞춤 기회 알림**: `SOURCES` 에 `cate=15`(공모전)·`16`(모집공고)·AICOSS `경진대회` 를 추가하고 `keyword_filter` 를 관심사 매칭으로 바꾼다. **F13 사업단 통합**: `k2web`/`aicoss` 수집기에 사업단 게시판을 더 등록하면 된다 — 수집기 코드는 재사용, 설정만 는다.
- BE 호출 지점: `collect.collect()` → `extract.extract_notice()` → `match.decide()` → `draft.build_draft()` 는 모두 파일 없이도 객체로 호출 가능하다. 승인 큐(`Draft`)와 알림(`Alert`)은 역할별 분해서의 `승인 대기 객체`·`알림 페이로드` 계약이다.
- 평가: 오매칭률(인수 기준 10% 이하)은 `eligible/ineligible` 중 사람이 뒤집은 비율. `data/matches/` 옆에 검수 기록을 남기고 `eval_ai-agent` 가 집계.

## 9. 프로젝트 구조

```
notice_agent/
├── SKILL.md                      이 문서
├── README.md                     사람용 요약 (설치·사용)
├── setup.cmd / run.cmd           .venv 생성 · 모듈 실행 (run.cmd <모듈> [옵션])
├── run-pipeline.cmd / register-task.ps1   작업 스케줄러 (창 숨김, data/logs/pipeline.log)
├── requirements.txt · .env.example · .gitignore
├── scripts/
│   ├── config.py                 소스 목록·경로·정책·LLM 슬롯
│   ├── schemas.py                Notice/Requirements/Profile/MatchResult/Draft/Alert
│   ├── sources/                  수집기: jnu_aspx · k2web · aicoss · hakstd(SSO)
│   ├── http.py · sso_session.py · attachments.py · textutil.py
│   ├── collect.py → extract.py(rules_extract.py, llm.py) → match.py → draft.py → notify.py
│   ├── approve.py                승인 대기 큐 CLI
│   ├── profile_from_hakstd.py    프로필 자동 채움
│   ├── pipeline.py               전체 실행
│   └── tests/                    test_match · test_rules_extract · test_extract_merge  (pytest)
├── assets/
│   ├── profile.example.json
│   ├── prompts/extract_requirements.md · draft_application.md   (버전 헤더)
│   └── templates/application_draft.md
├── references/
│   ├── site-structure.md         게시판·학사시스템 URL/셀렉터/SSO 흐름 (실측)
│   ├── schemas.md                입출력 JSON 계약
│   └── matching-rules.md         판정 규칙 표·경계값
├── data/   (gitignore)           notices/ attachments/ extracted/ matches/ drafts/ alerts/ cache/ logs/ profile.json manifest.json
└── state/  (gitignore)           SSO 세션
```

테스트: `.venv\Scripts\python -m pytest scripts\tests -q` (34개, 네트워크 불필요).
