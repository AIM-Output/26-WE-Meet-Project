# server — 유니버스 얇은 서버 (Cloudflare Workers + D1)

**남의 데이터가 필요한 기능**(F16 팀플 일정 조율부터, 나중에 F17·설치파일 안내·모바일 알림)만 맡는 서버다.
나머지 기능은 지금처럼 각자 PC 의 앱 안에서 돈다 — 이 서버가 멈춰도 앱은 팀 화면만 "잠시 후 다시 시도"를 띄우고 정상 동작해야 한다(요구사항정의서 F16 8절).

- **주소**: <https://univ-us-server.aim-output.workers.dev> (2026-11-16 첫 배포)
- **어디서 도나**: Cloudflare 데이터센터. 내 PC 를 꺼도 돌아간다. 계속 켜 둔 프로그램이 없고 요청이 올 때만 코드가 실행된다(Workers).
- **주소 하나로 둘 다**: 브라우저에 주소를 치면 웹 페이지(`public/`)가 열리고, 앱은 같은 주소의 `/v1/…` API 를 부른다.
- **DB**: D1 (Cloudflare 가 관리하는 SQLite).
- **언어**: TypeScript + [Hono](https://hono.dev). 앱의 Python 코드와 서로 import 할 수 없다 — "서버에 크롤러·자격증명 코드가 들어가지 않는다"(G5)가 언어 차원에서 지켜진다.
- 결정 배경: [WE-Meet_서버_플랫폼_검토.md](../WE-Meet_서버_플랫폼_검토.md) 13절 "2026-11-16".

```
server/
├── wrangler.jsonc          Cloudflare 설정 — 이름·D1 연결·정적 파일 폴더·환경값
├── public/                 브라우저로 여는 페이지 — 파일을 넣으면 그 이름이 주소가 된다
│   ├── index.html          첫 화면 = 넘기는 스케치북(기능마다 그림 한 장) · 차례 · 설치 방법
│   ├── sketchbook.js       책 넘김(넓은 화면) · 낱장(좁은 화면) · 펜으로 그려지는 효과 — 없어도 페이지는 읽힌다
│   ├── styles.css          디자인 v3 Paper & Pine 의 색·모서리 + 책·그림 스타일
│   ├── 404.html            없는 주소
│   ├── fonts/              앱과 같은 글꼴 — Pretendard(조각 92개 + CSS) · Plus Jakarta Sans(숫자·영문)
│   ├── icon.svg · favicon.ico   로고 — univ_us_local/frontend/src/app/ 의 복사본
│   ├── licenses.txt        함께 싣는 글꼴·아이콘의 저작권 표시
│   └── _headers            페이지에 붙는 보안 헤더(CSP 등)
├── migrations/             DB 스키마. 바꿀 때는 기존 파일을 고치지 않고 0002_… 를 새로 만든다
│   └── 0001_init.sql       users · teams · team_members
├── src/
│   ├── index.ts            진입점 — 주소 묶기 · 본문 크기 제한 · 오류 응답 모양
│   ├── env.ts              Cloudflare 에서 받는 것(DB, 환경값)의 타입
│   ├── lib/                auth(익명 토큰 확인) · crypto(해시·초대 코드) · validate(입력 검사) · errors
│   └── routes/             기능별 주소 — health · download · users · teams
├── test/                   실제 Workers 런타임 + 로컬 D1 에서 도는 테스트
├── vitest.config.ts
└── .npmrc                  npm 10 버그 우회 (아래 "버전을 고정한 이유")
```

## 지키는 선 (G5)

| 서버에 둔다 | 서버에 두지 않는다 |
|---|---|
| 익명 토큰의 **해시** · 표시 이름 | 이름 · 학번 · 이메일 · 비밀번호 · SSO 세션 |
| 팀 · 초대 코드 · 팀원 | 일정 **제목** · 과목명 · 성적 · 강의자료 |

- 스키마에 위 오른쪽 칸을 만들지 않는다. 기능을 더할 때도 "팀 공유에 꼭 필요한 것"만 올린다.
- 비밀값(API 키 등)이 생기면 `wrangler.jsonc` 가 아니라 `npx wrangler secret put <이름>` 으로 넣는다. 로컬용은 `.dev.vars`(git 제외).

## 실행 (내 PC 에서)

Node.js 20 이상. Cloudflare 계정·인터넷 없이 돈다.

```
cd server
npm install
npm run db:migrate:local     로컬 DB(.wrangler/ 안)에 스키마 적용 — 처음 한 번, 그리고 migrations/ 가 늘 때마다
npm run dev                  http://127.0.0.1:8787 (첫 화면) · http://127.0.0.1:8787/health
```

```
npm test                     테스트 (workerd 안에서, 로컬 D1 로)
npm run typecheck
```

## 브라우저로 여는 페이지

배포한 주소(<https://univ-us-server.aim-output.workers.dev>)를 브라우저에 치면 `public/index.html` 이 열린다.

- **페이지 더하기**: `public/` 에 파일을 넣는다. `public/guide.html` → `/guide`, `public/team/index.html` → `/team/`. 빌드 단계가 없다.
- **순서**: 주소가 `public/` 의 파일과 맞으면 그 파일을 바로 내준다(코드를 거치지 않아 요청 한도에 잡히지 않는다 — 정적 파일 요청은 무료·무제한). 맞는 파일이 없을 때만 `src/index.ts` 가 받는다.
- **없는 주소**: 브라우저로 열면 404 페이지, `/v1/…` 이거나 프로그램이 부른 것이면 JSON 404.
- **페이지에서 API 부르기**: 페이지와 API 가 **같은 주소**라 그냥 `fetch('/v1/…')` 하면 된다. 다른 주소의 호출을 허용하는 설정(CORS)이 필요 없다.
  다른 주소에 있는 페이지(예: 앱 창의 `http://127.0.0.1:…` 화면)가 이 서버를 직접 부르게 하려면 그때 CORS 를 켠다 — 지금은 앱 쪽은 사이드카(Python)가 부르는 것으로 보고 켜지 않았다.
- **바깥 자원**: `_headers` 의 CSP 가 이 서버의 파일만 허용한다. 바깥 스크립트·글꼴·이미지를 쓰려면 `_headers` 도 고친다. `_headers` 는 `public/` 파일에만 붙고 API 응답에는 붙지 않는다.
- **로고·글꼴**: `icon.svg` · `favicon.ico` · `fonts/` 는 프론트(`univ_us_local/frontend`)에서 복사한 것이다. 로고를 바꾸면 여기도 다시 복사하고, 표지 그림의 별자리(`index.html` 의 `art--title`)도 같이 고친다.
- `wrangler.jsonc` 의 `assets.not_found_handling` 은 켜지 않는다 — 켜면 브라우저로 여는 요청(`/download` 포함)이 코드까지 오지 않을 수 있다.

### 첫 화면 = 스케치북

기능마다 그림 한 장씩 그린 스케치북이다(2026-11-16). 색·글꼴·모서리는 앱의 디자인(`univ_us_local/frontend/DESIGN.md`)을 그대로 따른다.

- **두 가지 모양**: 넓은 화면(960px 이상)에서는 넘기는 책, 좁은 화면이나 스크립트가 꺼진 경우에는 옆으로 미는 낱장. 같은 HTML 을 `sketchbook.js` 가 책으로 바꾼다.
- **넘기는 법**: 책 가장자리의 접힌 모서리 · 아래 화살표 · 키보드 ← → · 터치로 쓸기 · 차례의 이름. 주소 뒤에 쪽 id 를 붙이면(`/#attendance`) 그 장이 펼쳐진 채 열린다.
- **구조**: `.leaf` 하나가 종이 한 장이고, 그 안의 `.page` 둘이 앞쪽(오른쪽에 보인다)과 뒤쪽(넘기면 왼쪽에 보인다)이다. HTML 에 적힌 순서가 곧 쪽 순서다. 첫 장의 앞쪽과 마지막 장의 뒤쪽은 빈 쪽(`.page--blank`)이다.
- **준비 중인 기능을 완성으로 바꾸기**: 그 `<article>` 에서 `plate--draft` 와 `<p class="plate__state">` 를 지우고, 연필 그림(`<g class="draft">`)을 색 있는 그림으로 바꾸고, 메모(`<ul class="plate__notes">`)를 넣는다. 차례에서는 그 줄을 "그리는 중" 묶음에서 위 묶음으로 옮긴다.
- **장을 더하기**: `.leaf` 를 하나 더 넣는다 — 쪽은 항상 2쪽씩 는다(남는 쪽은 준비 중인 장으로 채운다). 쪽마다 `id` · `data-title` 을 주고, 차례에 `<a href="#id">` 를 넣고, 쪽 번호(`.page__no`)를 다시 매긴다. 쪽 수는 스크립트가 HTML 에서 세므로 다른 곳은 고칠 것이 없다.
- **그림(SVG, `viewBox="0 0 420 280"`)**: 아래에서 위로 `blob`(바탕 얼룩) → `paper`(종이색 면) → `wash`(물감) → `pencil` · `ink`(선) → `lbl`(글자) 순으로 쌓는다. 잉크 선은 전부 `<path>` 로 그린다(그려지는 효과가 선의 길이를 쓴다). 색은 `styles.css` 의 `.art .w…` 에서 고르고, 손으로 그린 듯한 흔들림은 `filter="url(#f-ink)"` · `url(#f-wash)` 가 낸다.
- **지킬 것**: `style="…"` · `<style>` · 인라인 `<script>` 를 쓰지 않는다(CSP 가 막고 테스트가 잡는다). 글꼴·그림은 이 서버의 파일만 쓴다. 다크 모드는 두지 않는다.
- **테스트가 보는 것**(`test/pages.test.ts`): 페이지·글꼴 CSS 가 가리키는 파일이 다 있는지 · 종이마다 두 쪽인지 · 그림이 있는 쪽이 전부 차례에 있는지 · 인라인 코드가 없는지.
- 눈으로 볼 때: 브라우저 창이 가려져 있으면 그리기·넘김 애니메이션이 멈춘 채 보인다.

## API

`/health` · `/download` · `/v1/…` 의 응답은 JSON(또는 리다이렉트). 오류는 항상 `{ "error": { "code": "...", "message": "..." } }` — 앱은 `code` 로 분기한다.
시각은 UTC ISO 8601(`2026-11-16T03:00:00.000Z`).

| 주소 | 인증 | 내용 |
|---|---|---|
| `GET /` 와 `public/` 의 파일 | ✕ | 웹 페이지 (위 절) |
| `GET /health` | ✕ | 서버·DB 가 살아 있는지. `{ ok, service, version, time }` |
| `GET /download` | ✕ | GitHub Releases 최신 버전으로 302 — 공유용 고정 주소 |
| `POST /v1/users` | 토큰 | 익명 등록. 처음이면 201, 이미 있으면 200 과 같은 사용자 |
| `GET /v1/users/me` | 토큰 | 내 사용자 id |
| `POST /v1/teams` | 토큰 | 팀 만들기 `{ name, displayName }` → 팀장이 되고 초대 코드 6자리를 받는다 (F16-R01) |
| `POST /v1/teams/join` | 토큰 | 코드로 합류 `{ inviteCode, displayName }` — 새로 합류 201, 이미 팀원이면 200 (F16-R02) |
| `GET /v1/teams` | 토큰 | 내가 속한 팀 (F16-R06) |
| `GET /v1/teams/:teamId` | 토큰 | 팀 + 팀원(표시 이름·팀장 여부). 팀원이 아니면 404 |

| 오류 code | 상태 | 뜻 |
|---|---|---|
| `unauthorized` · `unknown_user` | 401 | 토큰이 없거나 형식이 틀림 · 등록 안 된 토큰 |
| `invalid_json` · `invalid_field` | 400 | 본문이 JSON 객체가 아님 · 칸이 없거나 길이가 틀림 |
| `invite_not_found` · `team_not_found` | 404 | 초대 코드가 틀림 · 팀이 없거나 내가 팀원이 아님 |
| `payload_too_large` | 413 | 본문 64KB 초과 |
| `not_found` · `internal_error` | 404 · 500 | 없는 주소 · 서버 오류 |

### 인증 — 익명 토큰

이메일·비밀번호가 없다(F16 D5). 앱이 기기 키를 **로컬에서** 만들고, 요청마다 `Authorization: Bearer <토큰>` 을 보낸다.

- 토큰은 `A-Z a-z 0-9 _ -` 로 된 40~128자(무작위 128비트 이상). 짧거나 추측 가능한 값은 거절한다.
- 서버는 토큰의 SHA-256 만 `users.key_hash` 에 둔다. DB 가 새도 토큰을 되살릴 수 없다.
- 사용자 id 는 해시와 따로 둔 무작위 값이다 — 기기를 바꿀 때(복구 코드, F16-S12) 해시만 갈아 끼우려는 것. 복구 코드는 아직 없다.
- 앱에서는 **사이드카(Python)가 부른다**고 보고 만들었다 — 바쁜 시간을 올리는 주체가 사이드카이고, 기기 키도 화면이 아니라 앱 데이터 폴더에 두기 위해서다. 이 서버의 웹 페이지가 API 를 부르는 것은 같은 주소라 그대로 된다("브라우저로 여는 페이지" 절).

## 기능을 더할 때

1. 표가 필요하면 `migrations/000N_이름.sql` 을 새로 만든다 → `npm run db:migrate:local`.
2. `src/routes/이름.ts` 에 `new Hono<AppEnv>()` 를 만들고, 로그인한 사용자만 쓰면 `use('*', requireUser)`.
3. `src/index.ts` 에 `app.route('/v1/이름', …)` 한 줄.
4. `test/이름.test.ts` — `registerUser()` 로 새 사용자를 만들어 쓰면 테스트끼리 섞이지 않는다.

무료 한도 때문에 지킬 것:

- **무거운 계산은 서버에서 하지 않는다**(요청당 CPU 10ms). F16 교집합 계산 `findSlots` 는 앱(사이드카) 쪽에 둔다.
- **쓰기를 아낀다**(하루 10만 행). 바쁜 시간은 블록마다 한 행이 아니라 **사람당 한 행(JSON)** 으로, 바뀐 때만 올린다.
- 한 요청에서 DB 질의 50번, 바깥 호출 50번까지. 여러 문장은 `db.batch([...])` 로 묶는다(한 번으로 세고, 한 트랜잭션이다).

## 배포 (저장소 주인)

2026-11-16 에 처음 배포했다. **바꾼 것을 올릴 때**는 Cloudflare 계정에 로그인된 PC 에서:

```
cd server
npm test                     먼저 통과하는지
npm run db:migrate:remote    migrations/ 에 새 파일이 있을 때만 — 배포보다 먼저
npm run deploy               → https://univ-us-server.aim-output.workers.dev
```

올린 뒤 `/health` 가 `"ok":true` 인지, 첫 화면이 열리는지 본다.

### 처음에 한 일 (기록 — 새 계정으로 다시 만들 때만)

```
npx wrangler login                                 브라우저가 열린다 — Cloudflare 계정으로 허용
npx wrangler d1 create univ-us --location apac     DB 만들기 → 출력된 database_id 를 wrangler.jsonc 의 DB 항목에 넣는다
npm run db:migrate:remote                          배포된 DB 에 스키마 적용 ("continue?" 에 Y)
npm run deploy                                     처음이면 workers.dev 이름을 묻는다
```

- Cloudflare 계정의 **이메일 인증**을 마쳐야 배포된다(안 했으면 `code: 10034`).
- 처음 배포할 때 묻는 workers.dev 이름(`aim-output`)은 **계정 전체**가 쓰는 이름이고 전 세계에서 하나뿐이어야 한다. 바꾸면 기존 주소가 끊긴다.
- 이름을 막 등록한 직후 몇 분은 접속이 됐다 안 됐다 한다(인증서 준비 중).
- `d1 create` 가 "설정 파일에 추가할까요?"라고 물으면 **아니오**. 예라고 하면 기존 항목을 고치지 않고 이름(`binding`)이 다른 항목을 하나 더 덧붙인다 — 코드는 `DB` 만 쓰므로 소용이 없고, 같이 들어가는 `"remote": true` 는 로컬 실행에서도 실제 DB 를 건드리게 만든다. `d1_databases` 에는 `DB` 항목 하나만 둔다.
- 그다음부터는 코드가 바뀌면 `npm run deploy`, 스키마가 바뀌면 그 전에 `npm run db:migrate:remote`.
- `database_id` 는 비밀이 아니다(계정 로그인 없이는 쓸 수 없다) — 커밋한다.
- 배포 전 확인: `npx wrangler deploy --dry-run`.

## 무료 한도 (2026-11-16 Cloudflare 공식 문서 기준)

| 항목 | 무료 한도 | 넘으면 |
|---|---|---|
| 요청 | 하루 10만 | 그날 요청이 실패 — 한국 시간 09:00(UTC 0시)에 풀린다 |
| CPU | 요청·예약 실행 한 번에 10ms | 그 요청이 실패 |
| 바깥 호출(subrequest) | 요청 한 번에 50 | 〃 |
| D1 읽기 · 쓰기 | 하루 500만 행 · 10만 행 | 질의가 실패(2026-09-01 부터) |
| D1 크기 | DB 하나 500MB, 계정 합계 5GB, DB 10개 | |
| D1 질의 | 요청 한 번에 50 (batch 는 1로 센다) | |
| 예약 실행(Cron) | 계정에 5개 | |
| 정적 파일(`public/`) | 요청은 무료·무제한 · 파일 하나 25 MiB · 2만 개 | 그래서 설치파일(47MB)은 GitHub Releases 에 둔다 |

모자라면 Workers 유료(월 $5)가 다음 단계다 — 코드는 그대로 쓴다.

## 버전을 고정한 이유

개발 안내가 Node.js **20 이상**이라 그 위에서 도는 조합으로 맞췄다.

| 패키지 | 고정 | 이유 |
|---|---|---|
| `wrangler` | 4.86.0 (2026-04) | Node 20 에서 도는 마지막 버전. 4.87 부터 Node 22 필요 |
| `@cloudflare/vitest-pool-workers` | 0.15.1 | wrangler 4.86.0 과 짝. 이름이 `@cloudflare/vitest-plugin` 으로 바뀌었다는 경고가 뜬다 — 무시 |
| `vitest` · `vite` | 4.1.5 · 6.x | 위 패키지와 짝 · vite 7 은 Node 20.19 이상 |
| `.npmrc` `legacy-peer-deps` | | npm 10.8 이 설치 중 `Cannot read properties of null (reading 'edgesOut')` 로 죽는 것 우회 |

- `npm install` 때 `undici` 의 Node 버전 경고(EBADENGINE)가 뜬다 — Node 20.16 에서 테스트·로컬 실행·배포 묶기까지 확인했다.
- `compatibility_date` 는 설치된 wrangler 의 런타임이 아는 날짜(2026-04)까지만 쓸 수 있다.
- Node 20 은 2026-04 에 지원이 끝났다. 팀이 Node 22 이상으로 올리면 위 넷을 최신으로 올리고 `.npmrc` 를 지운다.

## 아직 없는 것

- F16 나머지 — 탈퇴·팀 삭제·팀장 넘기기·초대 코드 재발급, 바쁜 시간, 투표, 확정 회의, 팀 할 일, 복구 코드
- 요청 횟수 제한(초대 코드 마구 넣어 보기·무한 등록 막기) — **주소가 이미 공개돼 있다.** 앱에 연결해 팀원에게 열기 전에 넣는다
- 앱 쪽 연결(사이드카의 원격 클라이언트, `/team` 화면의 예시 데이터 걷어내기)
- 초대 링크 페이지(`/join/코드` — 지금은 404), OS 별 설치파일 바로 받기(지금 `/download` 는 GitHub 의 최신 버전 페이지로 넘긴다)
- 밥집 추천, 모바일 알림
