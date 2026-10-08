# WE-Meet · 유니버스(Univ-Us) — 팀원 시작 가이드

전남대 e클래스에서 **내 과제·마감·강의자료를 자동으로 모아** 내 PC 의 **데스크톱 앱**(캘린더·할 일·학사일정·졸업요건·출결·시험 공부)에 띄워 주는 프로젝트입니다.
모든 것이 **내 컴퓨터 안에서만** 돕니다. 비밀번호·강의자료·로그인 세션은 어디에도 올라가지 않습니다.

> 2026-10-08 부터 **데스크톱 앱으로만** 실행합니다. 예전의 `유니버스 열기.cmd`(브라우저로 여는 로컬 서버 웹)·기능별 `setup.cmd`·`run.cmd`·`.venv` 는 없앴습니다.
> 아직 배포하는 설치 파일이 없어서, 팀원은 이 가이드대로 **직접 빌드하거나 개발 모드로** 실행합니다.

막히면 [8. 문제 해결](#8-문제-해결-faq) 을 먼저 보고, 그래도 안 되면 팀 채팅에 **오류 메시지 화면을 캡처해서** 올려 주세요.

```
저장소 폴더/
├── README.md                 ← 지금 보는 문서
├── desktop/                  데스크톱 앱 (Tauri 껍데기 + 로컬 서버를 묶은 사이드카) · 개발 모드 · cli.py — desktop/README.md
├── univ_us_local/            앱 안의 대시보드 — backend(FastAPI, 사이드카가 된다) + frontend(Next.js)
├── C0_Platform_agent/        C0 OS 공통 계층(osenv) — Windows·macOS 차이 · 앱 데이터 폴더 · 자식 프로세스 명령
├── C1_Calendar_agent/        C1 서비스 캘린더 — 내 일정·할 일 저장 + /api/events (모든 기능이 일정을 여기로 모은다)
├── C2_Profile_agent/         C2 내 프로필·학과 목록 (F1·F2·F11 이 같이 씀)
├── C3_Login_agent/           C3 학교(SSO) 자동 로그인 — F6·C2·F2·F11 이 같이 씀 · 자동 로그인 정보(DPAPI/키체인)
├── F1_Bachelor_agent/        F1 학사일정 자동 등록·알림 (학교 공개 페이지 수집 — 로그인 불필요)
├── F2_Graduation_agent/      F2 졸업요건·학점 트래커 (학사시스템 이수 내역 → 영역별 남은 학점)
├── F3_Attendance_agent/      F3 출결·학사경고 예방 (공개 시간표 → 수업 회차·결석 한도 경고)
├── F4_Textbook_agent/        F4 강의자료 보관·열람 (F6 가 받은 자료를 과목별로 열기)
├── F5_Test_agent/            F5 시험 공부 일정 (공지에서 시험 찾고 분량을 날짜로 역산 → 학습 블록)
├── F6_Eclass_agent/          F6 e클래스 과제·마감·자료 수집 → 캘린더·할 일·마감 알림
├── F7_Task_agent/            F7 과제 우선순위 (마감 + 예상 소요시간 → 지금 해야 함/이번 주/나중에)
├── F8_Plan_agent/            F8 공강 학습 플랜 (낮 09~18시 공강에 과제·할 일 → 남는 공강은 시험 공부)
├── notice_agent/             (참고 코드) 장학 공지 매칭 — 나중에 앱 기능(F11)으로 옮길 때 참고. 이 가이드에서는 다루지 않음
├── 요구사항정의서.md          기능별 요구사항 (무엇을 만드는가) — 기능 개발 전 먼저 볼 문서
├── Frontend-Route.md         화면·라우트·흐름 정의
├── WE-Meet_데스크톱앱_맥지원_계획.md   데스크톱 앱 · macOS · 얇은 서버로 가는 단계별 계획
├── Frontend-Figma.md · Frontend-Screens.md   디자인 팀 가이드 · 그릴 화면 목록
└── WE-Meet_프로젝트계획서 …   기획 문서 (docx / pdf)
```

전체 흐름: **① 프로그램 설치 → ② clone → ③ 개발 환경 한 번 → ④ 앱 실행 → ⑤ 앱 안에서 첫 설정·로그인·수집**
처음 한 번은 40분쯤(Rust·패키지·첫 빌드 포함), 다음부터는 명령 한 줄(또는 설치한 앱 아이콘)입니다.

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

확인 (PowerShell / 터미널, 설치 후 **창을 새로** 열고):

```bash
git --version
py -3.12 --version
node -v
cargo -V
```

맥은 `py -3.12` 대신 `python3.12 --version`.

---

## 2. 저장소 가져오기 (clone)

경로에 **한글·공백이 없고 짧은** 곳을 권장합니다 (`C:\Projects` · `~/Projects`). `OneDrive`·`바탕 화면`·`문서` 안은 피하세요.

```bash
git clone https://github.com/AIM-Output/26-WE-Meet-Project.git
cd 26-WE-Meet-Project
```

이 폴더를 이 문서에서 **"프로젝트 폴더"** 라고 부릅니다.

---

## 3. 개발 환경 (한 번)

python 가상환경은 **저장소에 하나**(`desktop/sidecar/.venv`)뿐입니다 — 앱 빌드·개발 모드·테스트가 같이 씁니다.

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

---

## 4. 앱 실행

### 4-1. 개발 모드 (코드를 고칠 때 — 권장)

```bash
cd desktop
npm run dev
```

- 처음엔 Rust 빌드로 **몇 분** 걸립니다. 앱 창(시작 화면 → 대시보드)이 뜨면 성공.
- 화면 코드(`univ_us_local/frontend/src`)를 고치면 창에 바로 반영됩니다. 파이썬 코드를 고쳤으면 `Ctrl+C` 후 `npm run dev` 다시.
- 개발 모드 데이터는 `desktop/.dev-data` 에 따로 있습니다(설치본 데이터와 섞이지 않음). 예약 자동 수집은 개발 모드에서 꺼져 있습니다.
- 첫 실행 때 브라우저 엔진(Chromium, 약 150MB)을 백그라운드로 받습니다. 받는 동안 로그인·가져오기는 "내려받는 중"이라고 답합니다.

### 4-2. 설치본 (매일 쓰기 — 예약 자동 수집·알림)

```bash
py -3.12 desktop/sidecar/build.py      # 화면 빌드 → 사이드카 빌드 (맥: desktop/sidecar/.venv/bin/python desktop/sidecar/build.py)
cd desktop
npx tauri build
```

→ `desktop/src-tauri/target/release/bundle/nsis/UnivUs_*_x64-setup.exe` (맥은 `bundle/dmg/`) 를 실행해 설치합니다. 시작 메뉴 / 응용 프로그램의 **UnivUs** 로 엽니다.

- 창을 닫으면 **트레이로 숨습니다**(예약 수집·마감 알림 계속). 완전히 끄려면 트레이 아이콘 → **종료**. 새 버전을 설치하기 전에도 종료.
- Windows 에서 "PC 보호" 경고가 뜨면 **추가 정보 → 실행** (코드 서명 전이라 뜨는 경고). 맥은 앱을 **우클릭 → 열기** 한 번.

---

## 5. 앱 안에서 첫 설정

| 순서 | 어디서 | 무엇을 |
|---|---|---|
| 1 | 처음 열면 나오는 **첫 설정** | 학과 → 입학년도·이수유형 → (선택) 학사정보시스템에서 가져오기 |
| 2 | ⚙ → **수집 원천 → e클래스 → `로그인 창 열기`** | 브라우저 창에서 [SSO 로그인] → 포털 아이디/비밀번호 → **휴대폰 2차 인증** 승인 ("이 기기를 신뢰" 가 있으면 켜기). e클래스 메인까지 들어가면 창이 저절로 닫히고 바로 수집합니다 |
| 3 | 같은 줄 **`자동 로그인 정보 저장`** (선택) | 아이디·비밀번호를 **이 PC 에만 암호화해** 저장 → 세션이 만료돼도 창 없이 다시 로그인 (Windows: 이 Windows 계정에서만 풀림 / 맥: 로그인 키체인) |
| 4 | e클래스 · 학사일정 줄의 **예약 실행 `켜기`** (설치본에서) | e클래스는 정각 4시간마다, 학사일정은 매일 08:00 — 창 없이 자동 수집. PC 가 꺼져 있었으면 켜지는 대로 따라잡기 |

첫 수집은 자료 양에 따라 **몇 분 ~ 십여 분** 걸립니다(서버 부하를 줄이려고 요청 사이에 1.5초씩 쉽니다). 두 번째부터는 이미 받은 파일을 건너뛰어 빠릅니다.

> 수집하지 않는 것: 동영상 본체, 퀴즈 문제(마감 일시만)·출석, 학생들이 글을 쓰는 게시판(Q&A·팀빌딩 등). 학교 저작권 안내를 지키기 위한 설계이므로 바꾸지 마세요.

### 화면

| 메뉴 | 기능 | 데이터 |
|---|---|---|
| 대시보드 | 브리핑 · 캘린더(e클래스 마감·내 일정·할 일·학사·수업·공강 블록) · 먼저 할 것(F7) · 할 일 · 기능 타일 | ✅ 실제 |
| 학사일정 | F1 학교 학사일정·학사공지 → 캘린더 자동 등록, 확인 필요 일정 | ✅ 실제 (로그인 불필요) |
| E클래스 | F6 과제·동영상 마감(내가 체크함·소요시간) + 공지·자료 새 글 · F7 우선순위 | ✅ 실제 |
| 졸업요건 | F2 영역별 이수·남은 학점 (학사정보시스템 기이수성적 가져오기) | ✅ 실제 |
| 출결 | F3 시간표 → 수업 회차, 결석 한도·학사경고 예방, 휴강 자동 반영 | ✅ 실제 |
| 강의자료 | F4 받은 자료를 과목·주차별로 열기 | ✅ 목록·열람 / 요약·문제·질문은 예시 |
| 시험·발표 | F5 공지에서 시험 찾기 → 분량을 날짜로 역산한 학습 블록·공부 체크·날마다 공부 시간 | ✅ 실제 |
| 기회 · 팀플 · 브리핑 · 대화 | F11~13 · F16 · F10 · F9 | 🚧 예시 데이터 (화면만) |
| 설정 | 내 프로필(C2) · 수집 원천(로그인·자동 로그인 정보·예약 실행) · 졸업요건 기준 · 가용 시간(F8) · 알림 | ✅ 실제 (장학 F11 줄만 예시) |

화면에 **"예시 데이터"** 띠가 보이면 아직 실제 데이터가 연결되지 않은 화면입니다.

---

## 6. 다음부터 쓸 때

| 하고 싶은 것 | 방법 |
|---|---|
| 앱 열기 | 설치본: 시작 메뉴 **UnivUs** (트레이에 있으면 아이콘 클릭) · 개발: `desktop` 에서 `npm run dev` |
| e클래스 최신 자료·마감 | 대시보드 **e클래스 동기화** 또는 수집 원천 **지금 수집** (예약 실행을 켰으면 저절로) |
| "로그인이 필요합니다" | **로그인 창 열기** — 자동 로그인 정보를 저장했다면 대부분 저절로 됨 |
| 팀 저장소의 새 버전 | `git pull` → (requirements·package.json 이 바뀌었으면 3단계 명령 다시) → 개발 모드 다시 띄우기 또는 설치본 다시 빌드 |
| 명령줄로 기능 돌려 보기 | 개발 venv 를 켜고(`desktop\sidecar\.venv\Scripts\activate` / `source desktop/sidecar/.venv/bin/activate`) 프로젝트 폴더에서 `python desktop/cli.py eclass sync --dry-run` · `bachelor list` · `login status` … (개발 데이터 대상, `--app` 을 앞에 붙이면 설치본 데이터) |
| 테스트 | 기능 폴더에서 개발 venv 로 `python -m pytest tests -q` |

---

## 7. 데이터 위치 · 절대 하지 말 것 (보안·저작권)

| 데이터 | 위치 |
|---|---|
| 설치본 (원본) | Windows `%LOCALAPPDATA%\kr.univus.desktop\data` · 맥 `~/Library/Application Support/kr.univus.desktop/data` — 기능 폴더와 같은 모양(`F6_Eclass_agent/data` …) |
| 개발 모드 | 프로젝트 폴더의 `desktop/.dev-data` (git 제외) — 설치본 데이터를 복사해 쓰려면 `C0_Platform_agent` 에서 `python -m osenv copy-data --to ../desktop/.dev-data` |

| ❌ 금지 | 이유 |
|---|---|
| 데이터 폴더의 `C3_Login_agent/state/` 를 복사·공유·업로드 | **내 계정으로 로그인된 상태**(세션 쿠키, 암호화된 비밀번호)가 들어 있음 |
| `F6_Eclass_agent/data/` · `F4_Textbook_agent/data/` 를 남에게 전송·클라우드·깃허브 업로드 | 학교 강의자료 — 학교 저작권 안내상 **타인 배포·인터넷 게시 금지** |
| 다른 기능의 `data/` (`C1`·`C2`·`F1`~`F8`) 공유 | 내 일정·프로필·**성적(이수 내역)**·출결·시험 계획 = 개인정보 |
| `desktop/.dev-data` 를 `git add -f` 로 커밋 | 위와 같음 (`.gitignore` 로 막혀 있음) |
| 팀원 PC 에서 내 계정으로 로그인 | 계정정보 공유 = 학교 금지 사항 |
| `F6_Eclass_agent/eclass/config.py` 의 `REQUEST_INTERVAL` 을 줄이기 | e클래스 서버에 부담 → 계정 차단 위험 |

`git status` 를 쳤을 때 `.dev-data/`, `.venv/`, `out/` 이 **보이지 않아야** 정상입니다.

---

## 8. 문제 해결 (FAQ)

**Q. `'py'은(는) 내부 또는 외부 명령… 인식되지 않습니다`**
Python 이 PATH 에 없습니다. Python 설치 파일을 다시 실행 → `Modify` → **py launcher** 와 **Add Python to environment variables** 체크. 끝나면 PowerShell 을 **새로** 여세요.

**Q. `pip install` 에서 `파일 이름이나 확장명이 너무 깁니다` (WinError 206)**
경로가 너무 깁니다. 1단계의 **Disable path length limit** 을 누르지 않았거나 폴더가 너무 깊습니다. `C:\Projects` 처럼 짧은 경로로 옮긴 뒤 3단계 다시.

**Q. `npm run dev` 가 `cargo` 를 못 찾아요 / `link.exe not found`**
Rust 를 설치한 뒤 창을 새로 열지 않았거나(PATH), Visual Studio Build Tools 의 **C++ 데스크톱 개발** 워크로드가 없습니다.

**Q. `npm run dev` 에서 `개발 모드: …\desktop\sidecar\.venv\…python.exe 이(가) 없습니다`**
3단계의 venv 를 만들지 않았습니다.

**Q. `npm run dev` 가 3000 / 8020 포트를 쓸 수 없다고 해요**
개발 모드가 이미 떠 있거나 다른 프로그램이 그 포트를 씁니다. 떠 있는 개발 모드를 끄고(`Ctrl+C`) 다시.

**Q. 로그인 창이 떴는데 10분 안에 못 끝냈어요 / 창을 실수로 닫았어요**
**로그인 창 열기** 를 다시 누르면 됩니다.

**Q. 수집이 `로그인 필요` 로 멈춰요**
세션이 끝났고 자동 재로그인도 안 된 것입니다. **로그인 창 열기** (휴대폰 인증 한 번). 자동 로그인 정보를 저장해 두면 대부분 생기지 않습니다.

**Q. 수집이 `네트워크 오류` 로 멈춰요**
예약 실행이면 5·15·45분 뒤 스스로 다시 시도합니다. 직접 돌렸다면 연결(학교 와이파이 방화벽 등)을 확인하고 다시.

**Q. 앱 창이 시작 화면에서 "로컬 서버가 멈췄습니다" 로 멈춰요**
트레이 → 종료 후 다시 실행. 그래도 같으면 데이터 폴더의 `logs/backend.log` 를 캡처해서 팀 채팅에.

**Q. `git pull` 이 `Your local changes would be overwritten` 으로 실패해요**
내가 파일을 고쳐서 충돌합니다. 고친 게 없다면 `git stash` → `git pull` → `git stash pop`. 잘 모르겠으면 팀 채팅에 문의.

**Q. 다른 PC 에서도 쓰고 싶어요**
그 PC 에서 이 가이드를 처음부터 다시 하면 됩니다 (로그인·2차 인증도 다시). 데이터 폴더를 복사해 가지 마세요 — 저장한 비밀번호는 그 PC·계정에서만 풀립니다.

---

## 9. 더 알아보기

| 문서 | 내용 |
|---|---|
| [desktop/README.md](desktop/README.md) | 데스크톱 앱 동작·보안·**개발 모드**·빌드·`cli.py`·아직 안 한 것 |
| [univ_us_local/README.md](univ_us_local/README.md) | 대시보드 구조·API·화면 |
| [C0_Platform_agent/README.md](C0_Platform_agent/README.md) | OS 공통 계층(`osenv`) — 자식 프로세스 명령·Chromium 자리·자격증명(DPAPI/키체인)·예약 실행(작업 스케줄러/launchd)·앱 데이터 폴더 |
| [C1_Calendar_agent/README.md](C1_Calendar_agent/README.md) | 서비스 캘린더 — `/api/events` 합치기 규칙·내 일정·할 일 저장 |
| [C2_Profile_agent/README.md](C2_Profile_agent/README.md) | 내 프로필 저장 규칙·학과 목록(교육과정검색)·학사정보시스템 가져오기·API |
| [C3_Login_agent/README.md](C3_Login_agent/README.md) | 학교 SSO 자동 로그인 — 신뢰 기기·재인증 순서·자동 로그인 정보·다른 기능이 빌려 쓰는 법 |
| [F1_Bachelor_agent/README.md](F1_Bachelor_agent/README.md) | 학사일정 수집 원천·규칙·매일 08:00 자동 수집 |
| [F2_Graduation_agent/README.md](F2_Graduation_agent/README.md) | 졸업요건 계산 규칙·기본 룰셋과 근거·기이수성적 가져오기·API |
| [F3_Attendance_agent/README.md](F3_Attendance_agent/README.md) | 출결 계산 규칙(날짜(회) 단위·1/4 한도·경고 단계)·시간표 자동 가져오기·자동 휴강·API |
| [F4_Textbook_agent/README.md](F4_Textbook_agent/README.md) | 강의자료 보관 규칙(하드링크·복사)·목록 만드는 규칙·직접 추가·원문 열기·API |
| [F5_Test_agent/README.md](F5_Test_agent/README.md) | 시험 공지 추출 규칙·역산 계산식·상한 초과 조정안·진도·재조정·API |
| [F6_Eclass_agent/README.md](F6_Eclass_agent/README.md) | e클래스 수집기 옵션, 결과 파일·과제 원장 규칙, 마감 알림, 지키는 선 |
| [F6_Eclass_agent/AUTOMATION.md](F6_Eclass_agent/AUTOMATION.md) | 예약 수집 — 정각 4시간마다 · 놓친 주기 따라잡기 · 네트워크 재시도 |
| [F7_Task_agent/README.md](F7_Task_agent/README.md) | 과제 우선순위 계산식·그룹 기준·이유 한 줄·오늘 남은 시간·설정·API |
| [F8_Plan_agent/README.md](F8_Plan_agent/README.md) | 공강 배치 규칙·미배치 이유·고정·충돌·API |
| [WE-Meet_데스크톱앱_맥지원_계획.md](WE-Meet_데스크톱앱_맥지원_계획.md) | macOS 지원 → 데스크톱 앱 → 얇은 서버로 가는 단계별 계획과 진행 기록 |
| [WE-Meet_서버_플랫폼_검토.md](WE-Meet_서버_플랫폼_검토.md) | 왜 "내 PC 안에서만" 구조인지 (설계 배경 — 2026-09 시점의 로컬 서버 웹 기록 포함) |
| [notice_agent/README.md](notice_agent/README.md) | (참고 코드) 장학 공지 매칭·신청서 초안 도구 |
