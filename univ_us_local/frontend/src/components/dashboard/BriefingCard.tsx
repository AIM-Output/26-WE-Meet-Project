"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { Bell, BookOpen, CalendarDays, ChevronDown, ChevronRight, Clock, Flame, Sun, TriangleAlert } from "lucide-react";
import { Chip } from "@/components/ui/Chip";
import { useStored } from "@/lib/storage";
import { generatedLabel, type Briefing, type BriefingIcon, type BriefingItem, type BriefingSection } from "@/lib/briefing";
import { useBriefingToday } from "@/lib/useBriefing";
import { parseLocal, WEEKDAY_KO } from "@/lib/dates";

// 오늘 브리핑 카드 — 커버 아래·3단 위 (Frontend-Route 15-3). 내용은 서버(C4)가 만든 스냅샷 그대로 그린다.
// 접기 상태는 기억한다(기본 펼침). LLM 한 줄이 없으면 그 줄만 빠진다(오류 문구 없음). 예정 시각 전·꺼짐이면 카드가 없다.

const ICON: Record<BriefingIcon, React.ReactNode> = {
  alert: <TriangleAlert aria-hidden />,
  class: <BookOpen aria-hidden />,
  calendar: <CalendarDays aria-hidden />,
  clock: <Clock aria-hidden />,
  flame: <Flame aria-hidden />,
  bell: <Bell aria-hidden />,
};

const TONE: Record<NonNullable<BriefingItem["tone"]>, string> = {
  danger: "text-danger-text",
  warn: "text-warn-text",
  muted: "text-faint",
};

const SHOW = 5; // 섹션당 최대 5줄 — 넘으면 '+N건 더' (F10 10절 분량)

function SectionBlock({ s }: { s: BriefingSection }) {
  const shown = s.items.slice(0, SHOW);
  const rest = s.count - shown.length;
  return (
    <section aria-labelledby={`briefing-${s.key}`} className="min-w-0">
      <h3
        id={`briefing-${s.key}`}
        className="mb-1.5 flex items-center gap-1.5 text-[13px] font-bold text-muted [&>svg]:size-4 [&>svg]:text-primary"
      >
        {ICON[s.icon]}
        {s.label}
        <span className="num text-faint">{s.count || ""}</span>
      </h3>
      {shown.length === 0 ? (
        <p className="text-[14px] text-faint">{s.empty}</p>
      ) : (
        <ul className="space-y-1">
          {shown.map((it, i) => (
            <li key={i} className="min-w-0 text-[14px] leading-snug">
              <Link href={it.href} className={`group flex min-w-0 items-baseline gap-1.5 hover:text-primary ${it.tone ? TONE[it.tone] : ""}`}>
                {it.tag && <span className="flex-none rounded bg-surface-3 px-1 text-[11px] font-semibold text-muted">{it.tag}</span>}
                <span className="truncate group-hover:underline">{it.text}</span>
                {it.sub && <span className="hidden min-w-0 truncate text-[12px] text-faint sm:inline">· {it.sub}</span>}
              </Link>
            </li>
          ))}
          {rest > 0 && (
            <li className="text-[13px] text-faint">
              {s.link ? (
                <Link href={s.link} className="hover:text-primary hover:underline">
                  +{rest}건 더
                </Link>
              ) : (
                `+${rest}건 더`
              )}
            </li>
          )}
        </ul>
      )}
      {s.footer && <p className="mt-1 text-[12px] text-faint">{s.footer}</p>}
    </section>
  );
}

/** 섹션들 — 대시보드 카드와 /briefing 이 같이 쓴다 */
export function BriefingSections({ b, compact }: { b: Briefing; compact?: boolean }) {
  if (b.empty) return <p className="text-[14px] text-muted">{b.emptyText ?? "오늘은 일정이 없습니다"}</p>;
  return (
    <div className={`grid gap-x-8 gap-y-4 ${compact ? "" : "md:grid-cols-2"}`}>
      {b.sections.map((s) => (
        <SectionBlock key={s.key} s={s} />
      ))}
    </div>
  );
}

