"use client";

import { useId, useRef, type ReactNode } from "react";
import { motion } from "motion/react";

// 탭 — role=tablist + 좌우 화살표 이동(6-12). 선택 표시는 layoutId 로 미끄러진다.
// variant: line = 페이지 안의 LNB(자료/요약/문제…) · pill = 필터(전체/e클래스/…)

export interface TabItem<K extends string> {
  key: K;
  label: ReactNode;
  count?: number;
  disabled?: boolean;
}

export function Tabs<K extends string>({
  items,
  value,
  onChange,
  label,
  variant = "line",
  size = "md",
  className = "",
}: {
  items: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  variant?: "line" | "pill";
  size?: "sm" | "md";
  className?: string;
}) {
  const id = useId();
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (from: number, dir: 1 | -1) => {
    for (let i = 1; i <= items.length; i++) {
      const j = (from + dir * i + items.length) % items.length;
      if (!items[j].disabled) {
        refs.current[j]?.focus();
        onChange(items[j].key);
        return;
      }
    }
  };

  const line = variant === "line";

  return (
    <div
      role="tablist"
      aria-label={label}
      className={`no-scrollbar flex max-w-full items-center overflow-x-auto ${line ? "gap-1 border-b border-border" : "gap-1 rounded-lg bg-surface-3 p-1"} ${className}`}
    >
      {items.map((t, i) => {
        const on = t.key === value;
        return (
          <button
            key={t.key}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={on}
            tabIndex={on ? 0 : -1}
            disabled={t.disabled}
            onClick={() => onChange(t.key)}
            onKeyDown={(e) => {
              if (e.key === "ArrowRight") {
                e.preventDefault();
                move(i, 1);
              } else if (e.key === "ArrowLeft") {
                e.preventDefault();
                move(i, -1);
              }
            }}
            className={`relative flex flex-none items-center gap-1.5 whitespace-nowrap font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
              size === "sm" ? "h-8 px-2.5 text-[13px]" : "h-10 px-3 text-[14px]"
            } ${line ? "-mb-px" : "rounded-md"} ${on ? "text-text" : "text-muted hover:text-text"}`}
          >
            {on && (
              <motion.span
                layoutId={`tab-${id}`}
                className={line ? "absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary" : "absolute inset-0 rounded-md bg-surface"}
                style={line ? undefined : { boxShadow: "var(--shadow-card), var(--inner-hi)" }}
                transition={{ type: "spring", bounce: 0, visualDuration: 0.22 }}
                aria-hidden
              />
            )}
            <span className="relative">{t.label}</span>
            {t.count !== undefined && (
              <span
                className={`num relative rounded-full px-1.5 text-[12px] leading-5 ${on ? "bg-primary-soft text-primary" : "bg-surface-3 text-faint"}`}
              >
                {t.count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
