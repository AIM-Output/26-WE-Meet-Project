# notice_agent — 장학 공지 매칭·신청서 초안 (Univ-Us F11)

전남대 장학 공지를 모아서 **내 프로필에 맞는 것만** 골라 알려주고, 신청서 초안을 만들어 두는 도구.
에이전트용 지침과 상세 설계는 [SKILL.md](SKILL.md), 사이트 구조는 [references/site-structure.md](references/site-structure.md).

**제출은 하지 않는다.** 초안을 확인·승인한 뒤 본인이 학사정보시스템/재단 사이트에서 직접 제출한다.

## 설치 (최초 1회)

```powershell
cd <프로젝트 폴더>\notice_agent
.\setup.cmd
```

- Python 3.12 (`py -3.12`) 로 `.venv` 를 만들고 패키지를 설치한다. `.env` 가 없으면 `.env.example` 을 복사한다.
- 학사정보시스템(SSO) 소스와 프로필 자동 채움은 Playwright 를 쓰는데, 브라우저는 **eclass_agent 의 `.venv\pw-browsers`** 를 그대로 쓴다 (따로 내려받지 않음). eclass_agent 가 없으면 `.venv\Scripts\playwright install chromium` 을 `PLAYWRIGHT_BROWSERS_PATH=<이 폴더>\.venv\pw-browsers` 로 실행할 것 (사용자 프로필 폴더에 두면 이 PC 에서는 안 보인다).

## 사용

```powershell
.\run.cmd profile_from_hakstd        # 학년·학적·전공·평점·이수학점을 학사시스템에서 읽어 data\profile.json 에 저장
notepad data\profile.json            # 소득구간(income_bracket)·관심사·초안용 정보(draft_context) 직접 채우기
notepad .env                         # LLM_MAIN_BASE_URL / LLM_MAIN_API_KEY / LLM_MAIN_MODEL

.\run.cmd pipeline --pages 2         # 처음: 수집 → 추출 → 매칭 → 초안 → 알림
.\run.cmd pipeline                   # 이후: 새 공지만
.\run.cmd approve list               # 승인 대기 초안 (마감 임박순)
.\run.cmd approve show  <notice_id>  # 초안 보기  (open 은 편집기로 열기)
.\run.cmd approve approve <notice_id> --note "제출 예정"
```

단계별 실행: `run.cmd collect --dry-run`, `run.cmd extract --all`, `run.cmd match`, `run.cmd draft --id <id>`, `run.cmd notify --deadline 3 [--json]`.
SSO 세션이 없을 때: `run.cmd collect --source hakstd_catalog --interactive` (창이 뜨면 직접 로그인).

LLM 을 설정하지 않으면 규칙 추출만 돌고 **모든 건이 '확인 필요'** 로 분류된다 (자동 판정 문턱 0.6 미만). 그래도 수집·마감·근거·초안 골격은 나온다.

## 주기 실행 (Windows 작업 스케줄러)

```powershell
powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -IntervalHours 6   # 로그인 중에만, 창 숨김
Start-ScheduledTask -TaskName NoticeAgent-Scholarship                          # 지금 한 번
powershell -ExecutionPolicy Bypass -File .\register-task.ps1 -Remove
```

로그: `data\logs\pipeline.log`. 새 알림은 `data\alerts\YYYY-MM-DD.md` 에 쌓인다.

## 결과물 (`data/`, git 에 올라가지 않음)

| 경로 | 내용 |
|---|---|
| `notices/<source>/<id>.json` | 공지 원문 (본문 텍스트·첨부 텍스트·이미지 여부) |
| `attachments/<id>/…` | 공고문 파일 |
| `extracted/<id>.json` | 자격 요건 JSON + 원문 근거 + 신뢰도 |
| `matches/<id>.json` | 판정 (`eligible` / `ineligible` / `needs_review` / `expired` / `not_applicable`) + 근거 |
| `drafts/<id>.md` `.json` | 신청서 초안 + 승인 상태 |
| `alerts/` | 알림 다이제스트, `sent.json`(중복 억제) |
| `profile.json` | 내 프로필 (이름·학번 없음) |

## 수집 소스

전남대 홈페이지 장학안내 · 인공지능학부 공지(장학 말머리) · AI융합대학 공지 · AICOSS 사업단 · 국제협력과 · 학사정보시스템 전체 장학 안내(SSO).
학과가 다르면 `scripts/config.py` 의 `SOURCES` 에서 `site`/`board` 만 바꾼다. 셀렉터·URL 규칙은 `references/site-structure.md`.

## 테스트

```powershell
.venv\Scripts\python -m pytest scripts\tests -q
```

## 지키는 선

요청 간격 1.5초 · 학사시스템은 조회만(신청 버튼 안 누름) · 비밀번호는 eclass_agent(DPAPI)만 · `data/` `state/` 공유 금지 · 제출은 사람이.
