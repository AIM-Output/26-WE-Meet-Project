"""완전 무인 모드용 자격증명 저장. 본인이 직접 입력하며, 비밀번호는 화면에 표시되지 않는다.
저장 위치 state/cred.bin 은 Windows DPAPI(이 계정 전용)로 암호화된다.

    python setup_creds.py          # 저장/갱신
    python setup_creds.py --show   # 저장된 아이디만 표시 (비번은 표시 안 함)
    python setup_creds.py --clear  # 삭제 (반자동 모드로 되돌리기)
"""
import getpass
import sys

import auth


def main() -> int:
    if "--clear" in sys.argv:
        print("삭제됨." if auth.clear() else "저장된 자격증명이 없습니다.")
        return 0
    if "--show" in sys.argv:
        c = auth.load()
        print(f"저장된 아이디: {c['username']}" if c else "저장된 자격증명이 없습니다.")
        return 0

    print("전남대 포털/e클래스 SSO 자격증명을 저장합니다. (state/cred.bin, DPAPI 암호화)")
    print("Ctrl+C 로 취소.")
    username = input("아이디: ").strip()
    if not username:
        print("취소됨.")
        return 1
    pw1 = getpass.getpass("비밀번호(화면에 안 보임): ")
    pw2 = getpass.getpass("비밀번호 확인: ")
    if pw1 != pw2:
        print("두 비밀번호가 다릅니다. 저장하지 않았습니다.")
        return 1
    if not pw1:
        print("비밀번호가 비어 있습니다. 저장하지 않았습니다.")
        return 1
    auth.save(username, pw1)
    print("저장 완료. 이제 `login.cmd --auto` 로 무인 로그인을 시험해 보세요.")
    print("  (처음 한 번은 login.cmd 를 수동으로 실행해 신뢰 기기 쿠키를 만들어 두면 2차 인증이 생략됩니다.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
