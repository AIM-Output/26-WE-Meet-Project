# C4_Briefing_agent — 브리핑 (유니버스 공통 기능 C4)

**모든 기능의 '오늘 할 것 · 곧 닥칠 것 · 새 알림'을 모아 하루 한 번 브리핑 스냅샷을 만든다.**
요구사항은 [요구사항정의서.md](../요구사항정의서.md) **F10 아침 브리핑** 절 — 계획서의 기능 번호는 F10 이지만, 새 계산 없이 다른 기능의 결과와
알림을 모으는 일이라 **공통 기능 C4** 로 구현했다(2026-10-25 사용자 결정). 화면·라우트는 [Frontend-Route.md](../Frontend-Route.md) 15절.

> 정보는 이미 앱 안에 다 있다. 아침에 여섯 화면을 돌아다니며 확인하는 사람은 없다 — 브리핑 하나만 보고 하루를 시작하게 한다.

- **설치할 것이 없다** — 표준 라이브러리 + fastapi(라우터에만).
- **숫자를 다시 계산하지 않는다**(F10-R17). 각 기능이 브리핑용으로 내놓은 함수의 결과를 고르고·정렬하고·한 줄 글로 옮길 뿐이다.
- **스냅샷이다.** 만든 뒤 데이터가 바뀌어도 그날 브리핑은 그대로 둔다. 다시 만들기만 덮어쓴다.
- **LLM 은 맨 위 한 줄만**(F10 D1, 선택). 없거나 실패하면 그 줄만 빠지고 브리핑은 그대로 나온다.
- 이 폴더가 쓰는 것은 `data/briefing.db` 하나(스냅샷 · 설정 · 수집 기다림 기록). 알림 센터 한 줄은 백엔드가 넘겨준 함수로 F1 알림 표에 넣는다.

```
C4_Briefing_agent/
├── briefing/                파이썬 패키지 (표준 라이브러리와 이름이 겹치지 않는다 — 백엔드가 sys.path 에 넣는다)
│   ├── config.py            경로 · 기본값(08:00 · 30일) · 놓침 60분 · 수집 대기 5분 · 섹션 정의 · 한 줄 요약 규칙(LLM_MAIN_*)
│   ├── compose.py           **재료 → 섹션 (순수 함수)** — 무엇을 고르고 어떤 글로 옮기는지 전부 여기
│   ├── headline.py          맨 위 한 줄 (LLM, 3초) + 검증(한 줄 · 60자 · 격려 금지 · 지어낸 숫자 금지)
│   ├── service.py           재료 모으기 · 정시/놓침 판정 · 수집 기다리기 · 저장 · 알림 1건 · 보관 정리 · 상태
│   ├── settings.py          켜기 · 시각 · 보관 기간 (기본값과 다른 값만 저장)
│   ├── store.py             SQLite (briefings · meta)
│   ├── api.py               FastAPI 라우터 (univ_us_local 이 include — 재료는 백엔드가 함수로 넘겨준다)
│   └── __main__.py          명령줄
├── tests/                   pytest 42개 (섹션 규칙 · D-3 · 자정 마감 · 새 알림 거르기 · 정시/놓침 · 수집 대기 · 다시 만들기 · 꺼짐 · 보관 · 한 줄 검증 · 라우터)
└── data/                    (gitignore) — 내 브리핑
    └── briefing.db
```

## 브리핑에 싣는 것 (섹션 — 화면 순서)

