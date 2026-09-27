"use client";

import { motion } from "motion/react";

// 진행 막대(`30/36 학점`) · 도넛. 정상 / 주의 / 초과 — 숫자를 늘 함께 쓴다.

type BarTone = "primary" | "ok" | "warn" | "accent" | "danger" | "study" | "neutral";
const FILL: Record<BarTone, string> = {
  primary: "var(--primary)",
  ok: "var(--ok)",
  warn: "var(--warn)",
  accent: "var(--accent)",
  danger: "var(--danger)",
  study: "var(--study)",
  neutral: "var(--faint)",
};

export function ProgressBar({
  value,
  max,
  tone = "primary",
  height = 8,
  label,
  marker,
}: {
  value: number;
  max: number;
  tone?: BarTone;
  height?: number;
  label?: string;
  marker?: number; // 0~1 — '오늘까지 계획' 같은 기준선
}) {
  const pct = max > 0 ? Math.min(1, Math.max(0, value / max)) : value > 0 ? 1 : 0;
  return (
    <div
      className="relative w-full overflow-hidden rounded-full bg-surface-3"
      style={{ height }}
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-label={label}
    >
      {/* transform 문자열로 애니메이션 → WAAPI(하드웨어 가속)로 돈다 */}
      <motion.div
        className="h-full origin-left rounded-full"
        style={{ background: FILL[tone], width: "100%" }}
        initial={{ transform: "scaleX(0)" }}
        animate={{ transform: `scaleX(${pct})` }}
        transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
      />
      {marker !== undefined && (
        <span className="absolute top-0 h-full w-0.5 bg-text/60" style={{ left: `${Math.min(100, marker * 100)}%` }} aria-hidden />
      )}
    </div>
  );
}

export function Donut({ value, max, size = 132, stroke = 12, children }: { value: number; max: number; size?: number; stroke?: number; children?: React.ReactNode }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = max > 0 ? Math.min(1, value / max) : 0;
  return (
    <div className="relative flex-none" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={stroke} />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--primary)"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={c}
          initial={{ strokeDashoffset: c }}
          animate={{ strokeDashoffset: c * (1 - pct) }}
          transition={{ type: "spring", bounce: 0, visualDuration: 0.7 }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{children}</div>
    </div>
  );
}
