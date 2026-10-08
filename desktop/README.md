# desktop — 유니버스 데스크톱 앱 (Tauri + Python 사이드카)

유니버스는 **데스크톱 앱으로만** 실행한다 (2026-10-08 — 브라우저로 여는 로컬 웹 실행 방식·저장소 런처는 없앴다).
기능 코드(`C*_agent`·`F*_agent`)와 대시보드(`univ_us_local/`)를 설치형 앱으로 묶는다. 계획·결정은
[WE-Meet_데스크톱앱_맥지원_계획.md](../WE-Meet_데스크톱앱_맥지원_계획.md) 4단계.

```
UnivUs (Tauri, Rust)                         univus-backend (PyInstaller onedir, Python)
 ├ 시작 화면(splash) ─ 실행 ─────────────────▶ desktop.py: 앱 데이터 폴더 · 빈 포트 · FastAPI
 │                     ◀── UNIVUS_READY {launchUrl} (표준출력)
 ├ 창 → http://127.0.0.1:<포트>/desktop/launch?code=… → 세션 쿠키(HttpOnly) → 대시보드
 ├ 트레이: 열기 · 로그인할 때 실행 · 종료          수집기·로그인 창·예약 실행 = 같은 실행 파일 --run-module eclass …
 └ 종료 → 표준입력 닫기 → 사이드카가 스스로 끝남   (기능별 .venv 가 없다 — osenv.module_cmd)
```

| 폴더·파일 | 내용 |
|---|---|
| `src-tauri/` | Rust 껍데기 — `src/main.rs`(사이드카·창·트레이·바깥 링크), `tauri.conf.json`, `icons/` |
| `src-tauri/tauri.dev.conf.json` | 개발 모드(`npm run dev`) 덧씌움 — 식별자 `.dev`, next dev 띄우기 |
| `splash/` | 서버가 뜰 때까지 보이는 시작 화면 (Tauri API 없음) |
| `sidecar/` | `univus-backend.spec`(PyInstaller) · `build.py` · `requirements.txt`(**저장소의 유일한 python venv** `sidecar/.venv` — 빌드·개발·테스트 공용) |
| `cli.py` | 개발용 명령줄 — 기능 모듈을 개발 데이터(또는 `--app` 앱 데이터)로 돌린다 |
| `.dev-data/` | (git 제외) 개발 모드 데이터 |

## 동작

- **데이터**: 설치 폴더(`%LOCALAPPDATA%\UnivUs`)가 아니라 `%LOCALAPPDATA%\kr.univus.desktop\data` / `~/Library/Application Support/kr.univus.desktop/data` 에 기능 폴더와 같은 모양으로
  (`<폴더>/F6_Eclass_agent/data` …, C0 `osenv.appdata`). **이 폴더가 원본이다** — 저장소의 `data/`·`state/` 는 쓰지 않는다. 서버 로그 `logs/backend.log`, Chromium `pw-browsers/`.
- **Chromium**: 첫 실행 때 백그라운드로 받는다(약 150MB, `logs/browsers.log`). 받는 동안 로그인·가져오기는 "내려받는 중"이라고 답한다.
- **보안**: 서버는 127.0.0.1 의 빈 포트에만 열리고, 앱 창이 가진 세션 쿠키가 없으면 모든 요청에 403 —
  같은 PC 의 다른 프로그램·브라우저 탭이 성적·일정·로그인 세션을 다루는 API 를 부를 수 없다. 대시보드에는 Tauri API 를 열지 않는다.
- **창 닫기 = 트레이로 숨기기** (예약 수집·마감 알림은 계속). 완전히 끝내려면 트레이 → 종료. 두 번 실행하면 떠 있는 창을 앞으로.
- **바깥 링크**(e클래스·학교 공지)는 기본 브라우저로, 강의자료 원문 등 로컬 주소는 앱 창으로.
- **학교 로그인**: 수집 원천 → e클래스 → `로그인 창 열기`(휴대폰 2차 인증 한 번) · `자동 로그인 정보 저장`(아이디·비밀번호를 DPAPI/키체인에 — 완전 무인).
- **예약 실행**: 대시보드 `켜기` 가 Windows 작업 스케줄러 / 맥 launchd 에 **앱 실행 파일**을 등록한다(`--run-module eclass tick` · `bachelor tick`).
  작업 이름 `UnivUs-F6-Eclass-Sync` · `UnivUs-F1-Academic-Sync`, launchd 라벨 `kr.univus.f6-eclass-sync` · `kr.univus.f1-academic-sync` — 바꾸면 기존 등록을 못 찾는다.

## 빌드 (설치 파일)

준비: Python 3.12 · Node 20+ · Rust(rustup) · Windows 는 Visual Studio C++ 빌드 도구 / 맥은 Xcode 명령줄 도구.

```bash
py -3.12 desktop/sidecar/build.py     # 화면 npm run build → sidecar/.venv 맞추기 → PyInstaller (맥: python3.12 …)
cd desktop
npm install
npx tauri build                       # → src-tauri/target/release/bundle/ (Windows nsis 설치 파일 약 46MB · 맥 .app/.dmg)
```

- `univ_us_local/frontend/out` 은 커밋하지 않는다 — `build.py` 가 매번 만든다(이미 만들었으면 `--skip-frontend`).
- `build.py` 는 마지막에 묶은 실행 파일로 `--self-check`(기능 폴더의 모든 모듈 import)를 돌린다 — PyInstaller 가 놓친 모듈은 그 기능을 쓸 때에야 터지므로(2026-10-08 `osenv.creds`) 실패하면 빌드도 실패한다.
  기능 코드(`osenv` 포함)는 PYZ 가 아니라 원본 `.py` 로 묶는다(`univus-backend.spec`).
