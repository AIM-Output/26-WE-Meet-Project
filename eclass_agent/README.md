# eclass_agent

전남대 e클래스(`sel.jnu.ac.kr`)에서 **본인 수강 과목의 문서 자료만** 내려받아
개인 에이전트가 읽을 수 있게 정리하는 도구.

## 설치 (최초 1회)

```powershell
cd <프로젝트 폴더>\eclass_agent
.\setup.cmd          # .venv 생성 + 패키지 설치 + Chromium 을 .venv\pw-browsers 에 내려받음
```

`setup.cmd` 가 하는 일을 손으로 하려면:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:PLAYWRIGHT_BROWSERS_PATH = "$PWD\.venv\pw-browsers"
.\.venv\Scripts\python.exe -m playwright install chromium
```

브라우저는 기본 위치(`%LOCALAPPDATA%\ms-playwright`)가 아니라 **이 폴더의 `.venv\pw-browsers`** 에 둔다.
`.cmd` 런처가 `PLAYWRIGHT_BROWSERS_PATH` 를 그쪽으로 잡아주므로, 런처로 실행하면 신경 쓸 것 없다.

## 사용

`.cmd` 런처는 항상 이 폴더의 `.venv` Python 을 쓴다. (전역 `python` 으로 실행하면
playwright 가 없거나 브라우저 버전이 달라 "playwright install" 에러가 난다.)

```powershell
.\login.cmd            # 창이 뜨면 [SSO 로그인]으로 직접 로그인 → 세션 저장
.\sync.cmd --dry-run   # 내려받지 않고 과목·자료 목록만 확인
.\sync.cmd             # 자료 수집 (이미 받은 파일은 건너뜀)
```

세션이 만료되면 `sync` 가 재인증을 시도하고, 안 되면 멈추고 안내한다 → `.\login.cmd` 다시.

`sync` 는 도는 동안 `state\sync.lock`(pid) 을 잡는다. 예약 작업·대시보드 버튼·수동 실행이 겹치면 뒤의 것이
"이미 실행 중" 을 남기고 **exit 3** 으로 물러난다 (죽은 프로세스가 남긴 잠금은 알아서 치운다). 끝나면
`state\sync.last.json` 에 시작·종료 시각과 종료 코드를 남긴다. `run-sync.cmd` 는 `--log state\sync.log` 로 출력을
줄 단위로 덧붙인다 (종료 코드: 0 성공 · 1 오류 · 2 세션 만료 · 3 다른 실행이 진행 중).

**백그라운드 자동화**(최초 1회 로그인 후 주기적 무인 수집 + 작업 스케줄러)는 [AUTOMATION.md](AUTOMATION.md) 참고.

```powershell
.\sync.cmd --only deadlines        # 마감 일정만 빠르게 갱신 (요청 ~10회)
.\sync.cmd --course 74261          # 특정 과목만
```

## 결과물 (`data/`)

| 경로 | 내용 |
|---|---|
| `deadlines.md` / `.json` | **마감 일정** — 캘린더(동영상 시청 기한 등) + 과제, 날짜순, 제출 여부 표시 |
| `<과목>/과제/<과제>.md` + `assignments.json` | 과제 설명·첨부·종료일시·남은 기한·제출/채점 상태 |
| `<과목>/게시판/<게시판>/<날짜>_<제목>.md` | 공지사항·자료실 글 본문 + 첨부 (교수·조교 게시물만) |
| `<과목>/<활동>/<파일>` | 강의자료 파일 (`ubfile`/`resource`/`folder`) |
| `courses.json` | 과목·활동 목록 — 동영상은 **제목·링크만** |
| `manifest.json` | 내려받은 파일·글 목록 (재실행 시 건너뛰기용) |

수집하지 않는 것: 동영상 본체(`vod`), 학생 글이 올라오는 게시판(Q&A·팀빌딩 등 — `config.BOARD_INCLUDE` 로 조정), 퀴즈·출석.

## 지키는 선 (학교 공지 「저작권 유의사항 안내」 기준)

| 학교 금지 사항 | 이 도구의 대응 |
|---|---|
| 자료를 타인에게 배포·전송 | `data/` 는 `.gitignore` — **팀 폴더에 있어도 공유 금지** |
| 계정정보 공유 | `state/` (세션) 도 `.gitignore`, 비밀번호는 어디에도 저장 안 함 |
| 복사방지 조치 무력화 | 동영상 모듈(`vod` 등) 은 요청조차 하지 않음 |
| 인터넷 게시 | 깃허브·클라우드 업로드 금지 |

추가로: 요청 간격 1.5초 / 동시성 1 / 게시판·포럼(타인 개인정보) 미수집 / 문서 확장자만.

`config.py` 의 `REQUEST_INTERVAL` 은 줄이지 말 것.