| 섹션 | 재료 (기능이 내놓은 함수) | 고르는 규칙 | 비었을 때 |
|---|---|---|---|
| ⚠ **주의** | F3 `today().totals.risky` · F7 `brief().overdue` | 출결 위험·초과 과목(F3-R35 '브리핑 상단') · 놓친 마감 N건 | 숨김 |
| 📚 **오늘 수업** | F3 `today().classes` | 시간 순 · 강의실 · 휴강은 '휴강'으로 남긴다(그 시간이 비었다는 뜻) | 숨김 |
| 📅 **오늘 일정** | C1 합친 캘린더 · F8 `today()` · F5 `today_block()` | 내 일정·할 일(끝낸 것 빼고) · 그날의 학사 일정 · 오늘 시험 · F8 학습 블록 · F5 '오늘 공부' — 종일 먼저, 그다음 시각 순 | 숨김 |
| ⏰ **마감 임박** | C1 캘린더의 `deadline`(F6) · F1 `upcoming(3)` · F5 `nextExam` · F11 `brief(3)` · F12 `brief(3)` | **D-3 이내**(달력 날짜 차이, 00:00 마감은 전날 24:00) — 과제·퀴즈·동영상(제출·체크한 것 빼고) · 학사(알림이 켜진 것, 긴 기간은 **끝나는 날**) · 시험 · 장학(F11-R74) · 담아 둔 대외활동(F12-R34). 가까운 순 | `사흘 안에 마감이 없습니다` |
| 🔥 **먼저 할 것** | F7 `brief(3)` | F7 순서 그대로 · 이유 한 줄 · 합계 시간 | 숨김 |
| 🔔 **새 알림** | 알림 센터(F1 notifications) 안 읽은 것 | **지난 브리핑 이후**(그래도 최대 하루) 배달된 것. 위 섹션과 겹치는 학사 D-n 알림(`rem:`)·과제별 마감 알림·브리핑 도착 알림은 뺀다 | 숨김 |

- 전부 비었으면 `오늘은 일정이 없습니다` 한 줄(F10-R16). 섹션당 화면에는 5줄, 넘으면 `+N건 더`(스냅샷에는 30줄까지).
- 각 줄은 그 항목의 **상세가 열린 URL** 을 갖는다(`/?event=…` · `/academic?event=…` · `/exams?exam=…` · `/scholarships?item=…` · `/attendance?course=…`).
- 못 읽은 재료는 그 섹션만 빠지고 `gaps` 에 기능 이름이 남는다 — 화면이 '○○ 을(를) 읽지 못해 빠졌습니다'로 알린다.
- 맨 위 한 줄(LLM)에는 **숫자와 제목만** 보낸다(`compose.facts`) — 강의실·메모·알림 본문·이름·학번은 보내지 않는다.

## 언제 만드나 (F10 4절 · 9절)

따로 도는 스케줄러가 없다 — F1 알림·F11 자동 수집과 같은 방식이다. 대시보드가 1분마다 부르는 `/api/status` 와 화면이 여는
`GET /api/briefing/today` 가 `service.ensure_today` 를 부르고, 그때 '만들 때가 됐는데 오늘 것이 없으면' 만든다.

| 상황 | 동작 | state |
|---|---|---|
| 예정 시각(기본 08:00) 전 | 만들지 않는다 — 카드 없음 | `before` |
| 예정 시각 ~ 60분 안 | 만든다 `source=scheduled` | `ready` |
| 60분 넘게 지나서 처음 켬(PC 가 꺼져 있었다) | 그 시점 기준으로 만든다 `source=catchup` = **놓친 브리핑** | `ready` |
| 그 순간 수집(e클래스·학사·장학·대외활동)이 돌고 있음 | 끝날 때까지 기다린다 — **최대 5분**, 넘으면 그대로 만든다 | `pending` (화면은 스켈레톤) |
| 꺼짐 | 만들지 않는다 — 카드 없음(손으로 만든 것은 `/briefing` 에 보인다) | `off` |
| 여러 날 만에 켬 | **오늘 것만** 만든다. 지난 날짜는 만들지 않는다(F10-R03) | |
| 다시 만들기 | 지금 기준으로 오늘 것을 덮어쓴다 `source=manual`. 처음에 놓친 브리핑이었다는 것(`firstSource`)은 남는다 | |

- 처음 만들 때 알림 센터에 1건(F10-R05) — `오늘 브리핑이 도착했습니다` / `놓친 브리핑 — 10:24 기준으로 만들었습니다`. 다시 만들기는 알림을 남기지 않는다.
- 보관 기간(기본 30일 · 7/14/30/60)이 지난 것은 만들 때·설정을 바꿀 때 오래된 것부터 지운다.
- `/api/status` 에서 브리핑을 **맨 끝**에 부른다 — 다른 기능이 그 순간 배달할 알림을 먼저 넣고 나서 '새 알림'을 모으게.

