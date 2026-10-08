# desktop — 유니버스 데스크톱 앱 (Tauri + Python 사이드카)

저장소 실행(`유니버스 열기.cmd` / `.command`)과 **같은 코드**를 설치형 앱으로 묶는다. 계획·결정은
[WE-Meet_데스크톱앱_맥지원_계획.md](../WE-Meet_데스크톱앱_맥지원_계획.md) 4단계.

```
UnivUs (Tauri, Rust)                         univus-backend (PyInstaller onedir, Python)
 ├ 시작 화면(splash) ─ 실행 ─────────────────▶ desktop.py: 앱 데이터 폴더 · 빈 포트 · FastAPI
 │                     ◀── UNIVUS_READY {launchUrl} (표준출력)
 ├ 창 → http://127.0.0.1:<포트>/desktop/launch?code=… → 세션 쿠키(HttpOnly) → 대시보드
 ├ 트레이: 열기 · 로그인할 때 실행 · 종료          수집기·로그인 창·예약 실행 = 같은 실행 파일 --run-module eclass …
 └ 종료 → 표준입력 닫기 → 사이드카가 스스로 끝남   (기능별 .venv 가 없다 — osenv.module_cmd)
```

| 폴더 | 내용 |
|---|---|
| `src-tauri/` | Rust 껍데기 — `src/main.rs`(사이드카·창·트레이·바깥 링크), `tauri.conf.json`, `icons/` |
| `splash/` | 서버가 뜰 때까지 보이는 시작 화면 (Tauri API 없음) |
| `sidecar/` | `univus-backend.spec`(PyInstaller) · `build.py` · 빌드용 `requirements.txt` |
| `src-tauri/tauri.dev.conf.json` | 개발 모드(`npm run dev`) 덧씌움 — 식별자 `.dev`, next dev 띄우기 |

## 동작

- **데이터**: 설치 폴더(`%LOCALAPPDATA%\UnivUs`)가 아니라 `%LOCALAPPDATA%\kr.univus.desktop\data` / `~/Library/Application Support/kr.univus.desktop/data` 에 저장소와 같은 모양으로
  (`<폴더>/F6_Eclass_agent/data` …, C0 `osenv.appdata`). 서버 로그 `logs/backend.log`, Chromium `pw-browsers/`.
- **Chromium**: 첫 실행 때 백그라운드로 받는다(약 150MB, `logs/browsers.log`). 받는 동안 로그인·가져오기는 "내려받는 중"이라고 답한다.
- **보안**: 서버는 127.0.0.1 의 빈 포트에만 열리고, 앱 창이 가진 세션 쿠키가 없으면 모든 요청에 403 —
  같은 PC 의 다른 프로그램·브라우저 탭이 성적·일정·로그인 세션을 다루는 API 를 부를 수 없다. 대시보드에는 Tauri API 를 열지 않는다.
- **창 닫기 = 트레이로 숨기기** (예약 수집·마감 알림은 계속). 완전히 끝내려면 트레이 → 종료. 두 번 실행하면 떠 있는 창을 앞으로.
- **바깥 링크**(e클래스·학교 공지)는 기본 브라우저로, 강의자료 원문 등 로컬 주소는 앱 창으로.
- **예약 실행**: 대시보드 `켜기` 가 Windows 작업 스케줄러 / 맥 launchd 에 **앱 실행 파일**을 등록한다(`--run-module eclass tick`).
- 저장소에서 쓰던 데이터를 옮기려면: `python -m osenv migrate-data` (C0_Platform_agent 폴더에서, 덮어쓰지 않음)

## 빌드

준비: Python 3.12 · Node 20+ · Rust(rustup) · Windows 는 Visual Studio C++ 빌드 도구 / 맥은 Xcode 명령줄 도구.

```bash
py -3.12 desktop/sidecar/build.py     # 맥: python3.12 desktop/sidecar/build.py → desktop/sidecar/dist/univus-backend/
cd desktop
npm install
npx tauri build                       # → src-tauri/target/release/bundle/ (Windows nsis 설치 파일 약 46MB · 맥 .app/.dmg)
```

- 화면을 고쳤으면 먼저 `univ_us_local/frontend` 에서 `npm run build` (사이드카가 `frontend/out` 을 묶는다).
- 아이콘: `src-tauri/icons/source.png` 를 바꾸고 `npm run icon`.

## 개발 모드 (`npm run dev`)

설치본을 빌드하지 않고 소스 그대로 앱 창에서 돌린다. 화면(`univ_us_local/frontend/src`)을 고치면 창에 바로 반영되고,
백엔드·기능 코드(`.py`)를 고치면 `npm run dev` 를 다시 띄운다 (Rust `src-tauri/` 는 tauri dev 가 알아서 다시 빌드).

