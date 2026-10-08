# C3_Login_agent — 포털 자동 로그인 (유니버스 공통 C3)

전남대 **SSO 로그인 한 번**으로 e클래스(`sel.jnu.ac.kr`)와 학사정보시스템(`hakstd.jnu.ac.kr`)이 같이 열린다.
그 로그인을 여러 기능이 같이 쓰므로 한 폴더에 모았다 (2026-09-30, 예전 `eclass_agent` 에서 분리).

| 빌려 쓰는 기능 | 무엇을 |
|---|---|
| **F6** e클래스 과제·마감 (`F6_Eclass_agent`) | 세션 · 재인증 · Chromium |
| **C2** 프로필 가져오기 (`C2_Profile_agent`) | 세션 · 재인증 — 학사정보시스템 |
| **F2** 기이수성적 (`F2_Graduation_agent`) | 세션 (로그인 절차는 C2 것을 거친다) |
| **F11** 장학 카탈로그 (`notice_agent`) | 세션 · 재인증 · Chromium |

- **비밀번호는 이 폴더 코드만 다룬다.** 빌려 쓰는 쪽은 세션 파일 경로와 `login.reauthenticate(p)` 만 안다.
- 신뢰 기기 쿠키(`RathonSSO_TrustDevice_*`, 약 1년) 덕에 한 번 휴대폰 2차 인증을 통과하면 그 뒤로는 창 없이 다시 로그인된다.
- 기능별 `.venv` 는 없다. 로그인 창·수집기는 앱 실행 파일(개발 모드는 `desktop/sidecar/.venv` 의 python)이 `-m login` 으로 다시 띄우고,
  Chromium 은 앱이 처음 실행 때 앱 데이터 폴더(`pw-browsers/`, 개발 모드는 `desktop/sidecar/.venv/pw-browsers`)에 받는다.

```
C3_Login_agent/
├── login/                  파이썬 패키지 (import login)
│   ├── config.py           경로 · SSO 주소 · 브라우저 위치 · browser_env()
│   ├── auth.py             DPAPI(이 Windows 계정 전용)·맥 키체인 자격증명 — ENTROPY 는 절대 바꾸지 말 것
│   ├── session.py          session_ok · refresh_via_sso · auto_login · reauthenticate · interactive_login (playwright)
│   ├── creds.py            자격증명 저장·보기·지우기 (명령줄)
│   ├── api.py              /api/login/creds — 앱의 '자동 로그인 정보' 화면 (비밀번호는 돌려주지 않는다)
│   ├── __init__.py         status() · problem() — playwright 없이도 import 된다(대시보드 백엔드용)
│   └── __main__.py         명령줄
├── requirements.txt        (참고용 — 실제 설치 목록은 desktop/sidecar/requirements.txt)
└── state/                  (gitignore, 개발 기본값) 세션·자격증명 — 앱은 앱 데이터 폴더의 C3_Login_agent/state
```

## 처음 한 번 (앱에서)

1. **설정 → 수집 원천 → e클래스 → `로그인 창 열기`** — 창이 뜨면 [SSO 로그인] → 휴대폰 2차 인증 → 신뢰 기기 등록 + 세션 저장
   (로그인되면 창이 저절로 닫히고 바로 수집한다)
2. (선택) 같은 줄의 **`자동 로그인 정보 저장`** — 아이디·비밀번호를 이 PC 에만 암호화해 저장 → 세션이 만료돼도 창 없이 다시 로그인 (완전 무인)

명령줄 (저장소 루트에서 개발 venv 를 켜고 — `desktop/cli.py` 가 개발 데이터로 `python -m login` 을 돌린다, `--app` 이면 앱 데이터):

```bash
python desktop/cli.py login              # 로그인 창
python desktop/cli.py login --auto       # 무인 로그인 시험 → "성공. 세션 저장됨."
python desktop/cli.py login check        # 저장된 세션이 지금 살아 있는지 (창 없음)
python desktop/cli.py login status       # 브라우저·세션·자격증명 파일 상태
python desktop/cli.py login creds        # 자격증명 저장 (--show 아이디만 · --clear 지우기)
```

## 재인증 순서 (`login.reauthenticate(p)`)

1. 저장된 세션(`state/storage_state.json`)으로 바로 접속 — 빌려 쓰는 쪽이 먼저 해 본다
2. 죽었으면 → SSO 쿠키로 조용히 복구 (`refresh_via_sso`, 비밀번호 안 씀)
3. 그래도 안 되면 → 저장된 자격증명으로 headless 자동 로그인 (신뢰 기기라 2차 인증 생략)
4. 신뢰 기기까지 만료됐으면 → 실패. 빌려 쓰는 쪽이 '로그인 필요'로 알린다 → `로그인 창 열기` 한 번(아이디·비밀번호는 자동 입력, 휴대폰 인증만)

반드시 `lms_sso.php`(SSO 시작점) → 'SSO 로그인' → `idpm.jnu.ac.kr` 경유로 가야 신뢰 기기 쿠키가 확인된다.
전체 세션(state)을 그대로 써야 하며, 쿠키를 골라내면 신뢰 인식이 깨진다.

## 빌려 쓰는 법 (코드)

```python
sys.path.append(r"...\C3_Login_agent")         # 환경변수 C3_AGENT_DIR 로 위치를 바꿀 수 있다
import login
login.config.use_browsers()                     # sync_playwright() 전에 — Chromium 위치
with sync_playwright() as p:
    ctx = p.request.new_context(storage_state=str(login.STATE_FILE))
    if not login.session_ok(ctx) and not login.reauthenticate(p):
        ...  # 로그인 필요
```

브라우저가 필요한 일은 자식 프로세스로 띄운다 — `osenv.module_cmd("login")` (앱이면 `<앱 실행 파일> --run-module login`), 환경변수는 `login.browser_env()`.

## 지키는 선 (e클래스 공지 「저작권 유의사항 안내」 — 계정정보 공유 금지)

- `state/` 는 곧 **내 계정으로 로그인된 상태**다. 복사·공유·업로드 금지 (`.gitignore`).
- 비밀번호는 **암호화된 형태로만** 이 PC에 존재(평문은 파일·로그·API 응답 어디에도 없음). Windows 는 DPAPI CurrentUser 범위라 **이 Windows 계정에서만** 복호화되고, 맥은 로그인 키체인에 둔다. 학교 비번을 바꾸면 앱의 `자동 로그인 정보 바꾸기` 로 다시 저장.
- `auth.py` 의 `ENTROPY = b"eclass-agent/jnu/v1"` 와 설명 문자열은 **폴더 이름이 아니라 암호화 키 재료**다. 바꾸면 저장된 `cred.bin` 을 풀 수 없다 — 폴더를 옮기면서도 그대로 두었다.
- 무인을 끄려면 앱의 `자동 로그인 정보 바꾸기` → `지우기` (반자동: 세션이 죽으면 로그인 창이 필요해진다).
