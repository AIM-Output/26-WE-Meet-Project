# 유니버스(Univ-Us) — 개발 안내

앱을 **쓰기만** 할 거면 이 문서는 필요 없습니다 → [README.md](README.md) 의 설치 파일을 받으세요.
여기는 코드를 고치고, 개발 모드로 돌리고, 설치 파일·릴리스를 만드는 사람을 위한 안내입니다.

유니버스는 **데스크톱 앱으로만** 실행합니다 (2026-10-08 — 예전의 브라우저로 여는 로컬 서버 웹·`유니버스 열기.cmd`·기능별 `setup.cmd`·`run.cmd`·`.venv` 는 없앴습니다).
Tauri 껍데기(`desktop/`)가 로컬 서버 사이드카(`univ_us_local/backend` + 기능 폴더를 PyInstaller 로 묶은 것)를 띄우고 창으로 대시보드를 엽니다.

```
저장소 폴더/
├── README.md                 사용 안내 (설치해서 쓰는 사람)
├── DEVELOPMENT.md            ← 지금 보는 문서
├── desktop/                  데스크톱 앱 (Tauri 껍데기 + 사이드카 빌드) · 개발 모드 · cli.py — desktop/README.md
├── univ_us_local/            앱 안의 대시보드 — backend(FastAPI, 사이드카가 된다) + frontend(Next.js)
├── C0_Platform_agent/        C0 OS 공통 계층(osenv) — Windows·macOS 차이 · 앱 데이터 폴더 · 자식 프로세스 명령
├── C1_Calendar_agent/        C1 서비스 캘린더 — 내 일정·할 일 저장 + /api/events (모든 기능이 일정을 여기로 모은다)
├── C2_Profile_agent/         C2 내 프로필·학과 목록 (F1·F2·F11 이 같이 씀)
├── C3_Login_agent/           C3 학교(SSO) 자동 로그인 — F6·C2·F2·F11 이 같이 씀 · 자동 로그인 정보(DPAPI/키체인)
├── F1_Bachelor_agent/        F1 학사일정 자동 등록·알림 (학교 공개 페이지 수집 — 로그인 불필요)
├── F2_Graduation_agent/      F2 졸업요건·학점 트래커
├── F3_Attendance_agent/      F3 출결·학사경고 예방
├── F4_Textbook_agent/        F4 강의자료 보관·열람
├── F5_Test_agent/            F5 시험 공부 일정
├── F6_Eclass_agent/          F6 e클래스 과제·마감·자료 수집 → 캘린더·할 일·마감 알림
├── F7_Task_agent/            F7 과제 우선순위
├── F8_Plan_agent/            F8 공강 학습 플랜
├── notice_agent/             (참고 코드) 장학 공지 매칭 — 나중에 앱 기능(F11)으로 옮길 때 참고
├── 요구사항정의서.md          기능별 요구사항 — 기능 개발 전 먼저 볼 문서
├── Frontend-Route.md         화면·라우트·흐름 정의
├── WE-Meet_데스크톱앱_맥지원_계획.md   데스크톱 앱 · macOS · 얇은 서버로 가는 단계별 계획과 진행 기록
├── Frontend-Figma.md · Frontend-Screens.md   디자인 팀 가이드 · 그릴 화면 목록
└── .github/workflows/        macos.yml(맥에서 테스트 + 사이드카 빌드) · release.yml(태그 → 설치 파일 → Releases 초안)
```

---

## 1. 프로그램 설치

| 프로그램 | Windows | macOS |
|---|---|---|
| Git | https://git-scm.com/download/win (기본값으로 설치) | `xcode-select --install` (Xcode 명령줄 도구 — Git·C 컴파일러가 같이 온다) |
| Python **3.12** | https://www.python.org/downloads/release/python-31210/ → "Windows installer (64-bit)" — 첫 화면 **Add python.exe to PATH** 체크, 끝 화면 **Disable path length limit** 클릭 | python.org 설치 후 `/Applications/Python 3.12/Install Certificates.command` 한 번 (또는 `brew install python@3.12`) |
| Node.js **20 이상** | https://nodejs.org (LTS) | 같음 (또는 `brew install node@20`) |
| Rust | https://rustup.rs → `rustup-init.exe` (기본값) | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| C++ 빌드 도구 | **Visual Studio Build Tools** — "C++를 사용한 데스크톱 개발" 워크로드 | Xcode 명령줄 도구 (위) |
| WebView2 | Windows 10/11 에 기본 포함 | 필요 없음 |

