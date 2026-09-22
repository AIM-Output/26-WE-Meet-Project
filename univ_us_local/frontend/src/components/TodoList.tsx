"use client";

import { useMemo, useState } from "react";
import { Dot, Icon, SectionTitle, Tag } from "./ui";
import type { CalEvent, DeadlineProps, UserProps } from "@/lib/types";
import { daysUntil, ddayLabel, fmtTime, parseLocal } from "@/lib/dates";

interface Props {
  events: CalEvent[];
  onOpenEvent: (id: string) => void;
  onToggleDone: (ev: CalEvent, done: boolean) => void;
  onNewTodo: () => void;
}

type Item = { ev: CalEvent; when: Date; done: boolean; kind: "todo" | "deadline" };

/** 오른쪽 컬럼 — 참고 페이지의 TO DO LIST (갤러리 카드, 탭: 할 일 / 완료).
 *  내 할 일(is_todo) 과 e클래스 과제(미제출 = 할 일, 제출 완료 = 완료)를 한 목록으로 본다. */
export default function TodoList({ events, onOpenEvent, onToggleDone, onNewTodo }: Props) {
  const [tab, setTab] = useState<"open" | "done">("open");

  const items = useMemo(() => {
    const out: Item[] = [];
    for (const ev of events) {
      const p = ev.extendedProps;
      if (p.kind === "deadline") {
        out.push({ ev, when: parseLocal((p as DeadlineProps).due), done: (p as DeadlineProps).submitted, kind: "deadline" });
      } else if ((p as UserProps).isTodo) {
        out.push({ ev, when: parseLocal(ev.start), done: (p as UserProps).done, kind: "todo" });
      }
    }
    return out;
  }, [events]);

  const open = items.filter((i) => !i.done).sort((a, b) => a.when.getTime() - b.when.getTime());
  const done = items.filter((i) => i.done).sort((a, b) => b.when.getTime() - a.when.getTime());
  const list = tab === "open" ? open : done;

  return (
    <div>
      <SectionTitle
        icon={<Icon name="check" />}
        action={
          <div role="tablist" className="flex gap-0.5">
            <button type="button" role="tab" aria-selected={tab === "open"} className="tab" onClick={() => setTab("open")}>
              할 일{open.length > 0 && <span className="ml-1 text-faint">{open.length}</span>}
            </button>
            <button type="button" role="tab" aria-selected={tab === "done"} className="tab" onClick={() => setTab("done")}>
              완료
            </button>
          </div>
        }
      >
        To Do List
      </SectionTitle>

      <div className="pt-12">
        {list.length === 0 ? (
          <div className="rounded-lg border border-dashed border-border px-3 py-10 text-center text-[14px] text-faint">
            {tab === "open" ? (
              <>
                남은 할 일이 없습니다.
                <br />
                <button type="button" className="mt-2 font-semibold text-text" onClick={onNewTodo}>
                  + 할 일 추가
                </button>
              </>
            ) : (
              "완료한 항목이 여기에 쌓입니다."
            )}
          </div>
        ) : (
          <ul className="space-y-2">
            {list.map(({ ev, when, done, kind }) => {
              const d = daysUntil(when);
              const overdue = !done && d < 0;
              const tagColor = done ? "green" : overdue || d <= 1 ? "red" : d <= 3 ? "yellow" : "blue";
              const p = ev.extendedProps;
              const color = p.kind === "deadline" ? p.courseColor : p.color;
              const sub = p.kind === "deadline" ? p.courseShort : p.categoryLabel;
              return (
                <li key={ev.id} className="tcard">
                  <div className="flex items-start gap-2.5">
                    {kind === "todo" ? (
                      <input
                        type="checkbox"
                        className="mt-[3px] size-4 flex-none cursor-pointer accent-[#2383e2]"
                        checked={done}
                        onChange={(e) => onToggleDone(ev, e.target.checked)}
                        aria-label={done ? "완료 취소" : "완료"}
                      />
                    ) : (
                      <span
                        className={`mt-[3px] flex size-4 flex-none items-center justify-center rounded-[3px] border text-[10px] ${
                          done ? "border-ok bg-ok-soft text-ok" : "border-border text-faint"
                        }`}
                        title={done ? "e클래스 제출 완료" : "e클래스에서 제출하면 완료로 바뀝니다"}
                      >
                        {done ? "✓" : "e"}
                      </span>
                    )}
                    <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onOpenEvent(ev.id)}>
                      <span className={`block text-[15px] font-medium leading-snug ${done ? "text-muted line-through" : ""}`}>
                        {ev.title}
                      </span>
                      <span className="mt-2 flex items-center gap-1.5 text-[13px] text-muted">
                        <Dot color={color} size={6} />
                        <span className="truncate">{sub}</span>
                      </span>
                      <span className="mt-2 flex flex-wrap items-center gap-1.5">
                        <Tag color={tagColor}>{done ? "완료" : ddayLabel(d)}</Tag>
                        <Tag color="gray">
                          {when.getMonth() + 1}/{when.getDate()}
                          {!ev.allDay && ` ${fmtTime(when)}`}
                        </Tag>
                      </span>
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
