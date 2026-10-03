# C3_Login_agent — 포털 자동 로그인 (유니버스 공통 C3)

전남대 **SSO 로그인 한 번**으로 e클래스(`sel.jnu.ac.kr`)와 학사정보시스템(`hakstd.jnu.ac.kr`)이 같이 열린다.
그 로그인을 여러 기능이 같이 쓰므로 한 폴더에 모았다 (2026-09-30, 예전 `eclass_agent` 에서 분리).

| 빌려 쓰는 기능 | 무엇을 |
|---|---|
| **F6** e클래스 과제·마감 (`F6_Eclass_agent`) | 세션 · 재인증 · `.venv`(playwright·bs4) · Chromium |
| **C2** 프로필 가져오기 (`C2_Profile_agent`) | 세션 · 재인증 · `.venv` — 학사정보시스템 |
| **F2** 기이수성적 (`F2_Graduation_agent`) | 세션 · `.venv` (로그인 절차는 C2 것을 거친다) |
| **F11** 장학 카탈로그 (`notice_agent`) | 세션 · 재인증 · Chromium |

- **비밀번호는 이 폴더 코드만 다룬다.** 빌려 쓰는 쪽은 세션 파일 경로와 `login.reauthenticate(p)` 만 안다.
- 신뢰 기기 쿠키(`RathonSSO_TrustDevice_*`, 약 1년) 덕에 한 번 휴대폰 2차 인증을 통과하면 그 뒤로는 창 없이 다시 로그인된다.

```
C3_Login_agent/
├── login/                  파이썬 패키지 (import login)
│   ├── config.py           경로 · SSO 주소 · 브라우저 위치 · browser_env()
│   ├── auth.py             DPAPI(이 Windows 계정 전용) 자격증명 암호화 — ENTROPY 는 절대 바꾸지 말 것
│   ├── session.py          session_ok · refresh_via_sso · auto_login · reauthenticate · interactive_login (playwright)
│   ├── creds.py            자격증명 저장·보기·지우기 (setup-creds.cmd)
│   ├── __init__.py         status() · problem() — playwright 없이도 import 된다(대시보드 백엔드용)
│   └── __main__.py         명령줄
├── setup.cmd               .venv + playwright·bs4 + Chromium(.venv\pw-browsers) — 한 번만
├── login.cmd               로그인 창 (--auto: 무인 로그인 시험 · check: 세션 확인)
├── setup-creds.cmd         완전 무인용 아이디·비밀번호 저장 (--show · --clear)
├── requirements.txt
└── state/  .venv/          (gitignore) 세션·자격증명 · 가상환경
```

## 처음 한 번

```powershell
cd C3_Login_agent
.\setup.cmd           # .venv + 패키지 + Chromium (수백 MB, 몇 분)
.\login.cmd           # 창이 뜨면 [SSO 로그인] → 휴대폰 2차 인증 → 신뢰 기기 등록 + 세션 저장
.\setup-creds.cmd     # (선택) 아이디·비밀번호 저장 → 세션이 만료돼도 창 없이 다시 로그인 (완전 무인)
.\login.cmd --auto    # (선택) 무인 로그인 시험 → "성공. 세션 저장됨."
```

대시보드에서는 **수집 원천 → e클래스 → `로그인 창 열기`** 가 `login.cmd` 와 같은 창을 띄운다(로그인되면 저절로 닫히고 바로 수집한다).

```powershell
.\login.cmd check                     # 저장된 세션이 지금 살아 있는지 (창 없음)
.\.venv\Scripts\python -m login status  # 설치·세션·자격증명 파일 상태
```

## 재인증 순서 (`login.reauthenticate(p)`)

1. 저장된 세션(`state/storage_state.json`)으로 바로 접속 — 빌려 쓰는 쪽이 먼저 해 본다
2. 죽었으면 → SSO 쿠키로 조용히 복구 (`refresh_via_sso`, 비밀번호 안 씀)
3. 그래도 안 되면 → 저장된 자격증명으로 headless 자동 로그인 (신뢰 기기라 2차 인증 생략)
4. 신뢰 기기까지 만료됐으면 → 실패. 빌려 쓰는 쪽이 '로그인 필요'로 알린다 → `login.cmd` 한 번(아이디·비밀번호는 자동 입력, 휴대폰 인증만)

반드시 `lms_sso.php`(SSO 시작점) → 'SSO 로그인' → `idpm.jnu.ac.kr` 경유로 가야 신뢰 기기 쿠키가 확인된다.
전체 세션(state)을 그대로 써야 하며, 쿠키를 골라내면 신뢰 인식이 깨진다.

## 빌려 쓰는 법 (코드)

```python
sys.path.insert(0, r"...\C3_Login_agent")      # 환경변수 C3_AGENT_DIR 로 위치를 바꿀 수 있다
import login
login.config.use_browsers()                     # sync_playwright() 전에 — Chromium 위치
with sync_playwright() as p:
    ctx = p.request.new_context(storage_state=str(login.STATE_FILE))
    if not login.session_ok(ctx) and not login.reauthenticate(p):
        ...  # 로그인 필요
```

브라우저가 필요한 기능은 **이 폴더의 `.venv\Scripts\python.exe`** 로 띄운다(환경변수 `PLAYWRIGHT_BROWSERS_PATH=…\.venv\pw-browsers`).
`.venv` 를 옮기면 `python.exe` 는 동작하지만 `pip.exe` 같은 실행 파일은 옛 경로가 박혀 있다 → `python -m pip` 을 쓴다.

## 지키는 선 (e클래스 공지 「저작권 유의사항 안내」 — 계정정보 공유 금지)

- `state/` 는 곧 **내 계정으로 로그인된 상태**다. 복사·공유·업로드 금지 (`.gitignore`).
- 비밀번호는 **암호화된 형태로만** 이 PC에 존재(평문은 파일·로그 어디에도 없음). DPAPI CurrentUser 범위라 **이 Windows 계정에서만** 복호화된다. 학교 비번을 바꾸면 `setup-creds.cmd` 다시.
- `auth.py` 의 `ENTROPY = b"eclass-agent/jnu/v1"` 와 설명 문자열은 **폴더 이름이 아니라 암호화 키 재료**다. 바꾸면 저장된 `cred.bin` 을 풀 수 없다 — 폴더를 옮기면서도 그대로 두었다.
- 무인을 끄려면 `.\setup-creds.cmd --clear` (반자동: 세션이 죽으면 로그인 창이 필요해진다).
