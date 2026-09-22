"""자격증명을 Windows DPAPI(CurrentUser)로 암호화해 state/cred.bin 에 저장/복호화.

- CryptProtectData 를 CurrentUser 범위로 쓰므로 **이 Windows 계정으로 로그인했을 때만** 복호화된다.
  파일을 다른 PC·다른 사용자에게 복사해도 풀리지 않는다.
- 추가로 앱 고유 엔트로피를 섞는다. pip 의존성 없이 ctypes 로 crypt32 를 직접 호출.
- 비밀번호 평문은 디스크에 절대 쓰지 않는다 (메모리에서만 잠깐 다룬다).
"""
import ctypes
import json
from ctypes import wintypes

import config as C

ENTROPY = b"eclass-agent/jnu/v1"


class _BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _in(data: bytes) -> _BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _out_bytes(blob: _BLOB) -> bytes:
    raw = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return raw


def _protect(data: bytes) -> bytes:
    out = _BLOB()
    din, ent = _in(data), _in(ENTROPY)
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(din), "eclass-agent", ctypes.byref(ent), None, None, 0, ctypes.byref(out)
    ):
        raise ctypes.WinError()
    return _out_bytes(out)


def _unprotect(data: bytes) -> bytes:
    out = _BLOB()
    din, ent = _in(data), _in(ENTROPY)
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(din), None, ctypes.byref(ent), None, None, 0, ctypes.byref(out)
    ):
        raise ctypes.WinError()
    return _out_bytes(out)


def save(username: str, password: str) -> None:
    blob = _protect(json.dumps({"username": username, "password": password}).encode("utf-8"))
    C.CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    C.CRED_FILE.write_bytes(blob)


def load() -> dict | None:
    """{'username','password'} 또는 None. 복호화 실패(다른 계정/손상)면 None."""
    if not C.CRED_FILE.exists():
        return None
    try:
        return json.loads(_unprotect(C.CRED_FILE.read_bytes()).decode("utf-8"))
    except Exception:
        return None


def clear() -> bool:
    if C.CRED_FILE.exists():
        C.CRED_FILE.unlink()
        return True
    return False


def has_creds() -> bool:
    return C.CRED_FILE.exists()
