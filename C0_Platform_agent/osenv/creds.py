"""비밀 보관 — Windows DPAPI(이 Windows 계정 전용) / macOS 키체인(로그인 키체인).

무엇을 어떤 이름으로 저장할지(ENTROPY·설명 문자열·키체인 항목 이름)는 쓰는 쪽(C3_Login_agent/login/auth.py)이 정한다.
여기는 OS 별 '금고'만 다룬다 — 평문을 디스크에 쓰지 않는다.

    dpapi_protect(data, entropy, description) / dpapi_unprotect(data, entropy)     Windows — pip 의존성 없이 ctypes 로 crypt32
    keychain_set(service, account, secret) / keychain_get / keychain_delete      macOS — keyring(Security 프레임워크)

DPAPI 코드는 auth.py 에서 그대로 옮겼다(2026-10-04). 구조체·호출 순서·인자를 바꾸면 이미 저장된 cred.bin 을 못 풀 수 있다.
키체인은 keyring 을 쓴다 — `security add-generic-password -w <비밀번호>` 는 비밀번호가 프로세스 목록에 잠깐 드러나서 쓰지 않는다.
"""
from __future__ import annotations

import ctypes
from typing import Optional


class CredsError(RuntimeError):
    """사람이 읽을 이유를 담는다."""


# ---------------------------------------------------------------- Windows DPAPI

class _BLOB(ctypes.Structure):
    # cbData 는 DWORD(= ctypes.c_ulong, ctypes.wintypes 의 정의 그대로). wintypes 를 import 하지 않아야 맥에서도 이 모듈을 불러올 수 있다.
    _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _in(data: bytes) -> _BLOB:
    buf = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_char)))


def _out_bytes(blob: _BLOB) -> bytes:
    raw = ctypes.string_at(blob.pbData, blob.cbData)
    ctypes.windll.kernel32.LocalFree(blob.pbData)
    return raw


def dpapi_protect(data: bytes, entropy: bytes, description: str) -> bytes:
    """CryptProtectData(CurrentUser) — 이 Windows 계정으로 로그인했을 때만 풀린다."""
    out = _BLOB()
    din, ent = _in(data), _in(entropy)
    if not ctypes.windll.crypt32.CryptProtectData(
        ctypes.byref(din), description, ctypes.byref(ent), None, None, 0, ctypes.byref(out)
    ):
        raise ctypes.WinError()
    return _out_bytes(out)


def dpapi_unprotect(data: bytes, entropy: bytes) -> bytes:
    out = _BLOB()
    din, ent = _in(data), _in(entropy)
    if not ctypes.windll.crypt32.CryptUnprotectData(
        ctypes.byref(din), None, ctypes.byref(ent), None, None, 0, ctypes.byref(out)
    ):
        raise ctypes.WinError()
    return _out_bytes(out)


# ---------------------------------------------------------------- macOS 키체인

def _keyring():
    try:
        import keyring                                   # C3_Login_agent/requirements.txt (맥에서만 설치)
    except ImportError as e:
        raise CredsError("keyring 이 설치되어 있지 않습니다 — desktop/sidecar/requirements.txt 를 다시 설치하세요 (개발 모드)") from e
    return keyring


def keychain_set(service: str, account: str, secret: str) -> None:
    try:
        _keyring().set_password(service, account, secret)
    except CredsError:
        raise
    except Exception as e:                               # noqa: BLE001 — 키체인 잠김·거부 등
        raise CredsError(f"키체인에 저장하지 못했습니다: {e}") from e


def keychain_get(service: str, account: str) -> Optional[str]:
    return _keyring().get_password(service, account)


def keychain_delete(service: str, account: str) -> bool:
    kr = _keyring()
    try:
        kr.delete_password(service, account)
        return True
    except Exception:                                    # noqa: BLE001 — 없으면 PasswordDeleteError
        return False