> 3.13·3.14 가 아니라 **3.12** 를 권장합니다 (검증된 버전). 다른 버전이 있어도 3.12 를 **추가로** 설치하면 됩니다.

확인 (설치 후 **창을 새로** 열고): `git --version` · `py -3.12 --version`(맥 `python3.12 --version`) · `node -v` · `cargo -V`

---

## 2. 저장소 가져오기

경로에 **한글·공백이 없고 짧은** 곳을 권장합니다 (`C:\Projects` · `~/Projects`). `OneDrive`·`바탕 화면`·`문서` 안은 피하세요.

```bash
git clone https://github.com/AIM-Output/26-WE-Meet-Project.git
cd 26-WE-Meet-Project
```

---

## 3. 개발 환경 (한 번)

python 가상환경은 **저장소에 하나**(`desktop/sidecar/.venv`)뿐입니다 — 앱 빌드·개발 모드·테스트·CI 가 같이 씁니다.

Windows (PowerShell, 프로젝트 폴더에서):

```powershell
py -3.12 -m venv desktop\sidecar\.venv
desktop\sidecar\.venv\Scripts\python -m pip install -r desktop\sidecar\requirements.txt
cd univ_us_local\frontend; npm ci; cd ..\..\desktop; npm install; cd ..
```

맥 (터미널, 프로젝트 폴더에서):

```bash
python3.12 -m venv desktop/sidecar/.venv
desktop/sidecar/.venv/bin/python -m pip install -r desktop/sidecar/requirements.txt
(cd univ_us_local/frontend && npm ci) && (cd desktop && npm install)
```

`git pull` 뒤 `requirements.txt`·`package-lock.json` 이 바뀌었으면 위 명령을 다시 실행합니다.

---

## 4. 개발 모드 (`npm run dev`)

```bash
cd desktop
npm run dev
```

- 처음엔 Rust 빌드로 **몇 분** 걸립니다. 앱 창(시작 화면 → 대시보드)이 뜨면 성공.
- 화면 코드(`univ_us_local/frontend/src`)를 고치면 창에 바로 반영됩니다. 파이썬 코드를 고쳤으면 `Ctrl+C` 후 `npm run dev` 다시.
- 개발 모드는 설치본과 **따로** 돕니다 — 데이터 `desktop/.dev-data`, 식별자 `kr.univus.desktop.dev`, 예약 자동 수집 꺼짐(설치본 예약을 덮어쓰지 않게).
- 첫 실행 때 브라우저 엔진(Chromium, 약 150MB)을 `desktop/sidecar/.venv/pw-browsers` 에 받습니다.
- 설치본 데이터로 개발하려면: `.dev-data` 를 지우고 `C0_Platform_agent` 에서 `python -m osenv copy-data --to ../desktop/.dev-data` (개발 venv python).

| 하고 싶은 것 | 방법 |
|---|---|
| 명령줄로 기능 돌려 보기 | 개발 venv 를 켜고(`desktop\sidecar\.venv\Scripts\activate` / `source desktop/sidecar/.venv/bin/activate`) 프로젝트 폴더에서 `python desktop/cli.py eclass sync --dry-run` · `bachelor list` · `login status` … (`--app` 을 앞에 붙이면 설치본 데이터) |
| 테스트 | 기능 폴더에서 개발 venv 로 `python -m pytest tests -q` (C0 는 `python -m pytest C0_Platform_agent/tests -q`) |
| 화면 타입 검사·린트 | `univ_us_local/frontend` 에서 `npx tsc --noEmit -p .` · `npx eslint src` |

