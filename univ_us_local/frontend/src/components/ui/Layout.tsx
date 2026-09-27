"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ChevronLeft } from "lucide-react";

// 페이지 뼈대. 모든 기능 페이지 제목 왼쪽에 `← 대시보드` (Frontend-Route 3-1) — GNB 가 없으므로 이게 되돌아가는 길이다.

export function Page({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <main id="main" className={`mx-auto w-full px-4 pt-6 pb-24 md:px-10 md:pt-8 ${wide ? "max-w-[1440px]" : "max-w-[1200px]"}`}>
      {children}
    </main>
  );
}

export function PageHeader({
  icon,
  title,
  subtitle,
  meta,
  actions,
  back = true,
}: {
  icon?: ReactNode;
  title: ReactNode;
  subtitle?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  back?: boolean;
}) {
  return (
    <header className="mb-6">
      {back && (
        <Link
          href="/"
          className="mb-3 inline-flex h-8 items-center gap-1 rounded-md pr-2 text-[13px] font-semibold text-muted transition-colors hover:text-primary"
        >
          <ChevronLeft className="size-4" aria-hidden />
          대시보드
        </Link>
      )}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="flex min-w-0 items-center gap-3">
          {icon && (
            <span className="grid size-10 flex-none place-items-center rounded-xl bg-primary-soft text-primary [&>svg]:size-5" aria-hidden>
              {icon}
            </span>
          )}
          <div className="min-w-0">
            <h1 className="text-[24px] font-bold leading-tight tracking-tight md:text-[28px]">{title}</h1>
            {subtitle && <p className="mt-0.5 text-[14px] text-muted">{subtitle}</p>}
          </div>
        </div>
        {(meta || actions) && (
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {meta && <div className="text-[13px] text-muted">{meta}</div>}
            {actions}
          </div>
        )}
      </div>
    </header>
  );
}

export function Section({
  title,
  icon,
  action,
  children,
  className = "",
  padded = true,
}: {
  title?: ReactNode;
  icon?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={`card min-w-0 ${padded ? "p-4 md:p-5" : ""} ${className}`}>
      {(title || action) && (
        <div className={`mb-3 flex flex-wrap items-center gap-2 ${padded ? "" : "px-4 pt-4 md:px-5"}`}>
          {icon && <span className="text-primary [&>svg]:size-[18px]" aria-hidden>{icon}</span>}
          {title && <h2 className="text-[15px] font-bold tracking-tight">{title}</h2>}
          {action && <div className="ml-auto flex items-center gap-2">{action}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/** 그룹 헤더 — `지금 해야 함 3 · 합계 6시간`. 접을 수 있다(④ 중요한 것만 펼친다). */
export function Group({
  title,
  count,
  extra,
  dot,
  defaultOpen = true,
  children,
  collapsible = false,
}: {
  title: ReactNode;
  count?: number;
  extra?: ReactNode;
  dot?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  collapsible?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const head = (
    <>
      {dot && <span className="size-2.5 flex-none rounded-full" style={{ background: dot }} aria-hidden />}
      <span className="text-[14px] font-bold">{title}</span>
      {count !== undefined && <span className="num text-[14px] font-bold text-faint">{count}</span>}
      {extra && <span className="text-[13px] font-medium text-muted">{extra}</span>}
      {collapsible && (
        <ChevronDown className={`ml-auto size-4 text-faint transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
      )}
    </>
  );
  return (
    <section className="mb-5">
      {collapsible ? (
        <button
          type="button"
          className="flex w-full items-center gap-2 rounded-lg px-1 py-2 text-left hover:bg-surface-3"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {head}
        </button>
      ) : (
        <div className="flex items-center gap-2 px-1 py-2">{head}</div>
      )}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", bounce: 0, visualDuration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <div className="pt-1">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}

/** 라벨 : 값 표 (모달 상세용) */
export function KV({ rows }: { rows: [ReactNode, ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[72px_1fr] gap-x-3 gap-y-2.5 text-[14px]">
      {rows.map(([k, v], i) => (
        <div key={i} className="contents">
          <dt className="pt-0.5 text-muted">{k}</dt>
          <dd className="min-w-0">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

/** 헤더·버튼에 붙는 팝오버 — 바깥 클릭·ESC 로 닫히고 트리거로 포커스를 돌려준다(6-12). */
export function Popover({
  trigger,
  children,
  align = "right",
  width = 360,
  label,
}: {
  trigger: (props: { open: boolean; toggle: () => void; ref: (el: HTMLButtonElement | null) => void }) => ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  width?: number;
  label: string;
}) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  // 트리거 버튼은 상태로 들고 있는다(닫을 때 포커스를 돌려주려고)
  const [btn, setBtn] = useState<HTMLButtonElement | null>(null);
  const close = useCallback(() => {
    setOpen(false);
    btn?.focus();
  }, [btn]);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!wrap.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open, close]);

  return (
    <div ref={wrap} className="relative">
      {trigger({ open, toggle: () => setOpen((v) => !v), ref: setBtn })}
      <AnimatePresence>
        {open && (
          <motion.div
            role="dialog"
            aria-label={label}
            initial={{ opacity: 0, scale: 0.96, y: -4 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.1 } }}
            transition={{ type: "spring", bounce: 0, visualDuration: 0.18 }}
            className={`absolute top-full z-50 mt-2 max-w-[calc(100vw-24px)] rounded-xl border border-border bg-surface ${
              align === "right" ? "right-0 origin-top-right" : "left-0 origin-top-left"
            }`}
            style={{ width, boxShadow: "var(--shadow-pop)" }}
          >
            {children(close)}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** 켜고 끄는 스위치 */
export function Toggle({ checked, onChange, label, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-10 flex-none items-center rounded-full transition-colors disabled:opacity-50 ${
        checked ? "bg-primary" : "bg-border-strong"
      }`}
    >
      <motion.span
        className="absolute left-0.5 size-5 rounded-full bg-white"
        style={{ boxShadow: "0 1px 2px rgba(0,0,0,0.2)" }}
        animate={{ x: checked ? 16 : 0 }}
        transition={{ type: "spring", bounce: 0.15, visualDuration: 0.2 }}
      />
    </button>
  );
}
