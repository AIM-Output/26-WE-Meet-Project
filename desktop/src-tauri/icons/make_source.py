"""앱 아이콘 원본(source.png, 1024×1024) 만들기 — 표준 라이브러리만. 다크그린 둥근 사각형 + 베이지 'U' (디자인 v3 "Paper & Pine").
    python make_source.py  →  npm run icon (desktop/) 이 모든 크기(ico·icns·png)를 만든다.
디자이너가 만든 아이콘이 생기면 source.png 만 바꾸고 npm run icon 을 다시 돌리면 된다."""
import struct
import zlib
from pathlib import Path

N = 1024
BG = (51, 100, 77)            # #33644d 다크그린 (브랜드 주색 — univ_us_local/frontend/DESIGN.md)
FG = (203, 175, 148)          # #cbaf94 베이지 (브랜드 두 번째 색) — 대시보드 헤더 로고와 같은 배색
RADIUS = 228                  # 둥근 모서리
SS = (0.25, 0.75)             # 2×2 서브샘플 (가장자리 부드럽게)


def in_rounded(x: float, y: float) -> bool:
    cx = min(max(x, RADIUS), N - RADIUS)
    cy = min(max(y, RADIUS), N - RADIUS)
    return (x - cx) ** 2 + (y - cy) ** 2 <= RADIUS ** 2


def in_u(x: float, y: float) -> bool:
    top, mid, bottom_r_out, bottom_r_in = 262, 590, 214, 94
    left, right = 512 - bottom_r_out, 512 + bottom_r_out
    if top <= y <= mid and (left <= x <= 512 - bottom_r_in or 512 + bottom_r_in <= x <= right):
        return True
    if y > mid:
        d2 = (x - 512) ** 2 + (y - mid) ** 2
        return bottom_r_in ** 2 <= d2 <= bottom_r_out ** 2
    return False


def pixel(px: int, py: int) -> bytes:
    bg = fg = 0
    for dx in SS:
        for dy in SS:
            x, y = px + dx, py + dy
            if in_rounded(x, y):
                if in_u(x, y):
                    fg += 1
                else:
                    bg += 1
    a = (bg + fg) / 4
    if a == 0:
        return b"\0\0\0\0"
    t = fg / (bg + fg)
    rgb = tuple(round(BG[i] * (1 - t) + FG[i] * t) for i in range(3))
    return bytes((*rgb, round(255 * a)))


def main() -> None:
    raw = b"".join(b"\0" + b"".join(pixel(x, y) for x in range(N)) for y in range(N))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", N, N, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    out = Path(__file__).with_name("source.png")
    out.write_bytes(png)
    print(f"{out} ({len(png) // 1024} KB)")


if __name__ == "__main__":
    main()
