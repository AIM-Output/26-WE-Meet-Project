"use client";

import { useState } from "react";
import Link from "next/link";
import { CalendarDays, Check, ExternalLink, EyeOff, Paperclip, Pencil, SquareCheck, Trash2 } from "lucide-react";
import { Modal } from "@/components/ui/Modal";
import { Chip, CourseChip, DdayChip, StatusBadge } from "@/components/ui/Chip";
import { KV } from "@/components/ui/Layout";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { closeQuery, useQueryValue } from "@/lib/useQueryState";
import { useAcademic } from "@/lib/useAcademic";
import { useAssignments } from "@/lib/useAssignments";
import { api } from "@/lib/api";
import { ACADEMIC_TYPE_META, type AcademicEvent } from "@/lib/demo";
import type { CalEvent, UserEventInput } from "@/lib/types";
import { addDays, daysUntil, fmtDateTime, fmtHours, parseLocal } from "@/lib/dates";
import { ESTIMATE_OPTIONS } from "@/lib/priority";
import { EventForm, DEFAULT_CATEGORIES, type EventDraft } from "./EventForm";

// 일정 상세 — `?event=` 가 붙으면 열리고, 뒤로가기·ESC 로 닫힌다. 소스 5종이 같은 자리를 쓴다(Frontend-Route 4-4).
// `/`·`/academic`·`/assignments` 가 같은 컴포넌트를 쓴다.

export function EventDetailHost() {
  const id = useQueryValue("event");
  const [last, setLast] = useState(id);
  if (id && id !== last) setLast(id);
  const shown = id ?? last;
  const close = () => closeQuery(["event"]);

  const { events, loading } = useAppData();
  const { list: academic } = useAcademic();

  let body: React.ReactNode = null;
  let title: React.ReactNode = "일정";
  if (shown?.startsWith("ac:")) {
    const ev = academic.find((e) => e.id === shown);
    if (ev) {
      title = ev.title;
      body = <AcademicDetail ev={ev} onClose={close} />;
    }
  } else if (shown) {
    const ev = events.find((e) => e.id === shown);
    if (ev?.extendedProps.kind === "deadline") {
      title = ev.title;
      body = <DeadlineDetail ev={ev} />;
    } else if (ev) {
      return <UserDetail ev={ev} open={!!id} onClose={close} />;
    }
  }
  if (!body) body = <p className="py-8 text-center text-[14px] text-muted">{loading ? "불러오는 중…" : "일정을 찾을 수 없습니다. 삭제되었거나 수집 목록에서 빠졌을 수 있습니다."}</p>;

  return (
    <Modal open={!!id} onClose={close} title={title}>
      {body}
    </Modal>
  );
}

/* ---------------------------------------------------------------- F6 과제 */

