"""앱 아이콘 만들기 — 표준 라이브러리만. 로고는 시안 B-2 '종이 별자리'(2026-10-25 사용자 선택,
univ_us_local/frontend/design/logo-concepts/): 종이 판 + 솔빛 별 여섯을 이은 U + 가장 밝은 별(왼쪽 위)의 모래빛 무리.
좌표는 100 단위 — 헤더 BrandMark.tsx · app/icon.svg · desktop/splash/index.html 과 같다.

    python make_source.py          → source.png (1024×1024, 큰 판)
    npm run icon   (desktop/ 에서)  → 모든 크기(ico·icns·png). 생긴 android/·ios/ 폴더는 쓰지 않아 지운다
    python make_source.py --small  → 32px 이하 자리(32x32.png · Square30x30Logo.png · icon.ico 의 16·24·32)와
                                     대시보드 파비콘(univ_us_local/frontend/src/app/favicon.ico)을 작은 판으로 다시 쓴다

작은 판 = 별자리를 1.2배 키우고 선·별을 굵게 한 것. 큰 판 그대로 16px 로 줄이면 선이 1px 아래로 녹는다."""
import math
import struct
import sys
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
FAVICON = HERE.parents[2] / "univ_us_local" / "frontend" / "src" / "app" / "favicon.ico"

PAPER = (251, 248, 243)       # #fbf8f3 종이 판
EDGE = (216, 204, 188)        # #d8ccbc 판 테두리 — 밝은 바탕에서 가장자리가 묻히지 않게
HALO = (230, 214, 194)        # #e6d6c2 가장 밝은 별의 모래빛 무리
LINE = (184, 154, 123)        # #b89a7b 별을 잇는 선 (짙은 모래)
STAR = (51, 100, 77)          # #33644d 별 (Pine, 브랜드 주색)
RX = 23                       # 판 모서리

REGULAR = dict(pts=[(29, 29), (31, 51), (39, 67), (58, 71), (68, 57), (71, 31)],
               r=(7.5, 4.5, 5.5, 4.5, 5.5, 6), line=3, halo=12.5, edge=0.75)
SMALL = dict(pts=[(24.8, 24.8), (27.2, 51.2), (36.8, 70.4), (59.6, 75.2), (71.6, 58.4), (75.2, 27.2)],
             r=(10.4, 6.2, 7.6, 6.2, 7.6, 8.3), line=5.5, halo=16.5, edge=2)


def d_tile(x: float, y: float) -> float:
    qx, qy = abs(x - 50) - (50 - RX), abs(y - 50) - (50 - RX)
    return math.hypot(max(qx, 0), max(qy, 0)) + min(max(qx, qy), 0) - RX


def d_segment(x: float, y: float, a: tuple, b: tuple) -> float:
    vx, vy = b[0] - a[0], b[1] - a[1]
    t = max(0.0, min(1.0, ((x - a[0]) * vx + (y - a[1]) * vy) / (vx * vx + vy * vy)))
    return math.hypot(x - a[0] - t * vx, y - a[1] - t * vy)


def render(n: int, g: dict) -> list:
    """n×n RGBA(미리 곱한 값 아님) 행 목록. 작은 크기는 크게 그려 상자 평균으로 줄인다(브라우저와 비슷한 가장자리)."""
    ss = 1 if n >= 256 else max(1, 256 // n)
    m = n * ss
    px = 100 / m                                   # 화면 1px 이 몇 단위인가
    segs = list(zip(g["pts"], g["pts"][1:]))
    hx, hy = g["pts"][0]

    def cov(d: float) -> float:                    # 거리(단위) → 그 화소를 덮는 비율
        return min(1.0, max(0.0, 0.5 - d / px))

    big = []
    for j in range(m):
        y = (j + 0.5) * px
        row = []
        for i in range(m):
            x = (i + 0.5) * px
            dt = d_tile(x, y)
            c_tile = cov(dt)
            if c_tile == 0:
                row.append((0.0, 0.0, 0.0, 0.0))
                continue
            acc = [PAPER[0] * c_tile, PAPER[1] * c_tile, PAPER[2] * c_tile, c_tile]
            layers = (
                (EDGE, max(0.0, c_tile - cov(dt + g["edge"]))),
                (HALO, cov(math.hypot(x - hx, y - hy) - g["halo"]) * c_tile),
                (LINE, cov(min(d_segment(x, y, a, b) for a, b in segs) - g["line"] / 2)),
                (STAR, cov(min(math.hypot(x - sx, y - sy) - r for (sx, sy), r in zip(g["pts"], g["r"])))),
            )
            for color, a in layers:
                if a > 0:
                    acc = [color[0] * a + acc[0] * (1 - a), color[1] * a + acc[1] * (1 - a),
                           color[2] * a + acc[2] * (1 - a), a + acc[3] * (1 - a)]
            row.append(tuple(acc))
        big.append(row)
    out = []
    for j in range(n):
        row = []
        for i in range(n):
            s = [0.0, 0.0, 0.0, 0.0]
            for jj in range(j * ss, j * ss + ss):
                for p in big[jj][i * ss:i * ss + ss]:
                    s = [s[k] + p[k] for k in range(4)]
            a = s[3] / (ss * ss)
            row.append((0, 0, 0, 0) if a == 0 else
                       tuple(round(s[k] / s[3]) for k in range(3)) + (round(255 * a),))
        out.append(row)
    return out


def png(rows: list) -> bytes:
    n = len(rows)
    raw = b"".join(b"\0" + b"".join(bytes(p) for p in row) for row in rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(images: list) -> bytes:
    """[(크기, PNG 바이트)] → .ico (항목마다 PNG 를 그대로 담는다 — Windows Vista 이후 지원)."""
    head, data = struct.pack("<HHH", 0, 1, len(images)), b""
    dirs = b""
    for n, p in images:
        dirs += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(p), 6 + 16 * len(images) + len(data))
        data += p
    return head + dirs + data


def icon_png(n: int) -> bytes:
    return png(render(n, SMALL if n <= 32 else REGULAR))


def main() -> None:
    if "--small" in sys.argv:
        for name, n in (("32x32.png", 32), ("Square30x30Logo.png", 30)):
            (HERE / name).write_bytes(icon_png(n))
        (HERE / "icon.ico").write_bytes(ico([(n, icon_png(n)) for n in (16, 24, 32, 48, 64, 256)]))
        FAVICON.write_bytes(ico([(n, icon_png(n)) for n in (16, 32, 48)]))
        print("작은 판: 32x32.png · Square30x30Logo.png · icon.ico ·", FAVICON)
        return
    out = HERE / "source.png"
    out.write_bytes(png(render(1024, REGULAR)))
    print(f"{out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
