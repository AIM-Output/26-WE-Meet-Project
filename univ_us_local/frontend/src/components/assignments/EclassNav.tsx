"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { useAppData } from "@/components/app/AppData";

// E클래스 카테고리 안의 두 화면 — 과제·동영상(/assignments) · 공지·자료(/eclass/posts). 페이지 사이 이동이라 링크(push)다.

export function EclassNav() {
  const path = usePathname()?.replace(/\/$/, "") ?? "";
  const { status } = useAppData();
  const open = status?.eclass?.counts?.open;
  const unread = status?.eclass?.feed?.unread ?? 0;
  const items = [
    { href: "/assignments", label: "과제·동영상", badge: open ? String(open) : null, alert: false },
    { href: "/eclass/posts", label: "공지·자료", badge: unread ? `새 ${unread}` : null, alert: unread > 0 },
  ];
  return (
    <nav aria-label="E클래스" className="no-scrollbar -mt-2 mb-6 flex gap-1 overflow-x-auto border-b border-border">
      {items.map((it) => {
        const on = path === it.href;
        return (
          <Link
            key={it.href}
            href={it.href}
            aria-current={on ? "page" : undefined}
            className={`relative flex h-10 flex-none items-center gap-1.5 px-3 text-[14px] font-semibold ${on ? "text-text" : "text-muted hover:text-text"}`}
          >
            {it.label}
            {it.badge && (
              <span className={`num rounded-full px-1.5 text-[11px] font-bold ${it.alert ? "bg-accent-text text-on-accent" : "bg-surface-3 text-muted"}`}>{it.badge}</span>
            )}
            {on && <motion.span layoutId="eclass-tab" className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-primary" />}
          </Link>
        );
      })}
    </nav>
  );
}