function DeadlineDetail({ ev }: { ev: CalEvent }) {
  const toast = useToast();
  const { courseColor } = useAppData();
  const { list, setUserDone, setEstimate } = useAssignments();
  const [showAll, setShowAll] = useState(false);
  if (ev.extendedProps.kind !== "deadline") return null;
  const p = ev.extendedProps;
  const a = list.find((x) => x.id === ev.id);
  const due = parseLocal(p.due);
  const desc = (p.description || "").trim();

  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <CourseChip name={`${p.courseShort}${p.courseCode ? ` (${p.courseCode})` : ""}`} color={courseColor(p.courseShort) ?? p.courseColor} />
        <Chip square>{a?.kindLabel ?? p.type ?? "과제"}</Chip>
      </div>
      <KV
        rows={[
          [
            "마감",
            <span key="d" className="flex flex-wrap items-center gap-2 font-semibold">
              {fmtDateTime(due)} <DdayChip date={due} done={p.submitted || a?.userDone} />
            </span>,
          ],
          [
            "제출",
            p.submitted ? (
              <StatusBadge tone="ok">{p.status || "제출 완료"}</StatusBadge>
            ) : a?.userDone ? (
              <Chip tone="ok" dashed icon={<SquareCheck aria-hidden />}>
                내가 체크함
              </Chip>
            ) : daysUntil(due) < 0 ? (
              <StatusBadge tone="danger">{p.status || "미제출"} · 마감 지남</StatusBadge>
            ) : (
              <StatusBadge tone="warn">{p.status || "미제출"}</StatusBadge>
            ),
          ],
          ...(p.graded ? [["채점", p.graded] as [string, string]] : []),
          ...(p.attachmentCount > 0
            ? [["첨부", <span key="a" className="inline-flex items-center gap-1.5"><Paperclip className="size-3.5 text-faint" aria-hidden />{p.attachmentCount}개 (eclass_agent/data 에 저장됨)</span>] as [string, React.ReactNode]]
            : []),
          ...(a && !p.submitted
            ? [
                [
                  "소요",
                  <span key="e" className="flex flex-wrap items-center gap-2">
                    <select
                      className="field field-sm w-auto"
                      aria-label="예상 소요시간"
                      value={ESTIMATE_OPTIONS.includes(a.estimate as (typeof ESTIMATE_OPTIONS)[number]) ? a.estimate : ""}
                      onChange={(e) => setEstimate(ev.id, Number(e.target.value))}
                    >
                      {!ESTIMATE_OPTIONS.includes(a.estimate as (typeof ESTIMATE_OPTIONS)[number]) && <option value="">{fmtHours(a.estimate)}</option>}
                      {ESTIMATE_OPTIONS.map((h) => (
                        <option key={h} value={h}>
                          {fmtHours(h)}
                        </option>
                      ))}
                    </select>
                    <span className="text-[13px] text-muted">{a.reason}</span>
                  </span>,
                ] as [string, React.ReactNode],
              ]
            : []),
        ]}
      />
      {desc && (
        <div className="rounded-xl bg-surface-2 p-3 text-[14px] leading-relaxed whitespace-pre-wrap text-muted">
          {desc.length > 200 && !showAll ? `${desc.slice(0, 200)}…` : desc}
          {desc.length > 200 && (
            <button type="button" className="ml-1 font-semibold text-primary" onClick={() => setShowAll((v) => !v)}>
              {showAll ? "접기" : "더 보기"}
            </button>
          )}
        </div>
      )}
      {!p.submitted && (
        <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-dashed border-border-strong p-3">
          <input
            type="checkbox"
            className="mt-0.5 size-4 accent-[var(--ok)]"
            checked={!!a?.userDone}
            onChange={(e) => {
              const v = e.target.checked;
              setUserDone(ev.id, v);
              if (v) toast("완료로 표시했습니다", { tone: "success", action: { label: "되돌리기", onClick: () => setUserDone(ev.id, false) } });
            }}
          />
          <span>
            <span className="block text-[14px] font-semibold">내가 체크함</span>
            <span className="text-[13px] text-muted">e클래스 밖에서 제출한 경우. 다음 수집에서 제출이 확인되면 &lsquo;제출 완료&rsquo;로 바뀝니다.</span>
          </span>
        </label>
      )}
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <span className="text-[13px] text-faint">e클래스에서 가져온 일정은 여기서 고칠 수 없습니다.</span>
        {p.url && (
          <a className="btn btn-primary" href={p.url} target="_blank" rel="noopener noreferrer">
            e클래스에서 열기
            <ExternalLink aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- F1 학사 */

function AcademicDetail({ ev, onClose }: { ev: AcademicEvent; onClose: () => void }) {
  const toast = useToast();
  const { update } = useAcademic();
  const meta = ACADEMIC_TYPE_META[ev.type];
  const s = parseLocal(ev.start);
  const e = ev.end ? parseLocal(ev.end) : null;
  const when = `${fmtDateTime(s, !ev.allDay)}${e ? ` ~ ${fmtDateTime(e, !ev.allDay)}` : ""}`;

  return (
    <div className="space-y-4 pt-1">
      <div className="flex flex-wrap items-center gap-2">
        <span className="chip chip-square text-white" style={{ background: meta.color }}>
          {meta.label}
        </span>
        {ev.changedFrom && <Chip tone="warn">변경됨</Chip>}
        <Chip tone="neutral" square>예시</Chip>
      </div>
      <p className="text-[15px] font-semibold">
        {when}
        {ev.changedFrom && <span className="ml-2 text-[13px] font-normal text-faint line-through">{ev.changedFrom}</span>}
      </p>
      <KV
        rows={[
          [
            "대상",
            <span key="t" className="flex flex-wrap items-center gap-2">
              {ev.target}
              {ev.appliesToMe === true && <StatusBadge tone="ok">내 해당</StatusBadge>}
              {ev.appliesToMe === false && <StatusBadge tone="neutral">해당 없음</StatusBadge>}
              {ev.appliesToMe === null && <StatusBadge tone="warn" unknown>판단 불가</StatusBadge>}
            </span>,
          ],
          ["신뢰도", <span key="c" className="num">{ev.confidence.toFixed(2)}</span>],
          ...(ev.evidence ? [["근거", <q key="q" className="text-muted">{ev.evidence}</q>] as [string, React.ReactNode]] : []),
          [
            "출처",
            <a key="s" href={ev.sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 font-semibold text-primary hover:underline">
              {ev.source}
              <ExternalLink className="size-3.5" aria-hidden />
            </a>,
          ],
        ]}
      />
      <div className="border-t border-border pt-4">
        <span className="label">알림</span>
        <div className="flex flex-wrap gap-2">
          {[7, 3, 1].map((d) => {
            const on = ev.reminders.includes(d);
            return (
              <button
                key={d}
                type="button"
                aria-pressed={on}
                className={`btn btn-sm ${on ? "border-primary bg-primary-soft text-primary hover:bg-primary-soft" : ""}`}
                onClick={() => update(ev.id, { reminders: on ? ev.reminders.filter((x) => x !== d) : [...ev.reminders, d] })}
              >
                {on && <Check aria-hidden />}D-{d}
              </button>
            );
          })}
        </div>
      </div>
      <div>
        <label className="label" htmlFor="ac-memo">
          메모
        </label>
        <textarea id="ac-memo" className="field" defaultValue={ev.memo} onBlur={(e) => update(ev.id, { memo: e.target.value })} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            const prev = ev.status;
            update(ev.id, { status: "hidden" });
            onClose();
            toast("숨겼습니다", { action: { label: "되돌리기", onClick: () => update(ev.id, { status: prev }) } });
          }}
        >
          <EyeOff aria-hidden />
          숨기기
        </button>
        <Link href={`/?date=${ev.start.slice(0, 7)}&filter=academic`} className="btn">
          <CalendarDays aria-hidden />
          캘린더에서 보기
        </Link>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 내 일정·할 일 */

function UserDetail({ ev, open, onClose }: { ev: CalEvent; open: boolean; onClose: () => void }) {
  const toast = useToast();
  const { refresh, status } = useAppData();
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  if (ev.extendedProps.kind !== "user") return null;
  const p = ev.extendedProps;
  const categories = status?.categories ?? DEFAULT_CATEGORIES;

  if (editing) {
    const start = parseLocal(ev.start);
    let end: Date | null = ev.end ? parseLocal(ev.end) : null;
    if (ev.allDay && end) end = addDays(end, -1);
    const draft: EventDraft = { title: ev.title, start, end, allDay: ev.allDay, category: p.category, memo: p.memo, isTodo: p.isTodo, done: p.done };
    return (
      <EventForm
        open={open}
        mode="edit"
        draft={draft}
        categories={categories}
        onClose={() => setEditing(false)}
        onSave={async (input: UserEventInput) => {
          await api.updateEvent(ev.id, input);
          await refresh();
          setEditing(false);
          toast("저장했습니다", { tone: "success" });
        }}
      />
    );
  }

  const s = parseLocal(ev.start);
  let when: string;
  if (ev.allDay) {
    const last = ev.end ? addDays(parseLocal(ev.end), -1) : null;
    when = last && last > s ? `${fmtDateTime(s, false)} ~ ${fmtDateTime(last, false)} · 종일` : `${fmtDateTime(s, false)} · 종일`;
  } else {
    when = ev.end ? `${fmtDateTime(s)} ~ ${fmtDateTime(parseLocal(ev.end)).split(") ")[1] ?? ""}` : fmtDateTime(s);
  }

  const toggleDone = async (done: boolean) => {
    try {
      await api.updateEvent(ev.id, { done });
      await refresh();
    } catch (e) {
      toast(`저장하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
    }
  };

  return (
    <Modal open={open} onClose={onClose} title={<span className={p.isTodo && p.done ? "text-muted line-through" : ""}>{ev.title}</span>}>
      <div className="space-y-4 pt-1">
        <div className="flex flex-wrap items-center gap-2">
          <Chip square>
            <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden />
            {p.categoryLabel}
          </Chip>
          <Chip tone={p.isTodo ? "accent" : "primary"} square>
            {p.isTodo ? "할 일" : "내 일정"}
          </Chip>
        </div>
        <p className="text-[15px] font-semibold">{when}</p>
        {p.isTodo && (
          <label className="flex cursor-pointer items-center gap-3 rounded-xl bg-surface-2 px-3 py-2.5 text-[14px] font-semibold">
            <input type="checkbox" className="size-4 accent-[var(--ok)]" checked={p.done} onChange={(e) => toggleDone(e.target.checked)} />
            {p.done ? "완료됨 — 체크를 풀면 다시 할 일로" : "완료로 표시"}
          </label>
        )}
        {p.memo && <p className="rounded-xl bg-surface-2 p-3 text-[14px] whitespace-pre-wrap text-muted">{p.memo}</p>}
        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border pt-4">
          {confirm ? (
            <div className="flex items-center gap-2 text-[14px]">
              <span className="font-semibold text-danger-text">정말 삭제할까요?</span>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  try {
                    await api.deleteEvent(ev.id);
                    onClose();
                    await refresh();
                    toast("삭제했습니다");
                  } catch (e) {
                    setBusy(false);
                    toast(`삭제하지 못했습니다: ${e instanceof Error ? e.message : String(e)}`, { tone: "error" });
                  }
                }}
              >
                삭제
              </button>
              <button type="button" className="btn btn-sm" onClick={() => setConfirm(false)} disabled={busy}>
                취소
              </button>
            </div>
          ) : (
            <button type="button" className="btn btn-ghost btn-danger" onClick={() => setConfirm(true)}>
              <Trash2 aria-hidden />
              삭제
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={() => setEditing(true)}>
            <Pencil aria-hidden />
            수정
          </button>
        </div>
      </div>
    </Modal>
  );
}
