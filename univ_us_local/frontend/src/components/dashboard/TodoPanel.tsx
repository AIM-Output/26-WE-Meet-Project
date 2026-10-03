"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Flame, Plus } from "lucide-react";
import { Tabs } from "@/components/ui/Tabs";
import { CourseChip, DdayChip } from "@/components/ui/Chip";
import { EmptyState } from "@/components/ui/Feedback";
import { useAppData } from "@/components/app/AppData";
import { useToast } from "@/components/ui/Toast";
import { useAssignments } from "@/lib/useAssignments";
import { isOpen, sortByPriority } from "@/lib/priority";
import { navigateQuery } from "@/lib/useQueryState";
import { api } from "@/lib/api";
import type { CalEvent, UserProps } from "@/lib/types";
import { deadlineDay, fmtDeadline, fmtDue, parseLocal } from "@/lib/dates";

// 오른쪽 컬럼 — 🔥 먼저 할 것 상위 3건(F7-S06) + 할 일 목록(내 할 일 + 미제출 과제).

const open = (id: string) => navigateQuery({ event: id }, "push");

export function TopPriority() {
  const { list } = useAssignments();
  const top = useMemo(() => sortByPriority(list.filter((a) => isOpen(a) && a.group !== "overdue")).slice(0, 3), [list]);
  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center gap-2">
        <Flame className="size-4 text-accent" aria-hidden />
        <h2 className="text-[13px] font-bold tracking-wide text-muted">먼저 할 것</h2>
      </div>
      {top.length === 0 ? (
        <p className="py-3 text-[14px] text-faint">지금 급한 과제가 없습니다</p>
      ) : (
        <ol className="space-y-1">
          {top.map((a, i) => (
            <li key={a.id}>
              <button type="button" onClick={() => open(a.id)} className="flex w-full items-start gap-3 rounded-lg px-2 py-2 text-left transition-colors hover:bg-surface-2">
                <span className={`num grid size-6 flex-none place-items-center rounded-full text-[12px] font-bold ${i === 0 ? "bg-accent-text text-white" : "bg-surface-3 text-muted"}`}>
                  {i + 1}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14px] font-semibold">{a.title}</span>
                  <span className="block truncate text-[12px] text-muted">
                    {a.p.courseShort} · {a.reason}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      <Link href="/assignments?sort=priority" className="mt-2 flex items-center justify-end gap-1 text-[13px] font-semibold text-primary hover:underline">
        과제 전체 보기
        <ArrowRight className="size-3.5" aria-hidden />
      </Link>
    </section>
  );
}

type Item = { id: string; title: string; when: Date; allDay: boolean; done: boolean; kind: "todo" | "deadline"; sub: string; color?: string; ev?: CalEvent };

export default function TodoPanel({ onNewTodo }: { onNewTodo: () => void }) {
  const { events, refresh, setEvents, courseColor } = useAppData();
  const toast = useToast();
  const { list } = useAssignments();
  const [tab, setTab] = useState<"open" | "done">("open");

  const items = useMemo(() => {
    const out: Item[] = [];
    for (const ev of events) {
      if (ev.extendedProps.kind === "user" && ev.extendedProps.isTodo)
        out.push({ id: ev.id, title: ev.title, when: parseLocal(ev.start), allDay: ev.allDay, done: ev.extendedProps.done, kind: "todo", sub: ev.extendedProps.categoryLabel, color: ev.extendedProps.color, ev });
    }
    for (const a of list)
      out.push({ id: a.id, title: a.title, when: a.due, allDay: false, done: !isOpen(a), kind: "deadline", sub: a.p.courseShort, color: courseColor(a.p.courseShort) ?? a.p.courseColor });
    return out;
  }, [events, list, courseColor]);

  const openItems = items.filter((i) => !i.done).sort((a, b) => a.when.getTime() - b.when.getTime());
  const doneItems = items.filter((i) => i.done).sort((a, b) => b.when.getTime() - a.when.getTime());
  const shown = tab === "open" ? openItems : doneItems.slice(0, 20);

  const toggle = async (it: Item, done: boolean) => {
    // 낙관적 — 화면을 먼저 바꾸고 실패하면 되돌린다(4-5)
    setEvents((xs) => xs.map((x) => (x.id === it.id ? { ...x, extendedProps: { ...(x.extendedProps as UserProps), done } } : x)));
    try {
      await api.updateEvent(it.id, { done });
      if (done) toast("완료했습니다", { tone: "success", action: { label: "되돌리기", onClick: () => toggle(it, false) } });
    } catch (e) {
      await refresh();
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  return (
    <section className="card p-4">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="text-[13px] font-bold tracking-wide text-muted">할 일</h2>
        <button type="button" className="btn btn-ghost btn-icon btn-sm ml-auto" onClick={onNewTodo} aria-label="할 일 추가">
          <Plus aria-hidden />
        </button>
      </div>
      <Tabs
        items={[
          { key: "open", label: "할 일", count: openItems.length },
          { key: "done", label: "완료" },
        ]}
        value={tab}
        onChange={setTab}
        label="할 일 목록"
        variant="pill"
        size="sm"
        className="mb-3"
      />
      {shown.length === 0 ? (
        <EmptyState
          compact
          title={tab === "open" ? "남은 할 일이 없습니다" : "완료한 항목이 여기에 쌓입니다"}
          action={
            tab === "open" && (
              <button type="button" className="btn btn-sm" onClick={onNewTodo}>
                <Plus aria-hidden />할 일 추가
              </button>
            )
          }
        />
      ) : (
        <ul className="thin-scroll -mx-1 max-h-[520px] space-y-1 overflow-y-auto px-1">
          <AnimatePresence initial={false}>
            {shown.map((it) => (
              <motion.li key={it.id} layout initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.15 }}>
                <div className="flex items-start gap-2.5 rounded-lg px-2 py-2 transition-colors hover:bg-surface-2">
                  {it.kind === "todo" ? (
                    <input
                      type="checkbox"
                      className="mt-1 size-4 flex-none cursor-pointer accent-[var(--primary)]"
                      checked={it.done}
                      onChange={(e) => toggle(it, e.target.checked)}
                      aria-label={`${it.title} ${it.done ? "완료 취소" : "완료"}`}
                    />
                  ) : (
                    <span
                      className={`mt-1 grid size-4 flex-none place-items-center rounded border text-[9px] font-bold ${it.done ? "border-ok bg-ok-soft text-ok-text" : "border-border-strong text-faint"}`}
                      title={it.done ? "제출·시청 완료" : "e클래스에서 제출(동영상은 시청)하면 완료로 바뀝니다"}
                      aria-hidden
                    >
                      e
                    </span>
                  )}
                  <button type="button" className="min-w-0 flex-1 text-left" onClick={() => open(it.id)}>
                    <span className={`block text-[14px] leading-snug font-medium ${it.done ? "text-faint line-through" : ""}`}>{it.title}</span>
                    <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1">
                      <CourseChip name={it.sub} color={it.color} className="max-w-[140px] text-[12px]" />
                      <span className="num text-[12px] text-faint">{it.allDay ? `${it.when.getMonth() + 1}/${it.when.getDate()}` : it.kind === "deadline" ? fmtDeadline(it.when) : fmtDue(it.when)}</span>
                    </span>
                  </button>
                  <DdayChip date={it.kind === "deadline" ? deadlineDay(it.when) : it.when} done={it.done} />
                </div>
              </motion.li>
            ))}
          </AnimatePresence>
        </ul>
      )}
    </section>
  );
}
