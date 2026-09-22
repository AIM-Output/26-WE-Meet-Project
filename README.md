# WE-Meet · 유니버스(Univ-Us) — 팀원 시작 가이드

전남대 e클래스에서 **내 과제·마감·강의자료를 자동으로 모아** 내 PC 안의 대시보드(캘린더·할 일)에 띄워 주는 프로젝트입니다.
모든 것이 **내 컴퓨터 안에서만** 돕니다. 비밀번호·강의자료·로그인 세션은 어디에도 올라가지 않습니다.

이 문서는 **처음 해 보는 사람** 이 순서대로 따라 하면 끝까지 되도록 썼습니다.
막히면 맨 아래 [9. 문제 해결](#9-문제-해결-faq) 을 먼저 보고, 그래도 안 되면 팀 채팅에 **오류 메시지 화면을 캡처해서** 올려 주세요.

```
저장소 폴더/
├── README.md                 ← 지금 보는 문서
├── eclass_agent/             e클래스 로그인 + 자료·마감 수집기 (Python)
├── univ_us_local/            대시보드 로컬 서버 웹 (FastAPI + Next.js 빌드 결과)
├── notice_agent/             (선택) 장학 공지 매칭 도구 — 이 가이드에서는 다루지 않음
├── 유니버스 열기.cmd          더블클릭 → 서버 켜고 브라우저로 대시보드 열기
├── 유니버스 종료.cmd          더블클릭 → 서버 끄기
└── WE-Meet_프로젝트계획서 …   기획 문서 (docx / pdf)
```

전체 흐름: **① 프로그램 설치 → ② clone → ③ 수집기 설치 → ④ e클래스 로그인 → ⑤ 수집 → ⑥ 대시보드 실행**
처음 한 번은 30분쯤(다운로드 포함), 다음부터는 더블클릭 한 번입니다.

---

## 0. 준비물

| 항목 | 내용 |
|---|---|
| PC | **Windows 10/11** (64비트). macOS·리눅스는 현재 지원하지 않음 (`.cmd` 런처와 Windows 암호화 API 사용) |
| 계정 | 전남대 포털 아이디/비밀번호 (e클래스 SSO 로그인에 쓰는 것) |
| 휴대폰 | 처음 로그인할 때 **2차 인증**을 받아야 함 |
| 인터넷 | 설치 중 약 **350MB** 내려받음 (Python 패키지 + 브라우저 엔진) |
| 디스크 | 여유 2GB 이상 |

---

## 1. 프로그램 설치 (Git, Python)

두 가지만 설치합니다. **이미 있으면 건너뛰세요** (아래 1-3 "확인" 으로 알 수 있음).

### 1-1. Git for Windows

1. https://git-scm.com/download/win → **"Click here to download"** (64-bit) 클릭
2. 설치 파일 실행 → 설정은 전부 **기본값 그대로 `Next`** → `Install`

### 1-2. Python 3.12

> ⚠️ 3.13·3.14 가 아니라 **3.12** 를 권장합니다 (검증된 버전). 다른 버전이 이미 있어도 3.12 를 **추가로** 설치하면 됩니다.

1. https://www.python.org/downloads/release/python-31210/ → 페이지 맨 아래 **"Windows installer (64-bit)"** 클릭
2. 설치 파일 실행 → 첫 화면 **맨 아래 체크박스를 켜고** `Install Now`
   - ✅ **Add python.exe to PATH** ← 꼭!
3. 설치가 끝난 화면에 **`Disable path length limit`** 버튼이 보이면 **꼭 눌러 주세요.** (경로가 긴 파일을 설치할 때 실패하는 것을 막아 줍니다.)

### 1-3. 확인

**PowerShell** 을 엽니다: `Windows 키` → `powershell` 입력 → Enter.
아래 두 줄을 한 줄씩 입력해 버전이 나오면 성공입니다.

```powershell
git --version
py -3.12 --version
```

- `git --version` → `git version 2.xx …`
- `py -3.12 --version` → `Python 3.12.x`

> `'py'은(는) … 인식되지 않습니다` 가 나오면 → Python 을 다시 설치하면서 **Add python.exe to PATH** 체크를 확인하세요. 설치 후에는 **PowerShell 창을 닫고 새로 여세요** (그래야 반영됨).

---

## 2. 폴더 만들고 저장소 가져오기 (clone)

### 2-1. 폴더 만들기

파일 탐색기에서 `C:\` 드라이브로 가서 새 폴더 **`Projects`** 를 만듭니다. (→ `C:\Projects`)

> 경로에 **한글·공백이 없고 짧은** 곳을 권장합니다. `OneDrive`·`바탕 화면`·`문서` 안은 클라우드 동기화 때문에 문제를 일으킬 수 있으니 피하세요.

### 2-2. 그 폴더에서 PowerShell 열기

탐색기로 `C:\Projects` 에 들어간 뒤, **위쪽 주소창을 클릭해 `powershell` 이라고 입력하고 Enter**.
→ 창이 뜨고 프롬프트에 `PS C:\Projects>` 가 보이면 됩니다.

### 2-3. clone

```powershell
git clone https://github.com/Khrrr0131/26-WE-Meet-Project.git
```

끝나면 `C:\Projects\26-WE-Meet-Project` 폴더가 생깁니다. 그 안으로 들어갑니다.

```powershell
cd 26-WE-Meet-Project
dir
```

`eclass_agent`, `univ_us_local`, `유니버스 열기.cmd` 등이 보이면 성공입니다.
**이 폴더를 이 문서에서 "프로젝트 폴더" 라고 부릅니다.**

---

## 3. e클래스 수집기 설치 (`eclass_agent`)

```powershell
cd eclass_agent
.\setup.cmd
```

`setup.cmd` 가 자동으로 ① 가상환경(`.venv`) 생성 → ② 패키지 설치 → ③ 브라우저 엔진(Chromium, 약 310MB) 다운로드를 합니다.
**3~10분** 걸립니다. `설치 완료.` 가 나오면 됩니다 (아무 키나 누르면 정리).

> 중간에 실패하면 인터넷을 확인하고 **`.\setup.cmd` 를 다시 실행**하세요. 이미 된 단계는 건너뜁니다.

---

## 4. e클래스 계정 등록 (로그인)

여기서 **내 전남대 계정으로 e클래스에 한 번 로그인**해서, 이후 수집기가 쓸 "로그인 상태(세션)" 를 내 PC 에 저장합니다.
비밀번호는 저장하지 않습니다. 브라우저 창에 **직접** 입력합니다.

```powershell
.\login.cmd
```

1. 크롬 같은 브라우저 창이 뜨고 e클래스 로그인 화면이 보입니다.
2. **[SSO 로그인]** 버튼 → 전남대 포털 **아이디/비밀번호** 입력 → 로그인
3. 휴대폰으로 **2차 인증** 요청이 옵니다 → 승인
   (이때 "이 기기를 신뢰" 같은 항목이 있으면 켜 두세요. 다음부터 2차 인증이 생략됩니다.)
4. e클래스 메인 화면까지 들어가지면 창이 **저절로 닫히고**, PowerShell 에 `세션 저장 완료` 가 나옵니다.
   - 창이 안 닫히면 → PowerShell 창을 클릭하고 **Enter**.
   - 최대 10분 안에 끝내야 합니다. 시간이 지나면 `.\login.cmd` 를 다시 실행하세요.

이제 `eclass_agent\state\` 안에 로그인 세션이 저장됐습니다. **이 폴더는 절대 남에게 보내지 마세요** (= 내 계정으로 로그인된 상태 그 자체입니다).

### (선택) 자동 재로그인 등록

로그인 세션은 몇 시간 지나면 만료됩니다. 그때마다 `login.cmd` 를 다시 하기 귀찮으면, 아이디/비밀번호를 **내 PC 에만, 내 Windows 계정으로 암호화해서** 저장해 두고 수집기가 알아서 재로그인하게 할 수 있습니다.

```powershell
.\setup-creds.cmd          # 아이디·비밀번호 입력 (비밀번호는 화면에 안 보임)
.\login.cmd --auto         # "성공. 세션 저장됨." 이 나오면 OK
```

- 저장 위치 `state\cred.bin` 은 Windows DPAPI 로 암호화되어 **내 Windows 계정에서만** 풀립니다. 파일을 복사해 가도 소용없습니다.
- 지우려면 `.\setup-creds.cmd --clear`.
- 학교 비밀번호를 바꾸면 `.\setup-creds.cmd` 를 다시 실행하세요.
- 몇 시간마다 자동 수집까지 하려면 → [eclass_agent/AUTOMATION.md](eclass_agent/AUTOMATION.md)

---

## 5. 크롤링 (자료·마감 수집)

먼저 **내려받지 않고 목록만** 확인해 봅니다.

```powershell
.\sync.cmd --dry-run
```

내 수강 과목과 자료 목록이 쭉 출력되면 로그인이 잘 된 것입니다. 이제 실제로 수집합니다.

```powershell
.\sync.cmd
```

- 처음엔 자료 양에 따라 **몇 분 ~ 십여 분** 걸립니다 (서버 부하를 줄이려고 요청 사이에 1.5초씩 쉽니다).
- 결과는 `eclass_agent\data\` 에 쌓입니다:

| 파일 | 내용 |
|---|---|
| `data\deadlines.md` | **마감 일정** (과제·동영상 시청 기한, 날짜순, 제출 여부) — 메모장으로 열어 보세요 |
| `data\<과목명>\과제\` | 과제 설명·첨부·마감 |
| `data\<과목명>\게시판\` | 공지·자료실 글 |
| `data\<과목명>\<활동>\` | 강의자료 파일 (pdf, pptx, hwp …) |

- 두 번째부터는 이미 받은 파일은 건너뛰므로 빠릅니다.
- 마감만 빨리 갱신: `.\sync.cmd --only deadlines`

> 수집하지 않는 것: 동영상 본체, 퀴즈·출석, 학생들이 글을 쓰는 게시판(Q&A·팀빌딩 등). 학교 저작권 안내를 지키기 위한 설계이므로 바꾸지 마세요.

---

## 6. 로컬 서버 웹(대시보드) 실행

파일 탐색기에서 **프로젝트 폴더**(예: `C:\Projects\26-WE-Meet-Project`) 로 가서

### **`유니버스 열기.cmd`** 를 더블클릭

- 처음엔 서버용 Python 패키지를 설치하느라 **1~2분** 걸립니다. `로컬 서버를 시작합니다...` 가 보이면 기다리세요.
- 준비되면 브라우저가 자동으로 **http://localhost:8000** 을 엽니다.
- 작업표시줄에 최소화된 **"Univ-Us Local Server"** 창이 하나 생깁니다. **이 창을 닫으면 서버가 꺼집니다.** 그냥 두세요.

화면 구성:

| 위치 | 내용 |
|---|---|
| 가운데 캘린더 | e클래스 마감(과목별 색) + 내 일정 + 할 일. 날짜 클릭/드래그로 새 일정 추가, 드래그로 이동 |
| 왼쪽 | 일정·할 일 추가 버튼, **"e클래스 동기화"** 버튼(= `sync.cmd` 를 대신 실행), 월별 완료율 |
| 오른쪽 | 할 일 목록 (미제출 과제 = 할 일, 제출 완료 = 완료). D-day 표시 |
| 상단 | 마지막 동기화 시각 |

캘린더에 과제가 안 보이면 → 5단계 수집이 끝났는지, `eclass_agent\data\deadlines.json` 이 있는지 확인하세요. 왼쪽 **"e클래스 동기화"** 버튼을 눌러도 됩니다.

### 끄기

**`유니버스 종료.cmd`** 더블클릭 (또는 최소화된 "Univ-Us Local Server" 창 닫기).

---

## 7. 다음부터 쓸 때

| 하고 싶은 것 | 방법 |
|---|---|
| 대시보드 열기 | `유니버스 열기.cmd` 더블클릭 |
| e클래스 최신 자료·마감 가져오기 | 대시보드 왼쪽 **e클래스 동기화** 버튼, 또는 PowerShell 에서 `eclass_agent` 폴더 → `.\sync.cmd` |
| "세션 만료" 라고 나올 때 | `eclass_agent` 폴더에서 `.\login.cmd` 다시 (4단계). 자동 재로그인을 등록했다면 저절로 됨 |
| 끄기 | `유니버스 종료.cmd` |
| 팀 저장소의 새 버전 받기 | 프로젝트 폴더에서 PowerShell → `git pull` → 대시보드 껐다 켜기 |

바탕 화면에 바로가기를 두고 싶으면 `유니버스 열기.cmd` 에서 우클릭 → **보내기 → 바탕 화면에 바로 가기 만들기**.

---

## 8. 절대 하지 말 것 (보안·저작권)

| ❌ 금지 | 이유 |
|---|---|
| `eclass_agent\state\` 폴더를 복사·공유·업로드 | **내 계정으로 로그인된 상태**(세션 쿠키, 암호화된 비밀번호)가 들어 있음 |
| `eclass_agent\data\` 를 남에게 전송·클라우드·깃허브 업로드 | 학교 강의자료 — 학교 저작권 안내상 **타인 배포·인터넷 게시 금지** |
| `git add -f` / `.gitignore` 수정으로 위 폴더를 커밋 | 위와 같음. 두 폴더는 이미 `.gitignore` 로 막혀 있음 |
| 팀원 PC 에서 내 계정으로 `login.cmd` | 계정정보 공유 = 학교 금지 사항 |
| `config.py` 의 `REQUEST_INTERVAL` 을 줄이기 | e클래스 서버에 부담 → 계정 차단 위험 |

`git status` 를 쳤을 때 `state/`, `data/`, `.venv/` 가 **보이지 않아야** 정상입니다.

---

## 9. 문제 해결 (FAQ)

**Q. `'py'은(는) 내부 또는 외부 명령… 인식되지 않습니다`**
Python 이 PATH 에 없습니다. Python 설치 파일을 다시 실행 → `Modify` → 다음 화면에서 **py launcher** 와 **Add Python to environment variables** 체크. 끝나면 PowerShell 을 **새로** 여세요.

**Q. `python` 을 치면 Microsoft Store 가 열려요**
Windows 의 가짜 python 별칭입니다. 이 프로젝트는 `py` 와 `.venv` 안의 python 만 쓰므로 무시해도 되지만, 거슬리면 `설정 → 앱 → 고급 앱 설정 → 앱 실행 별칭` 에서 `python.exe`, `python3.exe` 를 끄세요.

**Q. `setup.cmd` 에서 `파일 이름이나 확장명이 너무 깁니다` (WinError 206)**
프로젝트 폴더 경로가 너무 깁니다. 1-2 의 **`Disable path length limit`** 을 누르지 않았거나, 폴더가 너무 깊은 곳에 있습니다. `C:\Projects` 처럼 짧은 경로로 옮긴 뒤 `.\setup.cmd` 다시.

**Q. `setup.cmd` 에서 브라우저 다운로드가 실패해요**
인터넷(특히 학교 와이파이 방화벽)을 확인하고 다시 `.\setup.cmd`. 프록시 환경이면 휴대폰 핫스팟으로 시도.

**Q. `login.cmd` 를 실행했는데 `Executable doesn't exist … playwright install` 이 나와요**
브라우저 엔진이 없습니다. `.\setup.cmd` 를 다시 실행하세요. (전역 `python login.py` 로 실행하면 이 오류가 납니다 — **항상 `.cmd` 파일로** 실행하세요.)

**Q. 로그인 창이 떴는데 10분 안에 못 끝냈어요 / 창을 실수로 닫았어요**
`.\login.cmd` 를 다시 실행하면 됩니다.

**Q. `sync.cmd` 가 `세션이 만료` / `exit 2` 로 멈춰요**
로그인 세션이 끝난 것입니다. `.\login.cmd` 다시 (4단계).

**Q. `sync.cmd` 가 `이미 실행 중` 이라고 해요**
대시보드의 동기화 버튼이나 이전 실행이 아직 돌고 있습니다. 끝날 때까지 기다리세요. 정말 아무것도 안 도는데 계속 그러면 `eclass_agent\state\sync.lock` 파일을 지우세요.

**Q. `유니버스 열기.cmd` 가 `서버가 90초 안에 응답하지 않았습니다`**
최소화된 **"Univ-Us Local Server"** 창을 열어 빨간 오류를 보세요.
- `No Python 3.12 found` / `'py'은(는) …` → 1-2 단계 Python 설치
- `Address already in use` / 8000 포트 → `유니버스 종료.cmd` 실행 후 다시
- 그 외 → 창 내용을 캡처해서 팀 채팅에

**Q. 대시보드는 열리는데 캘린더가 비어 있어요**
`eclass_agent\data\deadlines.json` 이 있는지 확인. 없으면 5단계 `.\sync.cmd`. 있으면 페이지 새로고침(F5).

**Q. 한글이 `?????` 나 깨진 글자로 보여요**
`.cmd` 파일들은 한국어 Windows 기준입니다. 시스템 표시 언어가 한국어인지 확인하고, PowerShell 대신 **Windows Terminal**(Microsoft Store, 무료) 로 실행해 보세요.

**Q. `git pull` 이 `Your local changes would be overwritten` 으로 실패해요**
내가 파일을 고쳐서 충돌합니다. 고친 게 없다면 `git stash` → `git pull` → `git stash pop`. 잘 모르겠으면 팀 채팅에 문의.

**Q. 다른 PC 에서도 쓰고 싶어요**
그 PC 에서 이 가이드를 처음부터 다시 하면 됩니다 (로그인·2차 인증도 다시). `state\`·`data\` 를 복사해 가지 마세요.

---

## 10. 더 알아보기

| 문서 | 내용 |
|---|---|
| [eclass_agent/README.md](eclass_agent/README.md) | 수집기 옵션(`--course`, `--only deadlines`), 결과 파일 구조, 지키는 선 |
| [eclass_agent/AUTOMATION.md](eclass_agent/AUTOMATION.md) | 작업 스케줄러로 몇 시간마다 자동 수집 |
| [univ_us_local/README.md](univ_us_local/README.md) | 대시보드 구조·API·개발 모드 |
| [notice_agent/README.md](notice_agent/README.md) | (선택) 장학 공지 매칭·신청서 초안 도구 |
| [WE-Meet_서버_플랫폼_검토.md](WE-Meet_서버_플랫폼_검토.md) | 왜 "개인 로컬 서버" 구조인지 (설계 배경) |

### 개발자용: 프론트엔드(화면) 수정하기

화면 코드는 `univ_us_local/frontend/src/` 에 있고 **Node.js 20 이상**이 필요합니다. 그냥 쓰기만 할 땐 필요 없습니다 (빌드 결과 `frontend/out/` 이 저장소에 들어 있음).

```powershell
cd univ_us_local\frontend
npm install                 # 최초 1회
npm run dev                 # http://localhost:3000 (핫리로드; 백엔드 8000 은 유니버스 열기.cmd 로 켜 둘 것)
npm run build               # 수정이 끝나면 out/ 을 다시 만들어 함께 커밋 → 팀원은 Node 없이 반영됨
```
