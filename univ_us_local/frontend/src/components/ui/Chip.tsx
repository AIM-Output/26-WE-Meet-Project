"use client";

import type { ReactNode } from "react";
import { Check, CircleHelp, FileText, Info, Minus, OctagonAlert, TriangleAlert } from "lucide-react";
import { daysUntil } from "@/lib/dates";

// Frontend-Screens 4-1 공용 부품 — D-day 칩 · 상태 배지 · 근거 칩 · 과목 칩.
// 규칙: 상태는 색만으로 전하지 않는다(글자·아이콘 병기).

export type Tone = "neutral" | "primary" | "accent" | "danger" | "warn" | "ok" | "info" | "study";

export const TONE_CLASS: Record<Tone, string> = {
  neutral: "bg-surface-3 text-muted",
  primary: "bg-primary-soft text-primary",
  accent: "bg-accent-soft text-accent-text",
  danger: "bg-danger-soft text-danger-text",
  warn: "bg-warn-soft text-warn-text",
  ok: "bg-ok-soft text-ok-text",
  info: "bg-info-soft text-info-text",
  study: "bg-study-soft text-study",
};

export function Chip({
  tone = "neutral",
  icon,
  children,
  square,
  dashed,
  strike,
  title,
  className = "",
}: {
  tone?: Tone;
  icon?: ReactNode;
  children: ReactNode;
  square?: boolean;
  dashed?: boolean;
  strike?: boolean;
  title?: string;
  className?: string;
}) {
  return (
    <span
      title={title}
      className={`chip ${square ? "chip-square" : ""} ${TONE_CLASS[tone]} ${dashed ? "border border-dashed border-current bg-transparent" : ""} ${
        strike ? "line-through" : ""
      } ${className}`}
    >
      {icon}
      {children}
    </span>
  );
}

/** D-day 칩 — 여유(회색) / 임박 D-1~3(주황) / 당일(빨강) / 지남(빨강 취소선) */
export function DdayChip({ date, done, now }: { date: Date; done?: boolean; now?: Date }) {
  if (done) return <Chip tone="ok" icon={<Check aria-hidden />}>완료</Chip>;
  const n = daysUntil(date, now);
  if (n < 0)
    return (
      <Chip tone="danger" strike title={`${-n}일 지남`}>
        지남
      </Chip>
    );
  if (n === 0) return <Chip tone="danger">D-0</Chip>;
  if (n <= 3) return <Chip tone="accent">D-{n}</Chip>;
  return <Chip tone="neutral">D-{n}</Chip>;
}

const STATUS_ICON: Record<Tone, ReactNode> = {
  ok: <Check aria-hidden />,
  warn: <TriangleAlert aria-hidden />,
  accent: <TriangleAlert aria-hidden />,
  danger: <OctagonAlert aria-hidden />,
  info: <Info aria-hidden />,
  neutral: <Minus aria-hidden />,
  primary: <Check aria-hidden />,
  study: <Check aria-hidden />,
};

/** 상태 배지 — 해당·확인 필요·위험·충족 … 아이콘 + 글자 */
export function StatusBadge({ tone, children, unknown }: { tone: Tone; children: ReactNode; unknown?: boolean }) {
  return (
    <Chip tone={tone} square icon={unknown ? <CircleHelp aria-hidden /> : STATUS_ICON[tone]}>
      {children}
    </Chip>
  );
}

/** 근거 칩 — `p.12` · `공고문 1쪽`. 누르면 원문으로 */
export function EvidenceChip({ label, onClick, href, title }: { label: string; onClick?: () => void; href?: string; title?: string }) {
  const cls =
    "inline-flex h-6 flex-none items-center gap-1 rounded-md border border-border bg-surface px-1.5 text-[12px] font-semibold text-primary transition-colors hover:border-primary hover:bg-primary-soft cursor-pointer";
  if (href)
    return (
      <a className={cls} href={href} target="_blank" rel="noopener noreferrer" title={title ?? "원문 보기"}>
        <FileText className="size-3" aria-hidden />
        {label}
      </a>
    );
  return (
    <button type="button" className={cls} onClick={onClick} title={title ?? "원문 보기"}>
      <FileText className="size-3" aria-hidden />
      {label}
    </button>
  );
}

/** 과목 칩 — 과목 색 점 + 이름 */
export function CourseChip({ name, color, className = "" }: { name: string; color?: string; className?: string }) {
  return (
    <span className={`inline-flex min-w-0 items-center gap-1.5 text-[13px] font-medium text-muted ${className}`}>
      <span className="size-2 flex-none rounded-full" style={{ background: color ?? "var(--faint)" }} aria-hidden />
      <span className="truncate">{name}</span>
    </span>
  );
}
