# C0_Platform_agent — OS 공통 계층 (`osenv`)

Windows·macOS 에서 달라지는 것만 모은 표준 라이브러리 패키지입니다. 설치할 것 없음(맥 OCR 만 pyobjc — 사이드카 requirements 에 들어 있다).
계획과 배경은 [WE-Meet_데스크톱앱_맥지원_계획.md](../WE-Meet_데스크톱앱_맥지원_계획.md).

| 함수 | Windows | macOS·리눅스 |
|---|---|---|
| `venv_python(dir)` | `.venv\Scripts\python.exe` | `.venv/bin/python` (사이드카 빌드 venv) |
| `module_cmd(mod, *args)` | 지금 도는 python `-X utf8 -m mod` · 묶인 앱이면 `<앱 실행 파일> --run-module mod` | 같음 |
| `task_command(mod, *args)` | 작업 스케줄러용 `& '<실행 파일>' …` (register-task.ps1 `-Command`) | — |
| `browsers_dir()` | `PLAYWRIGHT_BROWSERS_PATH`(앱 데이터 폴더) 또는 지금 python 의 `venv/pw-browsers` | 같음 |
| `pid_alive(pid)` | `tasklist` (이름에 python 포함) | `os.kill(pid, 0)` |
| `NO_WINDOW` | `CREATE_NO_WINDOW` | `0` |
| `venv.ensure(dir, req)` | venv·패키지 — requirements 해시가 바뀌었을 때만 다시 설치 (desktop/sidecar/build.py) | 같음 |
| `appdata.default_root/apply/migrate` | `%LOCALAPPDATA%\kr.univus.desktop\data` | `~/Library/Application Support/kr.univus.desktop/data` |
| `creds.dpapi_protect/unprotect` · `creds.keychain_set/get/delete` | DPAPI(CurrentUser) | 로그인 키체인(keyring) — 무엇을 어떤 이름으로 넣을지는 C3 `auth.py` |
| `launchd.register/unregister/info` | (작업 스케줄러는 각 기능의 `register-task.ps1`) | `~/Library/LaunchAgents/<label>.plist` — 시각마다 + 로그인 시 |
| `ocr.available/image_texts/pdf_text` (2026-10-25) | **Windows 내장 OCR**(`Windows.Media.Ocr`) — PowerShell 5.1 이 `osenv/ocr_win.ps1` 을 돌린다(설치 없음, 이미지는 표준입력 base64 → 메모리 스트림, 긴 포스터는 잘라 읽기, 스캔 PDF 는 `Windows.Data.Pdf`) | macOS **Vision**(pyobjc-framework-Vision·Quartz, 맥만 requirements, 한국어는 macOS 13+) — 스캔 PDF 는 아직 None · 리눅스는 없음 |

쓰는 곳: C3 `login/config.py`(BROWSERS) · C2·F2·F6 `config.py`(C3_BROWSERS·module_cmd) · F1 `runner.py`·`pipeline.py` · F6 `runs.py`(pid_alive) · `univ_us_local/backend/desktop.py`(appdata·module_cmd) · F11 `attachments.py`(ocr — F12 도 이것으로).

OCR 은 모델을 묶지 않고 OS 엔진만 쓴다 — 한국어 OCR 이 없는 컴퓨터(`available()["korean"]` False)에서는 기능이 OCR 없이 돈다. `UNIVUS_OCR=off` 로 끈다(F11·F12 테스트).
`ocr_win.ps1` 은 **UTF-8 BOM + CRLF** 로 둔다 — PowerShell 5.1 은 BOM 없는 파일의 한글을 ANSI(cp949)로 읽어 문법 오류가 난다. 사이드카 spec 이 이 파일을 묶는다(`KEEP_FILES`).
손으로 확인: `python -m osenv.ocr 그림.png 공고.pdf`(C0 폴더에서).

빌려 쓰는 법 — 다른 기능 폴더를 빌리는 기존 방식과 같습니다. `sys.path` 에는 **append** 합니다(맨 앞에 넣으면 이 폴더의 `tests` 가 남의 것을 가릴 수 있음).

```python
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import module_cmd
```

기능마다 `.venv` 를 두지 않는다 — 데스크톱 앱(묶인 실행 파일)이든 개발 모드(`desktop/sidecar/.venv`)든 자식 프로세스는 지금 도는 python 을 다시 띄운다.

명령줄 (`C0_Platform_agent` 폴더에서, 개발 venv python 으로):

```bash
python -m osenv venv ../desktop/sidecar/.venv -r ../desktop/sidecar/requirements.txt   # 개발·빌드 venv 만들기·맞추기
python -m osenv copy-data --to ../desktop/.dev-data                                    # 설치된 앱 데이터 → 개발 데이터 (덮어쓰지 않음)
```

테스트: `python -m pytest C0_Platform_agent/tests -q` (개발 venv — `desktop/sidecar/.venv`)