- 설치본을 새로 깔기 전에 트레이 → 종료. 아이콘: `src-tauri/icons/source.png` 를 바꾸고 `npm run icon`.

## 개발 모드 (`npm run dev`)

설치본을 빌드하지 않고 소스 그대로 앱 창에서 돌린다. 화면(`univ_us_local/frontend/src`)을 고치면 창에 바로 반영되고,
백엔드·기능 코드(`.py`)를 고치면 `npm run dev` 를 다시 띄운다 (Rust `src-tauri/` 는 tauri dev 가 알아서 다시 빌드).

준비 (한 번):

```bash
py -3.12 -m venv desktop/sidecar/.venv                                          # 맥: python3.12 -m venv …
desktop/sidecar/.venv/Scripts/python -m pip install -r desktop/sidecar/requirements.txt   # 맥: …/.venv/bin/python
cd univ_us_local/frontend && npm ci && cd ../../desktop && npm install
```

```bash
cd desktop
npm run dev        # = tauri dev --config src-tauri/tauri.dev.conf.json
```

```
tauri dev ─ beforeDevCommand ─▶ next dev 127.0.0.1:3000 (univ_us_local/frontend, 즉시 반영)
   │                                   │ rewrites: /api · /desktop/launch · /study-calendar
   └ 디버그 빌드 창 ─ 실행 ─▶ desktop/sidecar/.venv python desktop.py --dev --port 8020 --frontend-url http://127.0.0.1:3000
                                         --data-root desktop/.dev-data
```

| | 설치본 | 개발 모드 |
|---|---|---|
| 식별자 | `kr.univus.desktop` | `kr.univus.desktop.dev` (`tauri.dev.conf.json`) — 설치본이 떠 있어도 따로 뜬다, WebView2 프로필도 따로 |
| 데이터 | `%LOCALAPPDATA%\kr.univus.desktop\data` | `desktop/.dev-data` (git 제외) |
| 화면 | 묶은 `frontend/out` | next dev (`:3000`) |
| 백엔드 | 사이드카 실행 파일, 빈 포트 | 저장소 소스(`desktop/sidecar/.venv`), 포트 `8020` 고정 (`next.config.ts` 의 `BACKEND_URL` 기본값과 같아야 한다) |
| 로그인 창·수집기 | 같은 실행 파일 `--run-module` | 같은 venv python `-m` |
| Chromium | 앱 데이터 폴더 `pw-browsers/` | `desktop/sidecar/.venv/pw-browsers` (첫 실행 때 받는다) |
| 서버 로그 | `logs/backend.log` | tauri dev 터미널 |
| 예약 실행 | 켜기/끄기 됨 | **꺼짐** (`--dev` → `F1_TASKS`·`F6_TASKS=off`) — 같은 작업 이름이라 설치본 등록을 덮어쓰지 않게 |

- **개발 데이터 채우기**: `.dev-data` 를 지운 뒤 `C0_Platform_agent` 에서 `python -m osenv copy-data --to ../desktop/.dev-data`
  (설치된 앱의 데이터를 복사, 덮어쓰지 않음). 비워 두면 첫 설정(온보딩) 화면부터 시작한다.
- **명령줄**: 개발 venv 를 켜고 저장소 루트에서 `python desktop/cli.py <패키지> …` — 예 `eclass sync --dry-run` · `bachelor list` · `login status`.
  `--app` 을 앞에 붙이면 설치된 앱의 데이터로 (앱이 떠 있으면 수집·쓰기는 피할 것). 패키지 목록은 `cli.py` 머리말.
- **테스트**: 기능 폴더마다 개발 venv 로 `python -m pytest tests -q` (C0 는 `python -m pytest C0_Platform_agent/tests -q`). CI(`.github/workflows/macos.yml`)도 같은 venv 로 돈다.
- 3000·8020 포트가 비어 있어야 한다. 묶은 사이드카를 dev 창으로 시험하려면 `UNIVUS_SIDECAR=<sidecar/dist/…/univus-backend(.exe)>` (이때는 데이터·포트가 설치본 규칙).
- 앱 창 밖 브라우저로 `http://127.0.0.1:3000` 을 열면 API 가 403 이다 (세션 쿠키는 앱 창만 가진다) — 정상.

**주의 (Windows, Claude 데스크톱 앱 안에서 작업할 때)**: Claude 앱은 MSIX 패키지라, 거기서 띄운 프로세스가 `%LOCALAPPDATA%` 에 새로 만드는 파일은
실제 위치가 아니라 `%LOCALAPPDATA%\Packages\Claude_…\LocalCache\Local\` 로 간다. 설치 파일 실행·`copy-data --from`(기본 위치)은 그 안에서 하지 말 것.
개발 모드 데이터는 저장소 안(`desktop/.dev-data`)이라 영향이 없다.

## 아직 안 한 것 (계획 문서 4단계)

- 코드 서명(Windows SmartScreen 경고 · 맥 공증) — 인증서·Apple 개발자 계정 필요
- 자동 업데이트(tauri-plugin-updater) — 서명 키·배포 위치(GitHub Releases) 결정 필요
- CI 에서 설치 파일 만들기 (지금 CI 는 맥에서 테스트 + 사이드카 빌드·실행까지)
