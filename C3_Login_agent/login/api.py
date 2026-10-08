"""대시보드(univ_us_local)에 붙이는 C3 API — 자동 로그인 정보(SSO 아이디·비밀번호) 저장·확인·지우기.
명령줄 `python -m login creds`(creds.py)의 앱 화면판이다. 화면: 설정 → 연결 소스 '자동 로그인 정보'.

    GET    /api/login/creds                         {saved, username, store}   — 비밀번호는 돌려주지 않는다
    PUT    /api/login/creds  {username, password}   저장·갱신 (Windows DPAPI state/cred.bin · 맥 로그인 키체인) → GET 과 같은 모양
    DELETE /api/login/creds                         지우기 → 반자동(신뢰 기기 쿠키 + 휴대폰 인증)으로 되돌린다

비밀번호는 요청 본문으로 한 번 들어와 auth.save 로만 간다 — 로그·응답·예외 문구에 넣지 않는다.
이 서버는 앱 창의 세션 쿠키와 Origin 을 확인한다(univ_us_local/backend/app/main.py) — 다른 프로그램이 부르지 못한다.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import auth
from . import config as C

MAX_USERNAME = 64
MAX_PASSWORD = 256


class CredsBody(BaseModel):
    username: str
    password: str


def creds_info() -> dict:
    data = auth.load() if auth.has_creds() else None
    return {
        "saved": auth.has_creds(),
        "username": (data or {}).get("username"),       # 복호화 실패(다른 계정에서 만든 파일 등)면 None — saved 는 참
        "store": "dpapi" if C.IS_WINDOWS else "keychain",
    }


def build_router() -> APIRouter:
    r = APIRouter(prefix="/api/login", tags=["C3 login"])

    @r.get("/creds")
    def get_creds() -> dict:
        return creds_info()

    @r.put("/creds")
    def put_creds(body: CredsBody) -> dict:
        username = body.username.strip()
        password = body.password
        if not username or len(username) > MAX_USERNAME or any(ch.isspace() for ch in username):
            raise HTTPException(422, "아이디(학번)를 확인하세요")
        if not password or len(password) > MAX_PASSWORD or "\n" in password or "\r" in password:
            raise HTTPException(422, "비밀번호를 확인하세요")
        try:
            auth.save(username, password)
        except Exception as e:                           # noqa: BLE001 — 저장소(DPAPI·키체인) 오류 종류만 알린다
            raise HTTPException(500, f"저장하지 못했습니다 ({type(e).__name__})") from None
        return creds_info()

    @r.delete("/creds")
    def delete_creds() -> dict:
        auth.clear()
        return creds_info()

    return r