자세한 동작(세션 쿠키·포트·데이터 폴더·앱 창 함정)은 [desktop/README.md](desktop/README.md).

---

## 5. 설치 파일 만들기 (내 PC 에서)

```bash
py -3.12 desktop/sidecar/build.py      # 화면 빌드 → 사이드카(PyInstaller) → --self-check (맥: desktop/sidecar/.venv/bin/python desktop/sidecar/build.py)
cd desktop
npx tauri build                        # Windows: src-tauri/target/release/bundle/nsis/UnivUs_*_x64-setup.exe · 맥: bundle/dmg/
```

설치본을 새로 깔기 전에 트레이 → **종료**. `frontend/out` 은 커밋하지 않습니다 — `build.py` 가 매번 만듭니다.

---

## 6. 릴리스 (팀원에게 배포)

팀원은 [Releases](https://github.com/AIM-Output/26-WE-Meet-Project/releases) 에서 설치 파일만 받아 씁니다. 설치 파일은 **CI 가 만듭니다** (`.github/workflows/release.yml`).

1. 버전 올리기 — 세 곳을 같은 값으로: `desktop/src-tauri/tauri.conf.json` 의 `version` · `desktop/package.json` 의 `version` · `desktop/src-tauri/Cargo.toml` 의 `version` (예: `0.2.0`)
2. main 에 머지된 상태에서 태그를 push:
   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. Actions 의 **Release** 가 Windows(`.exe`)·맥(`.dmg`) 설치 파일을 만들어 **초안(Draft)** 릴리스에 올립니다 (20~30분). 태그와 `tauri.conf.json` 버전이 다르면 실패합니다.
4. Releases 화면에서 초안을 열어 설명을 고치고 **Publish release** — 그때부터 README 의 "최신 버전 받기" 링크가 이 버전을 가리킵니다.

이미 있는 태그로 다시 만들려면 Actions → Release → **Run workflow** 에 태그를 넣습니다.
아직 없는 것: 코드 서명(Windows SmartScreen 경고 · 맥 공증 — 인증서·Apple 개발자 계정 필요), 자동 업데이트, 인텔 맥용.

---

## 7. 지키는 선 (보안·저작권)

| ❌ 금지 | 이유 |
|---|---|
| 앱 데이터 폴더·`desktop/.dev-data` 를 커밋·공유 (`git add -f` 포함) | 로그인 세션·암호화된 비밀번호·강의자료·성적이 들어 있음 (`.gitignore` 로 막혀 있음) |
| `C3_Login_agent/login/auth.py` 의 `ENTROPY`·설명 문자열 바꾸기 | 저장된 비밀번호를 풀 수 없게 된다 |
| `F6_Eclass_agent/eclass/config.py` 의 `REQUEST_INTERVAL`(1.5초) 줄이기 | e클래스 서버 부담 → 계정 차단 위험 |
| 대시보드(127.0.0.1)에 Tauri API(IPC) 열기 | 같은 PC 의 다른 프로그램이 성적·로그인 세션을 다룰 수 있게 된다 |

`git status` 에 `.dev-data/`, `.venv/`, `out/` 이 **보이지 않아야** 정상입니다.

---

## 8. 문제 해결 (개발)

**Q. `'py'은(는) … 인식되지 않습니다`** — Python 이 PATH 에 없습니다. 설치 파일 → `Modify` → **py launcher** · **Add Python to environment variables** 체크 후 창을 새로.

**Q. `pip install` 에서 `파일 이름이나 확장명이 너무 깁니다` (WinError 206)** — 경로가 너무 깁니다. **Disable path length limit** 을 누르거나 `C:\Projects` 처럼 짧은 경로로.

**Q. `npm run dev` 가 `cargo` 를 못 찾아요 / `link.exe not found`** — Rust 설치 후 창을 새로 열지 않았거나, Build Tools 의 **C++ 데스크톱 개발** 워크로드가 없습니다.

**Q. `개발 모드: …\desktop\sidecar\.venv\…python.exe 이(가) 없습니다`** — 3단계 venv 를 만들지 않았습니다.

**Q. `npm run dev` 가 3000 / 8020 포트를 못 쓴다고 해요** — 개발 모드가 이미 떠 있습니다. 끄고(`Ctrl+C`) 다시.

**Q. `build.py` 가 `self-check 실패` 로 끝나요** — PyInstaller 가 모듈을 빠뜨렸습니다. 메시지의 모듈을 `desktop/sidecar/univus-backend.spec` 에서 확인하세요 (기능 코드는 원본 `.py` 로 묶는다).

**Q. `git pull` 이 `Your local changes would be overwritten` 으로 실패해요** — 고친 게 없다면 `git stash` → `git pull` → `git stash pop`.

---

## 9. 문서

| 문서 | 내용 |
|---|---|
| [desktop/README.md](desktop/README.md) | 데스크톱 앱 동작·보안·**개발 모드**·빌드·`cli.py`·알아 둘 함정 |
| [univ_us_local/README.md](univ_us_local/README.md) | 대시보드 구조·API·화면 |
| [C0_Platform_agent/README.md](C0_Platform_agent/README.md) | OS 공통 계층(`osenv`) — 자식 프로세스 명령·Chromium 자리·자격증명(DPAPI/키체인)·예약 실행·앱 데이터 폴더 |
| [C1_Calendar_agent/README.md](C1_Calendar_agent/README.md) | 서비스 캘린더 — `/api/events` 합치기 규칙·내 일정·할 일 저장 |
| [C2_Profile_agent/README.md](C2_Profile_agent/README.md) | 내 프로필 저장 규칙·학과 목록(교육과정검색)·학사정보시스템 가져오기·API |
| [C3_Login_agent/README.md](C3_Login_agent/README.md) | 학교 SSO 자동 로그인 — 신뢰 기기·재인증 순서·자동 로그인 정보·다른 기능이 빌려 쓰는 법 |
| [F1_Bachelor_agent/README.md](F1_Bachelor_agent/README.md) | 학사일정 수집 원천·규칙·매일 08:00 자동 수집 |
| [F2_Graduation_agent/README.md](F2_Graduation_agent/README.md) | 졸업요건 계산 규칙·기본 룰셋과 근거·기이수성적 가져오기·API |
| [F3_Attendance_agent/README.md](F3_Attendance_agent/README.md) | 출결 계산 규칙·시간표 자동 가져오기·자동 휴강·API |
| [F4_Textbook_agent/README.md](F4_Textbook_agent/README.md) | 강의자료 보관 규칙·목록 만드는 규칙·직접 추가·원문 열기·API |
| [F5_Test_agent/README.md](F5_Test_agent/README.md) | 시험 공지 추출 규칙·역산 계산식·조정안·진도·재조정·API |
| [F6_Eclass_agent/README.md](F6_Eclass_agent/README.md) · [AUTOMATION.md](F6_Eclass_agent/AUTOMATION.md) | e클래스 수집기·과제 원장 규칙·마감 알림 · 예약 수집(정각 4시간마다·따라잡기·재시도) |
| [F7_Task_agent/README.md](F7_Task_agent/README.md) | 과제 우선순위 계산식·그룹 기준·오늘 남은 시간·API |
| [F8_Plan_agent/README.md](F8_Plan_agent/README.md) | 공강 배치 규칙·미배치 이유·고정·충돌·API |
| [WE-Meet_데스크톱앱_맥지원_계획.md](WE-Meet_데스크톱앱_맥지원_계획.md) | macOS 지원 → 데스크톱 앱 → 얇은 서버로 가는 단계별 계획과 진행 기록 |
| [WE-Meet_서버_플랫폼_검토.md](WE-Meet_서버_플랫폼_검토.md) | 왜 "내 PC 안에서만" 구조인지 (설계 배경) |
| [notice_agent/README.md](notice_agent/README.md) | (참고 코드) 장학 공지 매칭·신청서 초안 도구 |
