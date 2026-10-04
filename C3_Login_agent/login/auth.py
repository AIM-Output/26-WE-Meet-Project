"""자격증명(아이디·비밀번호) 저장/복호화 — Windows 는 DPAPI 로 암호화한 state/cred.bin, 맥은 로그인 키체인.

**ENTROPY 와 CryptProtectData 설명 문자열(DESCRIPTION = "eclass-agent")은 절대 바꾸지 말 것** — 폴더 이름이 아니라 암호화 키 재료다.
바꾸면 이미 저장된 state/cred.bin(비밀번호)을 풀 수 없다. (eclass_agent → C3_Login_agent 로 옮길 때도,
DPAPI 호출 코드를 C0 osenv.creds 로 옮길 때도(2026-10-04) 그대로 두었다.)
**KEYCHAIN_SERVICE·KEYCHAIN_ACCOUNT 도 바꾸지 말 것** — 맥에서 이미 저장한 항목을 못 찾는다.

- Windows: CryptProtectData 를 CurrentUser 범위로 쓰므로 **이 Windows 계정으로 로그인했을 때만** 복호화된다.
  파일을 다른 PC·다른 사용자에게 복사해도 풀리지 않는다. 추가로 앱 고유 엔트로피를 섞는다.
- 맥: 비밀은 키체인에만 있다. state/cred.keychain.json 은 '저장돼 있다'는 표시(항목 이름만, 비밀 없음) —
  대시보드 백엔드(keyring 없음)가 파일만 보고 hasCreds 를 판단하게 하려는 것이다.
- 비밀번호 평문은 디스크에 절대 쓰지 않는다 (메모리에서만 잠깐 다룬다).
"""
import json

from . import config as C
from osenv import IS_WINDOWS                 # C0 — config 가 sys.path 에 붙여 두었다
from osenv import creds as store

ENTROPY = b"eclass-agent/jnu/v1"
DESCRIPTION = "eclass-agent"
KEYCHAIN_SERVICE = "univus-jnu-sso"
KEYCHAIN_ACCOUNT = "default"


def save(username: str, password: str) -> None:
    raw = json.dumps({"username": username, "password": password})
    C.CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    if IS_WINDOWS:
        C.CRED_FILE.write_bytes(store.dpapi_protect(raw.encode("utf-8"), ENTROPY, DESCRIPTION))
        return
    store.keychain_set(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT, raw)
    C.CRED_FILE.write_text(json.dumps({"store": "keychain", "service": KEYCHAIN_SERVICE, "account": KEYCHAIN_ACCOUNT}),
                           encoding="utf-8")


def load() -> dict | None:
    """{'username','password'} 또는 None. 복호화 실패(다른 계정/손상·키체인 거부)면 None."""
    if not C.CRED_FILE.exists():
        return None
    try:
        if IS_WINDOWS:
            return json.loads(store.dpapi_unprotect(C.CRED_FILE.read_bytes(), ENTROPY).decode("utf-8"))
        raw = store.keychain_get(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def clear() -> bool:
    existed = C.CRED_FILE.exists()
    if not IS_WINDOWS:
        try:
            existed = store.keychain_delete(KEYCHAIN_SERVICE, KEYCHAIN_ACCOUNT) or existed
        except store.CredsError:
            pass
    C.CRED_FILE.unlink(missing_ok=True)
    return existed


def has_creds() -> bool:
    return C.CRED_FILE.exists()
