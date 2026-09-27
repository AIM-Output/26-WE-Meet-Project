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
├── frontend/           Next.js 16 + Tailwind 4 + FullCalendar 7 + motion + lucide-react
│   ├── DESIGN.md       디자인 시스템 v2 (토큰·글자·치수·공용 부품)
│   ├── src/app/        라우트 17개 (Frontend-Route 2-1) — 각 page.tsx 는 Suspense 로 감싼 클라이언트 화면
│   ├── src/components/ app(헤더·공용 데이터) · ui(공용 부품) · dashboard · events(상세·새 일정 모달) · pages(기능 화면)
│   └── src/lib/        api · useQueryState(모달=push/탭=replace) · priority(F7) · demo/(예시 데이터)
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

## 화면 (Frontend-Route · Frontend-Screens 기준, 2026-09-27 전면 재작성)

디자인은 `frontend/DESIGN.md` (Flat Design + Micro-interactions, 주색 틸 · 할 일 주황, Pretendard). 상단 메뉴(GNB)는 없고 **대시보드가 허브**다.

| 라우트 | 화면 | 데이터 |
|---|---|---|
| `/` | 브리핑 카드 → 3단(등록·빠른 실행·확인 필요·대화 카드 / 캘린더 월·주·목록·학기 / 먼저 할 것·할 일) → 기능 타일 10개. `?event=` 상세 · `?new=event` 새 일정 · `?place=preview` 공강 배치 | 실제(일정·마감·동기화) + 학사일정 예시 |
| `/assignments` | 진행 중/완료/지난 마감 · 급한 순 그룹(F7) · 소요시간 편집 · 내가 체크함 | **실제** (소요시간·체크는 브라우저 임시 저장) |
| `/academic` | 전체/내 해당/확인 필요/숨김 · 월 묶음 · 확인 필요 카드 | 예시 |
| `/onboarding` · `/settings/*` 5개 | 첫 설정 3단계 · 프로필·수집 원천·졸업요건 기준·가용 시간·알림 | 수집 원천의 e클래스 행은 실제, 나머지 예시(브라우저 저장) |
| `/graduation` `/attendance` `/courses` `/exams` `/briefing` `/chat` `/opportunities` `/team` | F2~F16 기능 화면 뼈대 | 예시 |

- **예시 데이터**는 `src/lib/demo/` 에 모여 있고 화면마다 "예시 데이터" 띠로 표시한다. API 가 생기면 `lib/api.ts` 에 같은 모양의 함수를 만들고 바꿔 끼운다.
- 모달·패널은 쿼리 파라미터 + `push`(뒤로가기로 닫힘), 탭·필터는 `replace` — `lib/useQueryState.ts` 한곳에서 처리.
- 반응형: ≥1280 3단 · 768~1279 캘린더 위 2단 · <768 1단(캘린더 → 실행 → 할 일), 모달은 바텀 시트, 일정 추가는 오른쪽 아래 떠 있는 버튼.
- `next.config.ts` 의 `trailingSlash: true` 로 `out/academic/index.html` 처럼 폴더마다 만들어져 주소창에 `/academic` 을 직접 쳐도 열린다.

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

F7 우선순위 → F9 자연어 일정 → F10 브리핑(스케줄러 내장) → F4 강의자료 → F11 장학 → 알림 채널(앱 내 알림·텔레그램). 폰 접근은 Tailscale, 정시 배달·F16·F17 은 얇은 서버 — 검토 문서 참고.

## 알아둘 것

- 백엔드는 HTML 에 `Cache-Control: no-cache`, `_next/static` 에 영구 캐시 헤더를 붙인다(빌드 뒤 옛 화면이 남지 않게). 이 헤더가 생기기 전에 열어 본 브라우저는 **한 번만 Ctrl+F5** 로 새로고침하면 된다.
- FullCalendar 7 은 클래스명이 해시라 CSS 로 직접 스타일하지 않고, 테마 변수(`--fc-breezy-*`)와 `eventContent`/`className` 옵션으로 만진다.
- 콘솔의 `inert` 경고는 FullCalendar 내부가 React 19 에 빈 문자열을 넘겨서 나는 것으로, 이 코드 문제는 아니다.
