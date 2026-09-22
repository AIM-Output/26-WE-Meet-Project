# univ_us_local — 유니버스(Univ-Us) 개인 로컬 서버 웹

내 PC에서 도는 대시보드. `eclass_agent` 가 내려받은 과제·마감을 캘린더에 띄우고, 내 일정을 등록·수정한다.
자격증명·강의자료·세션은 전부 PC 안에 남는다 (설계 배경: `../WE-Meet_서버_플랫폼_검토.md` 8·10절 "안 B").

```
univ_us_local/
├── backend/            FastAPI (127.0.0.1:8000) — /api + 프론트 정적 서빙
│   ├── app/main.py     라우트 (events / courses / status / sync)
│   ├── app/eclass_data.py   eclass_agent/data/*.json → 캘린더 이벤트, run-sync.cmd 실행 (잠금 파일·프로세스로 중복 확인)
│   ├── app/store.py    사용자 일정 SQLite (data/univus.db)
│   ├── app/config.py   경로·포트·허용 Origin·색상표
│   ├── requirements.txt · run.cmd
│   └── .venv/          (run.cmd 가 처음 실행 때 만든다)
├── frontend/           Next.js 16 + Tailwind 4 + FullCalendar 7
│   └── src/components/ Dashboard(레이아웃) · CalendarView · ActionPanel · TodoList · FeatureSection · EventModal · EventDetail
├── data/               univus.db (gitignore)
└── README.md
```

## 실행

### 사용 (Node 불필요 — 백엔드 하나로 끝)

```powershell
cd univ_us_local\backend
.\run.cmd
```

→ http://localhost:8000 . `frontend/out`(빌드된 정적 프론트)이 있으면 그대로 서빙한다.
프론트를 고쳤으면 `frontend` 에서 `npm run build` 로 `out/` 을 다시 만든 뒤 백엔드를 재시작한다.

### 개발 (핫리로드)

```powershell
# 터미널 1
cd univ_us_local\backend
.\run.cmd --reload

# 터미널 2
cd univ_us_local\frontend
npm install      # 최초 1회
npm run dev      # http://localhost:3000  (/api 는 next.config.ts rewrites 로 8000 에 전달)
```

Claude Code 에서는 `.claude/launch.json` 의 `univus-backend` / `univus-frontend` 로 같은 것을 띄운다.

## 화면 (Notion "Routine Planner" 템플릿 구조를 참고)

