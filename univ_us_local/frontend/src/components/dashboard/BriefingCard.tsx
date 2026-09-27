"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { BookOpen, CalendarDays, ChevronDown, Clock, Flame, Sun } from "lucide-react";
import { Chip } from "@/components/ui/Chip";
import { useStored } from "@/lib/storage";
import type { Briefing, BriefingLine } from "@/lib/demo";
import { parseLocal, WEEKDAY_KO } from "@/lib/dates";

// F10 아침 브리핑 카드 — 커버 아래·3단 위. 접기 상태는 기억한다(기본 펼침). LLM 한 줄이 없으면 그 줄만 빠진다(15-3).

export function BriefingSections({ b, compact }: { b: Briefing; compact?: boolean }) {
  const rows: { icon: React.ReactNode; label: string; lines: BriefingLine[]; empty: string }[] = [
    { icon: <BookOpen aria-hidden />, label: "수업", lines: b.classes, empty: "시간표가 없어 수업을 알 수 없습니다" },
    { icon: <CalendarDays aria-hidden />, label: "일정", lines: b.events, empty: "없음" },
    { icon: <Clock aria-hidden />, label: "마감", lines: b.deadlines, empty: "3일 안에 마감 없음" },
    { icon: <Flame aria-hidden />, label: "먼저 할 것", lines: b.top, empty: "지금 급한 과제가 없습니다" },
  ];
  return (
    <dl className={`grid gap-x-6 gap-y-3 ${compact ? "" : "md:grid-cols-2"}`}>
      {rows.map((r) => (
        <div key={r.label} className="flex min-w-0 gap-3">
          <dt className="flex w-[92px] flex-none items-center gap-1.5 self-start pt-0.5 text-[13px] font-bold text-muted [&>svg]:size-4 [&>svg]:text-primary">
            {r.icon}
            {r.label}
            <span className="num text-faint">{r.lines.length || ""}</span>
          </dt>
          <dd className="min-w-0 flex-1 text-[14px]">
            {r.lines.length === 0 ? (
              <span className="text-faint">{r.empty}</span>
            ) : (
              <ul className="space-y-0.5">
                {r.lines.slice(0, 5).map((l, i) => (
                  <li key={i} className="truncate">
                    <Link href={l.href} className="hover:text-primary hover:underline">
                      {l.text}
                    </Link>
                  </li>
                ))}
                {r.lines.length > 5 && <li className="text-[13px] text-faint">+{r.lines.length - 5}건 더</li>}
              </ul>
            )}
          </dd>
        </div>
      ))}
    </dl>
  );
}

export default function BriefingCard({ b }: { b: Briefing | null }) {
  const [collapsed, setCollapsed] = useStored("briefing-collapsed", false);
  if (!b) return null; // 08:00 이전·꺼짐 — 카드 없음
  const d = parseLocal(b.date);
  const total = b.classes.length + b.events.length + b.deadlines.length;

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
          <span className="block text-[15px] font-bold">
            {d.getMonth() + 1}월 {d.getDate()}일 {WEEKDAY_KO[d.getDay()]}요일 브리핑
          </span>
          {collapsed && (
            <span className="text-[13px] text-muted">
              일정 {b.events.length} · 마감 {b.deadlines.length} · 먼저 할 것 {b.top.length}
            </span>
          )}
        </span>
        {b.source === "catchup" && (
          <Chip tone="warn" className="hidden sm:inline-flex">
            놓친 브리핑 · 08:00 예정 → 지금 생성
          </Chip>
        )}
        {b.live ? (
          <span className="hidden text-[12px] text-faint sm:inline" title="브리핑 API(GET /api/briefing/today)가 생기기 전까지 실제 일정·마감으로 화면에서 조립합니다">
            임시 조립 · 서버 생성 전
          </span>
        ) : (
          <span className="num hidden text-[12px] text-faint sm:inline">{b.generatedAt} 생성</span>
        )}
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
              {total === 0 && b.top.length === 0 ? <p className="text-[14px] text-muted">오늘은 일정이 없습니다</p> : <BriefingSections b={b} />}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </section>
  );
}