## 명령줄

```
python desktop/cli.py briefing today                     오늘 브리핑 (만들 때가 됐는데 없으면 지금 만든다 — 앱과 같은 규칙)
python desktop/cli.py briefing make                      다시 만들기
python desktop/cli.py briefing list                      지난 브리핑 목록
python desktop/cli.py briefing show 2026-10-25           그날 스냅샷
python desktop/cli.py briefing json [2026-10-25]         API 응답 그대로
python desktop/cli.py briefing settings --time 07:30 --keep 14     설정 (--on · --off · --reset)
```

`today`·`make` 는 재료를 **대시보드 백엔드의 기능 어댑터**(`univ_us_local/backend/app`)에서 빌린다 — 앱과 같은 함수라 숫자가 화면과 같다.
저장소 루트에서 개발 venv 로 실행한다(`desktop/cli.py` 가 개발 데이터 `desktop/.dev-data` 로 `python -m briefing` 을 돌린다, `--app` 이면 앱 데이터).

## API (대시보드 백엔드가 붙인다 — Frontend-Route 15-6)

| 메서드 · 경로 | 내용 |
|---|---|
| `GET /api/briefing/today` | `{state: ready·before·pending·off, date, enabled, scheduledFor, scheduledAt, waitingFor, created, briefing}` — 만들 때가 됐는데 없으면 지금 만든다 |
| `POST /api/briefing/regenerate` | 다시 만들기 → 브리핑 |
| `GET /api/briefings?limit=30` | 지난 목록(최신 순, 본문 없이) `{items, keepDays, today}` |
| `GET /api/briefings/{date}` | 그날 스냅샷. 없으면 404(지난 날짜는 새로 만들지 않는다) |
| `GET /api/settings/briefing` · `PATCH` | `{enabled, time, keepDays}` (+ `defaults · changed · keepDaysChoices · llm`). `null` 은 그 칸을 기본값으로, `{reset: true}` 는 전부 |
| `/api/status` 의 `briefing` | `{available, enabled, time, state, waitingFor, updatedAt, llm, today: {date, generatedAt, source, missed, summary, counts, headline}}` — 1분마다 |

브리핑 한 건: `{id: "br:2026-10-26", date, generatedAt, scheduledFor, source, firstSource, firstGeneratedAt, missed, headline, summary,
sections: [{key, label, icon, link, count, items: [{text, sub, href, tone, tag}], more, empty, footer}], counts, gaps, empty, emptyText, model, promptVersion}`

- Frontend-Route 15-6 초안의 설정 경로 `/api/settings/notifications` 는 쓰지 않는다 — 알림 기본 시각은 F1(`/api/academic/settings`),
  과제 마감 알림은 F6(`/api/assignments/settings`)가 이미 자기 자리에 저장한다. 화면(`/settings/notifications`)은 셋을 한 곳에 모은다.
- 재료 함수는 백엔드가 `service.Sources` 로 넘긴다(`univ_us_local/backend/app/briefing.py`). 새 기능이 브리핑에 실을 것이 생기면
  그 기능이 `brief()`·`today()` 같은 함수를 내놓고, `Sources` 에 칸 하나 + `compose.py` 에 고르는 규칙 하나를 더한다.

## 테스트

```
cd C4_Briefing_agent
python -m pytest tests -q          # 개발 venv(desktop/sidecar/.venv)
```

임시 `data/` 를 쓰고 LLM 을 끈다(`C4_LLM=off`). 재료는 가짜 함수(conftest `FakeSources`) — 다른 기능의 DB 를 건드리지 않는다.

## 미결 (요구사항정의서 F10 11절)

- Q1 기본 시각 08:00 — 시범 사용 후.
- Q2 '권장 학습 계획' 별도 섹션 — 지금은 F8 블록·F5 오늘 공부가 '오늘 일정'에 들어간다.
- Q5 저녁 마무리 브리핑 — 2차.
- C-Q5 Windows 시스템 알림(토스트) — 1차는 앱 내 알림만.