참고 템플릿 공개 페이지를 1920px 에서 실측한 값을 그대로 따른다 (`globals.css` 머리 주석): 좌우 여백 96px, 커버 280px(#f4ebbf), 제목 36px, **3컬럼 341 : 1023 : 273 (= 20.8% : 62.5% : 16.7%), 컬럼 간격 46px**, 달력 칸 **146×140px**(`aspectRatio` 1.21, 주말 칸 회색, 날짜 오른쪽 위, 1일은 "9월 1일"), 콜아웃은 흰 배경 + 테두리 #e6e5e3 + 작은 알약 버튼, To Do 카드는 테두리 #ecebeb + Notion 태그 색. 페이지는 세로로 스크롤된다. 1280px 미만이면 캘린더가 위로 가고 두 패널이 아래에 나란히, 768px 미만이면 한 줄로 쌓인다.

| 영역 | 내용 |
|---|---|
| 왼쪽 (ActionPanel) | 회색 콜아웃 "일정, 할 일 등록"(일정 추가 / 할 일 추가), "빠른 실행"(e클래스 동기화 + 준비 중 기능 버튼), "월별 완료율" 막대 차트(과제 제출 + 할 일 완료, 이번 달과 지난 3개월) |
| 가운데 (Calendar) | `‣ C A L E N D A R` 제목 + 필터 탭(전체 / e클래스 / 내 일정 / 할 일) + FullCalendar 월·주·목록. e클래스 마감은 과목 색, 내 일정은 분류 색, **할 일은 주황**(☐/☑), 제출 완료·완료는 흐리게+취소선, 미제출 지난 마감은 빨강. 날짜 클릭/드래그 → 새 일정(할 일 탭이면 새 할 일), 드래그로 이동·늘리기 |
| 오른쪽 (TodoList) | `‣ T O   D O   L I S T` + 탭(할 일 / 완료) + 갤러리형 카드. 내 할 일(체크박스로 완료)과 e클래스 과제(미제출 = 할 일, 제출 완료 = 완료, e클래스에서만 바뀜)를 한 목록으로. D-day 칩 |
| 아래 (FeatureSection) | 참고 템플릿의 HABIT TRACKER 자리 — 아침 브리핑(F10) 숫자 + 나중에 붙일 기능 타일(F7·F9·F4·F11·F2·F8·F5·F16, 준비 중) |
| 상단바 | 고정. 마지막 동기화 시각, `+ 일정 추가` |

"할 일"은 일정과 같은 테이블(`user_events.is_todo`, `done`)에 있다 — 참고 템플릿의 Schedule DB(📆 일정 / 📋 할일 목록)와 같은 구조.

## API (`/api/docs` 에 Swagger)

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/events?start&end` | e클래스 마감 + 내 일정 (FullCalendar 형식, `extendedProps.kind` = `deadline` / `user`) |
| POST | `/api/events` | 내 일정/할 일 추가 `{title, start, end, all_day, category, memo, is_todo, done}` |
| PATCH / DELETE | `/api/events/{id}` | 내 일정만 (`dl:` 로 시작하는 마감 id 는 거부) |
| GET | `/api/courses` | 과목 + 색 |
| GET | `/api/status` | `updated_at`, 동기화 진행 상태 `sync`, 건수, 분류표, sync.log 끝부분 |
| POST | `/api/sync` | 수집 시작. 이미 돌고 있으면 띄우지 않고 `already_running: true` 를 붙여 상태만 반환 |

`sync` = `{running, started_at, finished_at, exit_code, source, pid}`. `source` 는 `button`(이 서버가 띄움) 또는
`external`(작업 스케줄러 예약 실행·수동 실행 — `eclass_agent/state/sync.lock` 의 pid 가 살아 있으면 실행 중으로 본다).
안 돌고 있을 때는 가장 최근 실행의 결과이며, 예약 실행의 결과는 `state/sync.last.json` 에서 읽는다.
버튼을 누르면 잠금 파일에 더해 `sync.py` 프로세스가 실제로 있는지도 확인한다 (Windows: PowerShell CIM, 1초쯤).
프론트는 동기화 중엔 3초, 평소엔 1분 간격으로 `/api/status` 를 봐서 예약 실행도 "예약 동기화 진행 중…" 으로 보여 준다.

날짜는 tz 없는 로컬 문자열. 종일 일정의 `end` 는 FullCalendar 규칙대로 **exclusive** (9/24~9/25 → `end=2026-09-26`).

## 지키는 선

- `127.0.0.1` 에만 바인딩. Host 가 localhost/127.0.0.1 이 아니면 400, 변경 요청의 Origin 이 허용 목록 밖이면 403 (DNS 리바인딩·CSRF 대비). LAN 에 열려면 인증·HTTPS 를 먼저.
- e클래스 자료는 읽기만 한다. 수집·로그인·자격증명은 `eclass_agent` 몫이고 이 앱은 그 결과 파일만 본다.
- `data/`·`.venv/`·`node_modules/` 는 커밋하지 않는다. `frontend/out/`(빌드 결과)은 **커밋한다** — 팀원이 Node 없이 실행하기 위해. 프론트를 고쳤으면 `npm run build` 후 `out/` 도 함께 커밋.

## 다음 단계 (아래 Features 칸 순서)

F7 우선순위 → F9 자연어 일정 → F10 브리핑(스케줄러 내장) → F4 강의자료 → F11 장학 → 알림 채널(Google Calendar·텔레그램). 폰 접근은 Tailscale, 정시 배달·F16·F17 은 얇은 서버 — 검토 문서 참고.

## 알아둘 것

- FullCalendar 7 은 클래스명이 해시라 CSS 로 직접 스타일하지 않고, 테마 변수(`--fc-breezy-*`)와 `eventContent`/`className` 옵션으로 만진다.
- 콘솔의 `inert` 경고는 FullCalendar 내부가 React 19 에 빈 문자열을 넘겨서 나는 것으로, 이 코드 문제는 아니다.
