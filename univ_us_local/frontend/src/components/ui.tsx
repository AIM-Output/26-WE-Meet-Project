"use client";

import { useEffect, type ReactNode } from "react";

/** 가운데 뜨는 다이얼로그. Esc·바깥 클릭으로 닫힌다. */
export function Modal({ onClose, children, width }: { onClose: () => void; children: ReactNode; width?: number }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="dialog" style={width ? { maxWidth: width } : undefined} role="dialog" aria-modal="true">
        {children}
      </div>
    </div>
  );
}

/** 참고 페이지의 작은 회색 선 아이콘 */
export function Icon({ name }: { name: "calendar" | "check" | "grid" | "chart" }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  switch (name) {
    case "calendar":
      return (
        <svg {...common} className="ico" aria-hidden>
          <rect x="3" y="5" width="18" height="16" rx="2" />
          <path d="M3 10h18M8 3v4M16 3v4" />
        </svg>
      );
    case "check":
      return (
        <svg {...common} className="ico" aria-hidden>
          <rect x="3" y="3" width="18" height="18" rx="3" />
          <path d="m8 12 3 3 5-6" />
        </svg>
      );
    case "grid":
      return (
        <svg {...common} className="ico" aria-hidden>
          <rect x="3" y="3" width="7" height="7" rx="1.5" />
          <rect x="14" y="3" width="7" height="7" rx="1.5" />
          <rect x="3" y="14" width="7" height="7" rx="1.5" />
          <rect x="14" y="14" width="7" height="7" rx="1.5" />
        </svg>
      );
    case "chart":
      return (
        <svg {...common} className="ico" aria-hidden>
          <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
        </svg>
      );
  }
}

/** ☑ C A L E N D A R 식 섹션 제목 + 구분선. 오른쪽에 탭/버튼을 둘 수 있다. */
export function SectionTitle({ icon, children, action }: { icon?: ReactNode; children: ReactNode; action?: ReactNode }) {
  return (
    <div className="mb-3">
      <div className="flex min-h-10 items-center justify-between gap-3">
        <h2 className="sec-title">
          {icon}
          <span>{children}</span>
        </h2>
        {action}
      </div>
      <div className="divider mt-2" />
    </div>
  );
}

/** 콜아웃 (Notion callout: 아이콘 + 제목, 들여쓴 구분선과 본문) */
export function Callout({ icon, title, children }: { icon: ReactNode; title: ReactNode; children: ReactNode }) {
  return (
    <section className="callout">
      <div className="callout-head">
        <span className="ico" aria-hidden>
          {icon}
        </span>
        <span>{title}</span>
      </div>
      <div className="callout-body">
        <div className="divider" />
        {children}
      </div>
    </section>
  );
}

export function Card({
  title,
  action,
  children,
  className = "",
}: {
  title?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card p-5 ${className}`}>
      {(title || action) && (
        <header className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-[15px] font-bold tracking-tight text-muted">{title}</h2>
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function Chip({ children, bg, fg, small }: { children: ReactNode; bg: string; fg: string; small?: boolean }) {
  return (
    <span className={`chip ${small ? "chip-sm" : ""}`} style={{ background: bg, color: fg }}>
      {children}
    </span>
  );
}

/** Notion 태그 (색 이름으로) */
export function Tag({ color, children }: { color: "blue" | "yellow" | "red" | "green" | "gray" | "orange"; children: ReactNode }) {
  return <span className={`tag tag-${color}`}>{children}</span>;
}

export function Dot({ color, size = 8 }: { color: string; size?: number }) {
  return (
    <span
      className="inline-block flex-none rounded-full"
      style={{ width: size, height: size, background: color }}
      aria-hidden
    />
  );
}
