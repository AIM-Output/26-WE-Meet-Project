import type { CSSProperties } from "react";

// 유니버스 로고 — 시안 B-2 '종이 별자리'(2026-10-25 사용자 선택, design/logo-concepts/).
// 종이 판 위 솔빛 별 여섯을 이으면 U, 가장 밝은 별(오늘의 나)은 모래빛 무리. 브랜드 고정색이라 토큰 대신 hex 를 쓴다.
// 32px 이하는 별자리를 1.2배 키우고 선·별을 굵힌 작은 판 — 큰 판은 작게 줄이면 선이 녹는다.
// 같은 좌표: app/icon.svg(작은 판) · desktop/splash/index.html · desktop/src-tauri/icons/make_source.py

type Geometry = { pts: [number, number][]; r: number[]; line: number; halo: number; edge: number };

const REGULAR: Geometry = {
  pts: [[29, 29], [31, 51], [39, 67], [58, 71], [68, 57], [71, 31]],
  r: [7.5, 4.5, 5.5, 4.5, 5.5, 6],
  line: 3,
  halo: 12.5,
  edge: 1.5,
};
const SMALL: Geometry = {
  pts: [[24.8, 24.8], [27.2, 51.2], [36.8, 70.4], [59.6, 75.2], [71.6, 58.4], [75.2, 27.2]],
  r: [10.4, 6.2, 7.6, 6.2, 7.6, 8.3],
  line: 5.5,
  halo: 16.5,
  edge: 4,
};

export function BrandMark({ size = 32, className, style }: { size?: number; className?: string; style?: CSSProperties }) {
  const g = size <= 32 ? SMALL : REGULAR;
  const [hx, hy] = g.pts[0];
  return (
    <svg viewBox="0 0 100 100" width={size} height={size} className={className} style={style} aria-hidden>
      <rect width="100" height="100" rx="23" fill="#fbf8f3" stroke="#d8ccbc" strokeWidth={g.edge} />
      <circle cx={hx} cy={hy} r={g.halo} fill="#e6d6c2" />
      <polyline
        points={g.pts.map((p) => p.join(",")).join(" ")}
        fill="none"
        stroke="#b89a7b"
        strokeWidth={g.line}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {g.pts.map(([x, y], i) => (
        <circle key={i} cx={x} cy={y} r={g.r[i]} fill="#33644d" />
      ))}
    </svg>
  );
}
