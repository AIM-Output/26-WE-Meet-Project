# C0_Platform_agent — OS 공통 계층 (`osenv`)

Windows·macOS 에서 달라지는 것만 모은 표준 라이브러리 패키지입니다. 설치할 것 없음.
계획과 배경은 [WE-Meet_데스크톱앱_맥지원_계획.md](../WE-Meet_데스크톱앱_맥지원_계획.md).

| 함수 | Windows | macOS·리눅스 |
|---|---|---|
| `venv_python(dir)` | `.venv\Scripts\python.exe` | `.venv/bin/python` |
| `pid_alive(pid)` | `tasklist` (이름에 python 포함) | `os.kill(pid, 0)` |
| `NO_WINDOW` | `CREATE_NO_WINDOW` | `0` |
| `script(name)` | `setup.cmd` | `setup.command` (안내 문구용) |
| `venv.ensure(dir, req, chromium=)` | venv·패키지·Chromium — requirements 해시가 바뀌었을 때만 다시 설치 | 같음 |
| `creds.dpapi_protect/unprotect` · `creds.keychain_set/get/delete` | DPAPI(CurrentUser) | 로그인 키체인(keyring) — 무엇을 어떤 이름으로 넣을지는 C3 `auth.py` |
| `launchd.register/unregister/info` | (작업 스케줄러는 각 기능의 `register-task.ps1`) | `~/Library/LaunchAgents/<label>.plist` — 시각마다 + 로그인 시 |

쓰는 곳: C3 `login/config.py`(PYTHON) · C2·F2·F6 `config.py`(C3_PYTHON) · F1 `runner.py`·`pipeline.py` · F6 `runs.py`(pid_alive).

빌려 쓰는 법 — 다른 기능 폴더를 빌리는 기존 방식과 같습니다. `sys.path` 에는 **append** 합니다(맨 앞에 넣으면 이 폴더의 `tests` 가 남의 것을 가릴 수 있음).

```python
C0_AGENT_DIR = Path(os.environ.get("C0_AGENT_DIR") or PROJECT_ROOT / "C0_Platform_agent")
if str(C0_AGENT_DIR) not in sys.path:
    sys.path.append(str(C0_AGENT_DIR))
from osenv import venv_python
```

맥 런처(`*.command`)는 `univus.sh` 를 `source` 하고 `univus_venv DIR REQ [--chromium]` 로 `python -m osenv venv` 를 부른다 — 런처에는 로직을 두지 않는다.

이후 단계에서 늘어날 것: 앱 데이터 폴더(데스크톱 앱 4단계).

테스트: `python -m pytest C0_Platform_agent/tests -q`
