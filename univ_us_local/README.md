# univ_us_local — 유니버스(Univ-Us) 개인 로컬 서버 웹

내 PC에서 도는 대시보드. e클래스 과제·마감(F6)·학사 일정(F1)·수업(F3)을 캘린더(C1)에 띄우고, 내 일정을 등록·수정한다.
자격증명·강의자료·세션은 전부 PC 안에 남는다 (설계 배경: `../WE-Meet_서버_플랫폼_검토.md` 8·10절 "안 B").
**기능 코드는 전부 기능 폴더에 있고**(`../C1_Calendar_agent` · `../F6_Eclass_agent` · …) 이 서버는 그 API 를 붙이는 곳이다.

```
univ_us_local/
├── backend/            FastAPI (127.0.0.1:8000) — /api + 프론트 정적 서빙
│   ├── app/main.py     라우트 (courses / status / sync) + C1·F6·C2·F1·F2·F3·F4·F5 라우터 include + 캘린더 소스 배선
│   ├── app/calendar_events.py ../C1_Calendar_agent 의 API(calendar_core.api)를 붙인다 — /api/events · 내 일정·할 일 (C1)
│   ├── app/eclass_data.py ../F6_Eclass_agent 의 API(eclass.api)를 붙인다 — 과제 마감·수집 실행·로그인 창·마감 알림 (F6)
│   ├── app/academic.py ../F1_Bachelor_agent 의 API(bachelor.api)를 붙인다 — 학사 일정·수집 원천·알림 (F1)
│   ├── app/student_profile.py ../C2_Profile_agent 의 API(student.api)를 붙인다 — 프로필·학과 마스터 (C2)
│   ├── app/graduation.py ../F2_Graduation_agent 의 API(graduation.api)를 붙인다 — 졸업요건·이수 내역 (F2)
│   ├── app/attendance.py ../F3_Attendance_agent 의 API(attendance.api)를 붙인다 — 출결·수업 회차·경고 (F3)
│   ├── app/materials.py ../F4_Textbook_agent 의 API(textbook.api)를 붙인다 — 강의자료 목록·원문 열기 (F4)
│   ├── app/exams.py    ../F5_Test_agent 의 API(exams.api)를 붙인다 — 시험·학습 계획·학습 블록 (F5)
│   ├── app/config.py   기능 폴더 경로·포트·허용 Origin·과목 색
│   ├── requirements.txt · run.cmd
│   └── .venv/          (run.cmd 가 처음 실행 때 만든다)
├── frontend/           Next.js 16 + Tailwind 4 + FullCalendar 7 + motion + lucide-react
│   ├── DESIGN.md       디자인 시스템 v2 (토큰·글자·치수·공용 부품)
│   ├── src/app/        라우트 17개 (Frontend-Route 2-1) — 각 page.tsx 는 Suspense 로 감싼 클라이언트 화면
│   ├── src/components/ app(헤더·공용 데이터) · ui(공용 부품) · dashboard · events(상세·새 일정 모달) · pages(기능 화면)
│   └── src/lib/        api · useQueryState(모달=push/탭=replace) · priority(F7) · demo/(예시 데이터)
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
| `/` | 브리핑 카드 → 3단(등록·빠른 실행·확인 필요·대화 카드 / 캘린더 월·주·목록·학기 / 먼저 할 것·할 일) → 기능 타일 10개. `?event=` 상세 · `?new=event` 새 일정 · `?place=preview` 공강 배치 | **실제**(일정·마감·학사일정·동기화 2종) |
| `/assignments` | 진행 중/완료/지난 마감 · 급한 순 그룹(F7) · 소요시간 편집 · 내가 체크함 | **실제** (소요시간·체크는 브라우저 임시 저장) |
| `/academic` | 학기 선택 · 전체/내 해당/확인 필요/숨김 · 월 묶음 · 확인 필요 카드(날짜 고쳐 승인) · 내 캘린더에 담기 | **실제** (F1_Bachelor_agent) |
| 헤더 🔔 | 알림 팝오버 — 놓친 알림 / 최근, 같은 시각 알림 묶음, 모두 읽음 | **실제** (학사일정 알림 · 출결 경고) |
| `/graduation` | 요약(남은 학점·판정·판정 근거·영역별·교양 영역 조건·졸업인증) · 이수 과목(구분 지정·제외·직접 입력) · 가정 계산(내 계획) · `?area=` 포함 과목 모달 | **실제** (F2_Graduation_agent) |
| `/onboarding` · `/settings/*` 5개 | 첫 설정 3단계 · 프로필·수집 원천·졸업요건 기준·가용 시간·알림 | **첫 설정·내 프로필·졸업요건 기준은 실제**(C2 — 학과 목록 625곳, 학사시스템 가져오기 / F2 — 룰셋 보기·수정·되돌리기, 교과구분 매핑, 교육과정 받기), 수집 원천의 e클래스·학사·기이수성적 행과 알림 기준 시각도 실제, 나머지 예시. 프로필이 하나도 없으면 `/` 가 `/onboarding` 으로 보낸다 |
| `/attendance` | 과목별 현황(결석/허용 횟수 막대·남은 여유·상태·근거 줄·누적 직접 수정·회차 목록 칩 출석·결석·지각·공결·휴강, 학사일정·e클래스 공지 휴강은 자동) · 이번 주 몰아서 입력 · 시간표 설정(자동 가져오기·요일·교시·한도·지각 환산·학기·휴업일·교시 시각). 캘린더 주·목록 보기의 수업을 눌러도 출결 | **실제** (F3_Attendance_agent) |
| `/courses` | 과목별 강의자료 — 종류(강의자료·게시판 첨부·과제 첨부·직접 추가)·주차(추정)·쪽수·상태, 파일 끌어다 추가, 앱 안에서 열기·내려받기 | **자료 탭·원문 뷰어는 실제** (F4_Textbook_agent). 요약·문제·질문 탭은 예시 (모델 정해진 뒤) |
| `/exams` | 시험 목록(공지에서 찾은 것·확인 필요·지난 시험) + 우측 패널 3단계(옵션 → 미리보기 → 진도) · 시험 추가·수정·삭제 | **실제** (F5_Test_agent). 캘린더의 시험·학습 블록 상세, 대시보드 `오늘 공부` 타일도 같은 데이터 |
| `/briefing` `/chat` `/opportunities` `/team` | F7~F16 기능 화면 뼈대 | 예시 |

- **예시 데이터**는 `src/lib/demo/` 에 모여 있고 화면마다 "예시 데이터" 띠로 표시한다. API 가 생기면 `lib/api.ts` 에 같은 모양의 함수를 만들고 바꿔 끼운다.
- 모달·패널은 쿼리 파라미터 + `push`(뒤로가기로 닫힘), 탭·필터는 `replace` — `lib/useQueryState.ts` 한곳에서 처리.
- 반응형: ≥1280 3단 · 768~1279 캘린더 위 2단 · <768 1단(캘린더 → 실행 → 할 일), 모달은 바텀 시트, 일정 추가는 오른쪽 아래 떠 있는 버튼.
- `next.config.ts` 의 `trailingSlash: true` 로 `out/academic/index.html` 처럼 폴더마다 만들어져 주소창에 `/academic` 을 직접 쳐도 열린다.

## API (`/api/docs` 에 Swagger)

| 메서드 | 경로 | 내용 |
|---|---|---|
| GET | `/api/events?start&end` | 캘린더 전체 — 내 일정 + e클래스 마감 + 학사 일정 + 수업 회차 (FullCalendar 형식, `extendedProps.kind` = `user` / `deadline` / `academic` / `class`). 합치는 곳은 C1 이고 소스 배선은 `app/main.py` 의 `CALENDAR_SOURCES` |
| POST | `/api/events` | 내 일정/할 일 추가 `{title, start, end, all_day, category, memo, is_todo, done, origin?}` — `origin='ac:…'` 은 학사 일정 '내 일정에 넣기'(같은 학사 일정이면 409) |
| PATCH / DELETE | `/api/events/{id}` | 내 일정만 (`dl:`·`ac:`·`cl:` 로 시작하는 id 는 거부) — 나머지는 [C1_Calendar_agent/README.md](../C1_Calendar_agent/README.md) |
| GET | `/api/courses` | 과목 + 색 |
| GET | `/api/status` | `updated_at`(마지막 e클래스 수집 성공), 동기화 진행 상태 `sync`, 건수, 분류표, sync.log 끝부분, **`calendar`**(내 일정 DB 자리·건수·분류표, C1), **`eclass`**(진행 중·지난 마감 수·연속 실패·로그인 필요·재시도·다음 주기·updatedAt, F6), **`academic`**(학사 원천 상태·확인 필요 건수·마지막 수집의 신규 건수 `newCount`·`lastRunAt`·updatedAt), **`graduation`**(남은 학점·판정·한 줄 요약·updatedAt — 기능 타일) |
| POST | `/api/sync` | e클래스 수집 시작(F6). 이미 돌고 있으면 띄우지 않고 `already_running: true` 를 붙여 상태만 반환 |
| GET / PATCH | `/api/assignments/{id}` | F6 과제 상세(변경 이력) · `{userDone}` 내가 체크함 · `{estimatedHours}` 소요시간. 목록 `GET /api/assignments?tab=`, 알림 시점 `GET/PUT /api/assignments/settings` — 나머지는 [F6_Eclass_agent/README.md](../F6_Eclass_agent/README.md) |
| GET / PATCH | `/api/sources/eclass` | e클래스 수집 원천 — 주기·예약 작업·최근 실행·연속 실패·로그인 상태 · `{intervalHours}` 주기 변경(작업 스케줄러 재등록) · `{scheduled}` 예약 켜기/끄기 |
| POST / GET | `/api/sync/login` | 로그인 창 열기 (C3 — 이 PC 화면에 브라우저 창) → 로그인되면 바로 수집 |
| GET / POST | `/api/eclass/feed` · `/api/eclass/feed/{id}` · `/api/eclass/feed/read` · `/api/eclass/feed/settings` | E클래스 새 글·자료 (공지·자료실 글·강의자료) · 본문 · 읽음 · 알림 켜고 끄기 — `status.eclass.feed` 에 안 읽은 수 |
| GET / PATCH / DELETE | `/api/profile` | C2 프로필 (C2_Profile_agent/data/profile.db). 항목별 자동/입력 출처, 필수 채움 여부. 이름·학번은 받지 않는다 — 나머지는 [C2_Profile_agent/README.md](../C2_Profile_agent/README.md) |
| GET / POST | `/api/master/departments` · `/api/master/departments/sync` | 학과 선택기 목록 · 교육과정검색 재수집 |
| POST / GET | `/api/profile/import` | 학사정보시스템 가져오기 (C3_Login_agent 세션) · 진행 상태, 로그인 기록 없으면 409 |
| GET | `/api/academic/events` | 학기 목록 + 학사 일정 전체 (F1, 탭은 화면에서 거름) |
| PATCH | `/api/academic/events/{id}` | `{status: approved\|hidden\|restore, start, end, memo, pinned, reminders}` — 원천 값은 안 바뀐다 |
| GET | `/api/academic/upcoming?days=3` · `/api/academic/status` · `/api/academic/settings`(PUT) | 브리핑용 · 원천 상태 · 알림 기준 시각 |
| GET | `/api/sources` | 학사 수집 원천 4곳 (`jnu_calendar` 학사일정 표 · `jnu_notice` 학사안내 · `my_dept` 내 학부 · `my_college` 내 단과대학) — ③·④ 는 프로필 소속으로 찾은 홈페이지·게시판과 상태(`resolve`·`stale`)를 같이 준다 |
| PATCH | `/api/sources/{key}` | `{enabled}` 켜고 끄기 (끄면 그 원천에서만 온 일정이 목록·캘린더에서 빠지고, 다시 켜면 돌아온다) · `{overrideUrl}` ③·④ 게시판 직접 지정 (`null` = 자동으로) |
| POST | `/api/sources/{key}/sync` | 지금 수집 (`academic` 이면 켜진 학사 원천 전부) — `F1_Bachelor_agent/run-sync.cmd` 를 백그라운드로 |
| GET | `/api/notifications` | 알림 (때가 된 것을 먼저 배달, 놓친 알림 표시) · `POST /{id}/read` · `POST /read-all` |
| GET | `/api/graduation/status?track=` | F2 졸업요건 — 판정·영역별·인증·이수 과목·기준. 과목 추가·구분 지정·가정 계산·룰셋 수정 등 나머지는 [F2_Graduation_agent/README.md](../F2_Graduation_agent/README.md) |
| POST / GET | `/api/graduation/sync` | 학사정보시스템 기이수성적 가져오기 (C3_Login_agent 세션) · 진행 상태, 로그인 기록 없으면 409 |
| GET | `/api/attendance/summary?semester=` | F3 출결 — 학기·과목(시간표·회차·집계)·합계·교시 시각. 출결 찍기·휴강·보강·시간표 저장·자동 가져오기 등 나머지는 [F3_Attendance_agent/README.md](../F3_Attendance_agent/README.md) |
| GET | `/api/materials?course=&kind=&q=` | F4 강의자료 — 과목 요약 + 자료 목록(종류·주차·쪽수·상태). 직접 추가·삭제·다시 훑기는 [F4_Textbook_agent/README.md](../F4_Textbook_agent/README.md) |
| GET | `/api/materials/{id}/file` | 원문 열기(inline) · `?download=1` 내려받기 — **자료 id 로만** 연다(경로를 받지 않는다). 파일은 PC 밖으로 나가지 않는다 |
| GET | `/api/exams?semester=` | F5 시험 — 다가오는 시험·확인 필요·지난 시험·오늘 분량. 시험 추가·수정, 계획 미리보기·등록·진도·재조정은 [F5_Test_agent/README.md](../F5_Test_agent/README.md) |
| POST | `/api/study-plans/preview` · `/api/study-plans` | 계획 계산(저장 안 함) · 등록(학습 블록 생성). 조정안은 본문에 `apply` 를 넣어 다시 부른다 |

`/api/events` 에는 학사 일정 중 **내 캘린더에 등록된 것**(자동+내 해당, 승인, 담기)이 `extendedProps.kind = "academic"` 으로 섞여 온다.
두 주가 넘는 신청 기간은 `id#start`·`id#end` 두 점으로 오고 `extendedProps.refId` 가 원래 id 다.
수업 회차(F3)는 `extendedProps.kind = "class"`, id `cl:<과목>:<날짜>:<교시>` 로 온다(휴업일 회차는 빼고). 시각은 학교 시간표 모듈(월수금 50분·화목 75분)로 계산돼 있고, 캘린더는 주·목록 보기에서만 그린다.

과제 마감(F6)은 `extendedProps.kind = "deadline"`, id `dl:<e클래스 활동 번호>` 로 온다 — 제출 상태·내가 체크함·변경 이력(`changed`)·첨부 이름이 같이 실린다.

시험(F5)은 `extendedProps.kind = "exam"`, id `ex:<과목>:<해시8>` 로 온다 — **날짜가 확정된 시험만**(임의 일정·확인 필요는 빠진다).
공부 계획(학습 블록)은 `/api/events` 에 넣지 않는다 — F5 의 공부 캘린더(`/study-calendar`, 데이터 `GET /api/study-calendar`)에만 있다 (2026-10-01).

`sync` = `{running, started_at, finished_at, exit_code, source, runSource, attempt, retry, error, counts, ledger, pid}`. `source` 는 `button`(대시보드에서 누름) 또는
`external`(작업 스케줄러 예약 실행·명령줄 — `F6_Eclass_agent/state/sync.lock` 의 pid 가 살아 있으면 실행 중으로 본다). `runSource` 는 이력의 원래 값(schedule·catchup·retry·button·manual).
안 돌고 있을 때는 가장 최근 실행의 결과이며, 이력은 `F6_Eclass_agent/state/runs.jsonl` 에서 읽는다. 종료 코드: 0 성공 · 1 오류 · 2 로그인 필요 · 3 건너뜀 · 4 네트워크 오류 · -1 시간 초과.
버튼을 누르면 잠금 파일에 더해 `-m eclass sync|tick` 프로세스가 실제로 있는지도 확인한다 (Windows: PowerShell CIM, 1초쯤).
`/api/status` 를 부를 때마다(1분) 때가 된 과제 마감 알림(D-3·D-1·당일)·마감 변경·수집 실패 알림을 알림 센터(F1 notifications 표)에 넣는다.
프론트는 동기화 중엔 3초, 평소엔 1분 간격으로 `/api/status` 를 봐서 예약 실행도 "예약 동기화 진행 중…" 으로 보여 준다.

날짜는 tz 없는 로컬 문자열. 종일 일정의 `end` 는 FullCalendar 규칙대로 **exclusive** (9/24~9/25 → `end=2026-09-26`).

## 지키는 선

- `127.0.0.1` 에만 바인딩. Host 가 localhost/127.0.0.1 이 아니면 400, 변경 요청의 Origin 이 허용 목록 밖이면 403 (DNS 리바인딩·CSRF 대비). LAN 에 열려면 인증·HTTPS 를 먼저.
- 캘린더(C1)는 `C1_Calendar_agent` 의 코드·DB(`data/univus.db`). `/api/events` 라우터가 거기 있고, 이 서버는 다른 기능의 일정(F6 마감·F1 학사·F3 수업)을 소스로 넘겨주기만 한다. 그 폴더가 없으면 `/api/events` 가 붙지 않고 `/api/status` 의 `calendar.available=false`.
- e클래스 과제·마감(F6)은 `F6_Eclass_agent` 의 코드·원장(`data/eclass.db`). 수집(playwright)은 이 서버가 아니라 `C3_Login_agent/.venv` 의 python 으로 따로 돈다. 학교 로그인·자격증명은 `C3_Login_agent` 몫이다. F6 폴더가 없으면 과제가 빠진 채 나머지는 동작한다(`/api/status` 의 `eclass.available=false`).
- 학사 일정(F1)은 `F1_Bachelor_agent` 의 코드·DB(`data/academic.db`)를 그대로 쓴다. 그 폴더가 없거나 못 불러와도 나머지 화면은 동작한다(`/api/status` 의 `academic.available=false`).
- 프로필(C2)은 `C2_Profile_agent` 의 코드·DB(`data/profile.db`). F1·F2 는 여기서 프로필을 읽는다. 그 폴더가 없으면 '프로필 없음'으로 동작한다.
- 졸업요건(F2)은 `F2_Graduation_agent` 의 코드·DB(`data/graduation.db`). 계산은 그쪽 규칙 코드 한 곳에서만 하고 화면은 결과만 그린다. 그 폴더가 없으면 `/api/status` 의 `graduation.available=false`.
- 출결(F3)은 `F3_Attendance_agent` 의 코드·DB(`data/attendance.db`). 학기 범위·휴업일은 F1 DB 를 읽기만 하고, 경고는 F1 의 알림 표에 넣는다. 그 폴더가 없으면 `/api/status` 의 `attendance.available=false`.
- 강의자료(F4)는 `F4_Textbook_agent` 의 코드·DB(`data/textbook.db`)·**보관함**(`data/materials/`). F6 가 받아 둔 파일을 하드링크(안 되면 복사)로 들여와 F4 에서 연다 — F6 `data/` 를 지워도 자료는 남는다. 그 폴더가 없으면 `/api/status` 의 `materials.available=false`.
- 시험·학습 계획(F5)은 `F5_Test_agent` 의 코드·DB(`data/exams.db`). 시험은 e클래스 공지(F6 가 모아 둔 글)에서 찾고 분량은 F4 의 쪽수를 읽는다 — 둘 다 읽기만 한다. 계산은 규칙 기반이고 LLM 호출이 없다. 그 폴더가 없으면 `/api/status` 의 `exams.available=false`.
- `data/`·`.venv/`·`node_modules/` 는 커밋하지 않는다. `frontend/out/`(빌드 결과)은 **커밋한다** — 팀원이 Node 없이 실행하기 위해. 프론트를 고쳤으면 `npm run build` 후 `out/` 도 함께 커밋.

## 다음 단계 (아래 Features 칸 순서)

F7 우선순위 → F9 자연어 일정 → F10 브리핑(스케줄러 내장) → F4 강의자료 → F11 장학 → 알림 채널(앱 내 알림·텔레그램). 폰 접근은 Tailscale, 정시 배달·F16·F17 은 얇은 서버 — 검토 문서 참고.

## 알아둘 것

- 백엔드는 HTML 에 `Cache-Control: no-cache`, `_next/static` 에 영구 캐시 헤더를 붙인다(빌드 뒤 옛 화면이 남지 않게). 이 헤더가 생기기 전에 열어 본 브라우저는 **한 번만 Ctrl+F5** 로 새로고침하면 된다.
- FullCalendar 7 은 클래스명이 해시라 CSS 로 직접 스타일하지 않고, 테마 변수(`--fc-breezy-*`)와 `eventContent`/`className` 옵션으로 만진다.
- 콘솔의 `inert` 경고는 FullCalendar 내부가 React 19 에 빈 문자열을 넘겨서 나는 것으로, 이 코드 문제는 아니다.