```bash
cd desktop
npm run dev        # = tauri dev --config src-tauri/tauri.dev.conf.json
```

```
tauri dev ─ beforeDevCommand ─▶ next dev 127.0.0.1:3000 (univ_us_local/frontend, 즉시 반영)
   │                                   │ rewrites: /api · /desktop/launch · /study-calendar
   └ 디버그 빌드 창 ─ 실행 ─▶ univ_us_local/backend/.venv python desktop.py --dev --port 8020 --frontend-url http://127.0.0.1:3000
                                         --data-root desktop/.dev-data
```

| | 설치본 | 개발 모드 |
|---|---|---|
| 식별자 | `kr.univus.desktop` | `kr.univus.desktop.dev` (`tauri.dev.conf.json`) — 설치본이 떠 있어도 따로 뜬다, WebView2 프로필도 따로 |
| 데이터 | `%LOCALAPPDATA%\kr.univus.desktop\data` | `desktop/.dev-data` (git 제외) |
| 화면 | 묶은 `frontend/out` | next dev (`:3000`) |
| 백엔드 | 사이드카 실행 파일, 빈 포트 | 저장소 소스, 포트 `8020` 고정 (`next.config.ts` 의 `BACKEND_URL` 기본값과 같아야 한다) |
| 서버 로그 | `logs/backend.log` | tauri dev 터미널 |
| 예약 실행 | 켜기/끄기 됨 | **꺼짐** (`--dev` → `F1_TASKS`·`F6_TASKS=off`) — 같은 작업 이름이라 설치본 등록을 덮어쓰지 않게 |

- 준비(한 번): `univ_us_local/backend/.venv` (`py -3.12 -m venv univ_us_local/backend/.venv` → 그 python 으로 `pip install -r univ_us_local/backend/requirements.txt`),
  `univ_us_local/frontend` 에서 `npm install`. 로그인·수집은 아직 기능별 `.venv`(C3_Login_agent·F1_Bachelor_agent)를 부른다 — 하나로 합치는 것은 정리 단계에서.
- 개발 데이터 채우기: `.dev-data` 를 지운 뒤 `C0_Platform_agent` 에서 `py -3.12 -m osenv migrate-data --to ../desktop/.dev-data`
  (저장소 `data/`·`state/` 를 복사, 덮어쓰지 않음). 비워 두면 첫 설정(온보딩) 화면부터 시작한다.
- 3000·8020 포트가 비어 있어야 한다. 묶은 사이드카를 dev 창으로 시험하려면 `UNIVUS_SIDECAR=<sidecar/dist/…/univus-backend(.exe)>` (이때는 데이터·포트가 설치본 규칙).
- 앱 창 밖 브라우저로 `http://127.0.0.1:3000` 을 열면 API 가 403 이다 (세션 쿠키는 앱 창만 가진다) — 정상.

**주의 (Windows, Claude 데스크톱 앱 안에서 작업할 때)**: Claude 앱은 MSIX 패키지라, 거기서 띄운 프로세스가 `%LOCALAPPDATA%` 에 새로 만드는 파일은
실제 위치가 아니라 `%LOCALAPPDATA%\Packages\Claude_…\LocalCache\Local\` 로 간다. 설치 파일 실행·`migrate-data`(기본 위치)는 그 안에서 하지 말 것.
개발 모드 데이터는 저장소 안(`desktop/.dev-data`)이라 영향이 없다.

## 알려진 문제

- **예약 작업 이름이 저장소 실행과 같다.** 앱 모드도 `UnivUs-F6-Eclass-Sync` · `UnivUs-F1-Academic-Sync`(맥 launchd `kr.univus.f6-eclass-sync` · `kr.univus.f1-academic-sync`)를 쓴다.
  그래서 한 PC 에서 앱과 저장소 실행을 같이 쓰면, 한쪽에서 예약 실행 `켜기`/다시 등록을 누를 때 다른 쪽 등록을 덮어쓴다 (예약이 앱 실행 파일 ↔ 저장소 `.venv` 사이에서 바뀐다).
  모드별로 이름을 나눌 때까지는 한 PC 에서 둘 중 하나만 쓴다. 이름을 바꾸면 기존 등록을 못 찾으므로, 바꿀 때 옛 이름을 지우는 처리(F6 `LEGACY_TASK_NAMES` 처럼)를 같이 넣는다.

## 아직 안 한 것 (계획 문서 4단계)

- 코드 서명(Windows SmartScreen 경고 · 맥 공증) — 인증서·Apple 개발자 계정 필요
- 자동 업데이트(tauri-plugin-updater) — 서명 키·배포 위치(GitHub Releases) 결정 필요
- CI 에서 설치 파일 만들기, `frontend/out` 커밋 중단
