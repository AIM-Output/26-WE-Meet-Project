"use client";

import { useState } from "react";
import { Modal } from "@/components/ui/Modal";
import type { CategoryInfo, CategoryKey, UserEventInput } from "@/lib/types";
import { addDays, parseLocal, toDateStr, toLocalIso } from "@/lib/dates";

// 새 일정·할 일 / 수정 폼 — 제목 · 일시 · 분류 · 메모 (Frontend-Screens 1차 #3).

export interface EventDraft {
  title: string;
  start: Date;
  end: Date | null; // 종일이면 '표시용 마지막 날'(exclusive 아님)
  allDay: boolean;
  category: CategoryKey;
  memo: string;
  isTodo: boolean;
  done: boolean;
}

export const DEFAULT_CATEGORIES: Record<CategoryKey, CategoryInfo> = {
  personal: { label: "개인", color: "#33644d" },
  study: { label: "학업", color: "#3d6b8c" },
  team: { label: "팀플", color: "#9a6a14" },
  etc: { label: "기타", color: "#6b6560" },
};

const pad = (n: number) => String(n).padStart(2, "0");
const timeOf = (d: Date) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;

export function EventForm({
  open,
  mode,
  draft,
  categories,
  onSave,
  onClose,
  heading,
}: {
  open: boolean;
  mode: "create" | "edit";
  draft: EventDraft;
  categories: Record<CategoryKey, CategoryInfo>;
  onSave: (input: UserEventInput) => Promise<void>;
  onClose: () => void;
  /** 모달 제목을 바꿀 때 — 학사 일정 '내 일정에 넣기' */
  heading?: string;
}) {
  return (
    <Modal open={open} onClose={onClose} title={heading ?? (mode === "create" ? (draft.isTodo ? "새 할 일" : "새 일정") : draft.isTodo ? "할 일 수정" : "일정 수정")}>
      {/* key 로 초안이 바뀔 때마다 입력값을 새로 잡는다 */}
      <FormBody key={`${mode}-${draft.start.getTime()}-${draft.isTodo}`} mode={mode} draft={draft} categories={categories} onSave={onSave} onClose={onClose} />
    </Modal>
  );
}

function FormBody({
  mode,
  draft,
  categories,
  onSave,
  onClose,
}: {
  mode: "create" | "edit";
  draft: EventDraft;
  categories: Record<CategoryKey, CategoryInfo>;
  onSave: (input: UserEventInput) => Promise<void>;
  onClose: () => void;
}) {
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
  const [titleError, setTitleError] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) {
      setTitleError(true);
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
    <form onSubmit={submit} className="space-y-5 pt-2" noValidate>
      <div>
        <label className="label" htmlFor="ev-title">
          제목
        </label>
        <input
          id="ev-title"
          data-autofocus
          className="field"
          value={title}
          aria-invalid={titleError}
          aria-describedby={titleError ? "ev-title-err" : undefined}
          onChange={(e) => {
            setTitle(e.target.value);
            if (e.target.value.trim()) setTitleError(false);
          }}
          placeholder="예) 팀 회의, 운영체제 과제 시작"
        />
        {titleError && (
          <p id="ev-title-err" className="mt-1.5 text-[13px] font-medium text-danger-text">
            제목을 입력하세요.
          </p>
        )}
      </div>

      <div className="flex flex-wrap gap-2" role="group" aria-label="종류">
        {[
          { v: false, label: "일정" },
          { v: true, label: "할 일" },
        ].map((o) => (
          <button
            key={o.label}
            type="button"
            aria-pressed={isTodo === o.v}
            onClick={() => setIsTodo(o.v)}
            className={`btn btn-sm ${isTodo === o.v ? "border-primary bg-primary-soft text-primary hover:bg-primary-soft" : ""}`}
          >
            {o.label}
          </button>
        ))}
        <label className="ml-auto inline-flex cursor-pointer items-center gap-2 text-[14px] font-semibold">
          <input type="checkbox" checked={allDay} onChange={(e) => setAllDay(e.target.checked)} className="size-4 accent-[var(--primary)]" />
          종일
        </label>
        {isTodo && mode === "edit" && (
          <label className="inline-flex cursor-pointer items-center gap-2 text-[14px] font-semibold">
            <input type="checkbox" checked={done} onChange={(e) => setDone(e.target.checked)} className="size-4 accent-[var(--ok)]" />
            완료
          </label>
        )}
      </div>

      <fieldset className="space-y-3">
        <legend className="label">일시</legend>
        {[
          { label: "시작", date: startDate, setDate: setStartDate, time: startTime, setTime: setStartTime },
          { label: "종료", date: endDate, setDate: setEndDate, time: endTime, setTime: setEndTime },
        ].map((r) => (
          <div key={r.label} className="grid grid-cols-[40px_1fr] items-center gap-2">
            <span className="text-[13px] font-semibold text-muted">{r.label}</span>
            <div className="flex gap-2">
              <input type="date" aria-label={`${r.label} 날짜`} className="field min-w-0 flex-1" value={r.date} onChange={(e) => r.setDate(e.target.value)} />
              {!allDay && (
                <input type="time" aria-label={`${r.label} 시각`} className="field w-[128px] flex-none" value={r.time} onChange={(e) => r.setTime(e.target.value)} />
              )}
            </div>
          </div>
        ))}
        {allDay && <p className="hint pl-12">종료는 마지막 날짜입니다. 하루짜리면 시작과 같게 두세요.</p>}
      </fieldset>

      <div>
        <span className="label">분류</span>
        <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="분류">
          {(Object.keys(categories) as CategoryKey[]).map((k) => {
            const c = categories[k];
            const on = k === category;
            return (
              <button
                key={k}
                type="button"
                role="radio"
                aria-checked={on}
                onClick={() => setCategory(k)}
                className="btn btn-sm gap-2"
                style={on ? { borderColor: c.color, background: `${c.color}14`, color: c.color } : undefined}
              >
                <span className="size-2.5 rounded-full" style={{ background: c.color }} aria-hidden />
                {c.label}
              </button>
            );
          })}
        </div>
      </div>

      <div>
        <label className="label" htmlFor="ev-memo">
          메모 <span className="font-normal text-faint">(선택)</span>
        </label>
        <textarea id="ev-memo" className="field" value={memo} onChange={(e) => setMemo(e.target.value)} />
      </div>

      {error && <p className="rounded-lg bg-danger-soft px-3 py-2 text-[14px] text-danger-text">{error}</p>}

      <div className="flex justify-end gap-2 border-t border-border pt-4">
        <button type="button" className="btn" onClick={onClose} disabled={saving}>
          취소
        </button>
        <button type="submit" className="btn btn-primary" disabled={saving}>
          {saving && <span className="spin" aria-hidden />}
          {mode === "create" ? "추가" : "저장"}
        </button>
      </div>
    </form>
  );
}
