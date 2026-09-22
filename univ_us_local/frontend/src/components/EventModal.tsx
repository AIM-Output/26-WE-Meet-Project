"use client";

import { useState } from "react";
import { Modal } from "./ui";
import type { CategoryInfo, CategoryKey, UserEventInput } from "@/lib/types";
import { addDays, parseLocal, toDateStr, toLocalIso } from "@/lib/dates";

export interface EventDraft {
  title: string;
  start: Date;
  end: Date | null; // 종일이면 exclusive 가 아니라 "표시용 마지막 날"
  allDay: boolean;
  category: CategoryKey;
  memo: string;
  isTodo: boolean;
  done: boolean;
}

interface Props {
  mode: "create" | "edit";
  draft: EventDraft;
  categories: Record<CategoryKey, CategoryInfo>;
  onSave: (input: UserEventInput) => Promise<void>;
  onClose: () => void;
}

const pad = (n: number) => String(n).padStart(2, "0");
const timeOf = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export default function EventModal({ mode, draft, categories, onSave, onClose }: Props) {
  const [title, setTitle] = useState(draft.title);
  const [allDay, setAllDay] = useState(draft.allDay);
  const [startDate, setStartDate] = useState(toDateStr(draft.start));
  const [startTime, setStartTime] = useState(timeOf(draft.start));
  const [endDate, setEndDate] = useState(toDateStr(draft.end ?? draft.start));
  const [endTime, setEndTime] = useState(timeOf(draft.end ?? new Date(draft.start.getTime() + 3_600_000)));
  const [category, setCategory] = useState<CategoryKey>(draft.category);
  const [memo, setMemo] = useState(draft.memo);
  const [isTodo, setIsTodo] = useState(draft.isTodo);
  const [done, setDone] = useState(draft.done);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setError("제목을 입력하세요.");
      return;
    }
    let start: string;
    let end: string | null;
    if (allDay) {
      start = startDate;
      const s = parseLocal(startDate);
      const en = parseLocal(endDate || startDate);
      end = en > s ? toDateStr(addDays(en, 1)) : null; // FullCalendar 규칙: 종일 end 는 exclusive
    } else {
      const s = parseLocal(`${startDate}T${startTime}`);
      const en = parseLocal(`${endDate || startDate}T${endTime}`);
      start = toLocalIso(s);
      end = en > s ? toLocalIso(en) : null;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave({ title: title.trim(), start, end, all_day: allDay, category, memo: memo.trim(), is_todo: isTodo, done: isTodo && done });
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSaving(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <form onSubmit={submit} className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-xl font-bold">
            {mode === "create" ? (isTodo ? "새 할 일" : "새 일정") : isTodo ? "할 일 수정" : "일정 수정"}
          </h2>
          <button type="button" className="btn btn-sm" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="label" htmlFor="ev-title">
              제목
            </label>
            <input
              id="ev-title"
              className="field"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="예) 팀 회의, 운영체제 과제 시작"
              autoFocus
            />
          </div>

          <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-[15px] font-semibold">
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} className="size-5 accent-accent" />
              종일
            </label>
            <label className="flex cursor-pointer items-center gap-2">
              <input type="checkbox" checked={isTodo} onChange={(e) => setIsTodo(e.target.checked)} className="size-5 accent-todo" />
              할 일 <span className="text-[13px] font-medium text-faint">(To Do List 에서 완료 체크)</span>
            </label>
            {isTodo && mode === "edit" && (
              <label className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" checked={done} onChange={(e) => setDone(e.target.checked)} className="size-5 accent-ok" />
                완료
              </label>
            )}
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-[60px_1fr] items-center gap-2">
              <span className="label mb-0">시작</span>
              <div className="flex gap-2">
                <input type="date" className="field min-w-0 flex-1" value={startDate} onChange={(e) => setStartDate(e.target.value)} required />
                {!allDay && (
                  <input type="time" className="field w-[136px] flex-none" value={startTime} onChange={(e) => setStartTime(e.target.value)} />
                )}
              </div>
            </div>
            <div className="grid grid-cols-[60px_1fr] items-center gap-2">
              <span className="label mb-0">종료</span>
              <div className="flex gap-2">
                <input type="date" className="field min-w-0 flex-1" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
                {!allDay && (
                  <input type="time" className="field w-[136px] flex-none" value={endTime} onChange={(e) => setEndTime(e.target.value)} />
                )}
              </div>
            </div>
            {allDay && <p className="pl-[68px] text-[14px] text-faint">종료는 마지막 날짜입니다. 하루짜리면 시작과 같게 두세요.</p>}
          </div>

          <div>
            <label className="label">분류</label>
            <div className="flex flex-wrap gap-2">
              {(Object.keys(categories) as CategoryKey[]).map((k) => {
                const c = categories[k];
                const on = k === category;
                return (
                  <button
                    key={k}
                    type="button"
                    onClick={() => setCategory(k)}
                    className="chip cursor-pointer border transition"
                    style={{
                      background: on ? c.color : "transparent",
                      color: on ? "#fff" : c.color,
                      borderColor: c.color,
                      height: 32,
                      paddingInline: 12,
                    }}
                  >
                    {c.label}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="label" htmlFor="ev-memo">
              메모
            </label>
            <textarea id="ev-memo" className="field" value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="선택" />
          </div>

          {error && <p className="rounded-lg bg-danger-soft px-3 py-2 text-[15px] text-danger">{error}</p>}
        </div>

        <div className="mt-5 flex justify-end gap-2">
          <button type="button" className="btn" onClick={onClose} disabled={saving}>
            취소
          </button>
          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving && <span className="spin" />}
            {mode === "create" ? "추가" : "저장"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