/** 못 읽은 재료 — 실패를 숨기지 않는다(Frontend-Screens 5절 ③). 있는 섹션만 보여 준 이유 */
export function BriefingGaps({ b }: { b: Briefing }) {
  if (!b.gaps.length) return null;
  return <p className="hint mt-3">{b.gaps.join(" · ")} 을(를) 읽지 못해 그 내용은 빠졌습니다</p>;
}

export function GeneratedChip({ b, className = "" }: { b: Briefing; className?: string }) {
  const label = generatedLabel(b);
  if (b.missed && b.source !== "manual")
    return (
      <Chip tone="warn" className={className}>
        {label}
      </Chip>
    );
  return (
    <span className={`num text-[12px] text-faint ${className}`}>
      {b.missed && <Chip tone="warn" className="mr-1.5">놓친 브리핑</Chip>}
      {label}
    </span>
  );
}

const dateTitle = (date: string) => {
  const d = parseLocal(date);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${WEEKDAY_KO[d.getDay()]}요일 브리핑`;
};

export default function BriefingCard() {
  const { data, error, loading, reload } = useBriefingToday();
  const [collapsed, setCollapsed] = useStored("briefing-collapsed", false);

  if (loading && !data) return null;
  if (error && !data)
    return (
      <section className="card flex flex-wrap items-center gap-3 px-4 py-3 md:px-5" aria-label="오늘 브리핑">
        <Sun className="size-4 text-faint" aria-hidden />
        <span className="flex-1 text-[14px] text-muted">브리핑을 불러오지 못했습니다</span>
        <button type="button" className="btn btn-sm" onClick={() => void reload()}>
          다시 시도
        </button>
      </section>
    );
  if (!data) return null;
  if (data.state === "pending")
    return (
      <section className="card px-4 py-4 md:px-5" aria-label="오늘 브리핑" aria-busy="true">
        <div className="flex items-center gap-3">
          <div className="skeleton size-8 rounded-lg" />
          <div className="skeleton h-4 w-48" />
          <span className="ml-auto text-[12px] text-faint">{data.waitingFor.join(" · ")} 수집이 끝나면 만듭니다</span>
        </div>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <div className="skeleton h-3.5 w-4/5" />
          <div className="skeleton h-3.5 w-3/5" />
          <div className="skeleton h-3.5 w-2/3" />
          <div className="skeleton h-3.5 w-1/2" />
        </div>
      </section>
    );
  const b = data.briefing;
  if (data.state !== "ready" || !b) return null; // 예정 시각 전 · 꺼짐 — 카드 없음 (15-7)

  return (
    <section className="card overflow-hidden" aria-label="오늘 브리핑">
      <button
        type="button"
        className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-surface-2 md:px-5"
        aria-expanded={!collapsed}
        onClick={() => setCollapsed(!collapsed)}
      >
        <span className="grid size-8 flex-none place-items-center rounded-lg bg-accent-soft text-accent-text">
          <Sun className="size-4" aria-hidden />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-bold">{dateTitle(b.date)}</span>
          {collapsed && <span className="block truncate text-[13px] text-muted">{b.headline ?? b.summary}</span>}
        </span>
        <GeneratedChip b={b} className="hidden sm:inline-flex" />
        <ChevronDown className={`size-4 flex-none text-faint transition-transform ${collapsed ? "" : "rotate-180"}`} aria-hidden />
      </button>
      <AnimatePresence initial={false}>
        {!collapsed && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ type: "spring", bounce: 0, visualDuration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <div className="border-t border-border px-4 py-4 md:px-5">
              {b.headline && <p className="mb-3 text-[15px] font-semibold">{b.headline}</p>}
              <BriefingSections b={b} />
              <BriefingGaps b={b} />
              <div className="mt-3 flex justify-end">
                <Link href="/briefing" className="inline-flex items-center gap-0.5 text-[13px] font-semibold text-muted hover:text-primary">
                  지난 브리핑
                  <ChevronRight className="size-4" aria-hidden />
                </Link>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
