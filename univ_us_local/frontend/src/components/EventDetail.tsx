"use client";

import { useState } from "react";
import { Chip, Dot, Modal } from "./ui";
import type { CalEvent } from "@/lib/types";
import { addDays, daysUntil, ddayLabel, fmtDateTime, parseLocal } from "@/lib/dates";

interface Props {
  event: CalEvent;
  onEdit: (event: CalEvent) => void;
  onDelete: (event: CalEvent) => Promise<void>;
  onToggleDone: (event: CalEvent, done: boolean) => void;
  onClose: () => void;
}

function whenText(ev: CalEvent): string {
  const s = parseLocal(ev.start);
  if (ev.allDay) {
    if (!ev.end) return `${fmtDateTime(s, false)} · 종일`;
    const last = addDays(parseLocal(ev.end), -1);
    return `${fmtDateTime(s, false)} ~ ${fmtDateTime(last, false)} · 종일`;
  }
  if (!ev.end) return fmtDateTime(s);
  const e = parseLocal(ev.end);
  return `${fmtDateTime(s)} ~ ${e.toDateString() === s.toDateString() ? fmtDateTime(e).split(") ")[1] : fmtDateTime(e)}`;
}

export default function EventDetail({ event, onEdit, onDelete, onToggleDone, onClose }: Props) {
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [showDesc, setShowDesc] = useState(false);
  const p = event.extendedProps;

  if (p.kind === "deadline") {
    const due = parseLocal(p.due);
    const d = daysUntil(due);
    const overdue = !p.submitted && d < 0;
    const statusChip = p.submitted
      ? { bg: "var(--ok-soft)", fg: "var(--ok)", text: p.status || "제출 완료" }
      : overdue
        ? { bg: "var(--danger-soft)", fg: "var(--danger)", text: `${p.status || "미제출"} · 마감 지남` }
        : { bg: "var(--warn-soft)", fg: "var(--warn)", text: p.status || "미제출" };
    const desc = (p.description || "").trim();
    const short = desc.length > 160 && !showDesc ? desc.slice(0, 160) + "…" : desc;

    return (
      <Modal onClose={onClose} width={580}>
        <div className="p-5">
          <div className="mb-1 flex items-center gap-2 text-[14px] font-semibold text-muted">
            <Dot color={p.courseColor} />
            <span>{p.courseShort}</span>
            {p.courseCode && <span className="text-faint">{p.courseCode}</span>}
            <span className="ml-auto rounded-md bg-gray-100 px-1.5 py-0.5 text-[13px] font-bold text-gray-600">
              e클래스 {p.type || "마감"}
            </span>
          </div>
          <h2 className="text-2xl font-bold leading-snug">{event.title}</h2>

          <div className="mt-4 grid grid-cols-[80px_1fr] gap-y-2 text-[15px]">
            <span className="text-muted">마감</span>
            <span className="font-semibold">
              {fmtDateTime(due)}{" "}
              <span className={overdue ? "text-danger" : d <= 3 ? "text-warn" : "text-muted"}>({ddayLabel(d)})</span>
            </span>
            <span className="text-muted">제출</span>
            <span>
              <Chip bg={statusChip.bg} fg={statusChip.fg}>
                {statusChip.text}
              </Chip>
            </span>
            {p.graded && (
              <>
                <span className="text-muted">채점</span>
                <span>{p.graded}</span>
              </>
            )}
            {p.attachmentCount > 0 && (
              <>
                <span className="text-muted">첨부</span>
                <span>{p.attachmentCount}개 (eclass_agent/data 에 저장됨)</span>
              </>
            )}
          </div>

          {desc && (
            <div className="mt-4 rounded-xl bg-gray-50 p-3 text-[15px] leading-relaxed whitespace-pre-wrap text-gray-700">
              {short}
              {desc.length > 160 && (
                <button type="button" className="ml-1 font-semibold text-accent" onClick={() => setShowDesc((v) => !v)}>
                  {showDesc ? "접기" : "더 보기"}
                </button>
              )}
            </div>
          )}

          <div className="mt-5 flex items-center justify-between gap-2">
            <span className="text-[14px] text-faint">e클래스에서 수집한 일정은 여기서 수정할 수 없습니다.</span>
            <div className="flex gap-2">
              <button type="button" className="btn" onClick={onClose}>
                닫기
              </button>
              {p.url && (
                <a className="btn btn-primary" href={p.url} target="_blank" rel="noreferrer">
                  e클래스에서 열기 ↗
                </a>
              )}
            </div>
          </div>
        </div>
      </Modal>
    );
  }

  return (
    <Modal onClose={onClose}>
      <div className="p-5">
        <div className="mb-1 flex items-center gap-2 text-[14px] font-semibold text-muted">
          <Dot color={p.color} />
          <span>{p.categoryLabel}</span>
          <span className="ml-auto rounded-md bg-gray-100 px-1.5 py-0.5 text-[13px] font-bold text-gray-600">
            {p.isTodo ? "할 일" : "내 일정"}
          </span>
        </div>
        <h2 className={`text-2xl font-bold leading-snug ${p.isTodo && p.done ? "text-muted line-through" : ""}`}>{event.title}</h2>
        {p.isTodo && (
          <label className="mt-3 inline-flex cursor-pointer items-center gap-2 rounded-lg bg-panel px-3 py-2 text-[15px] font-semibold">
            <input type="checkbox" className="size-5 accent-ok" checked={p.done} onChange={(e) => onToggleDone(event, e.target.checked)} />
            {p.done ? "완료됨 — 체크를 풀면 다시 할 일로" : "완료로 표시"}
          </label>
        )}
        <p className="mt-2 text-[15px] font-semibold">{whenText(event)}</p>
        {p.memo && <p className="mt-3 rounded-xl bg-gray-50 p-3 text-[15px] whitespace-pre-wrap text-gray-700">{p.memo}</p>}

        <div className="mt-5 flex items-center justify-between gap-2">
          {confirm ? (
            <div className="flex items-center gap-2 text-[15px]">
              <span className="text-danger">정말 삭제할까요?</span>
              <button
                type="button"
                className="btn btn-sm btn-danger"
                disabled={busy}
                onClick={async () => {
                  setBusy(true);
                  await onDelete(event);
                }}
              >
                삭제
              </button>
              <button type="button" className="btn btn-sm" onClick={() => setConfirm(false)} disabled={busy}>
                취소
              </button>
            </div>
          ) : (
            <button type="button" className="btn btn-danger" onClick={() => setConfirm(true)}>
              삭제
            </button>
          )}
          <div className="flex gap-2">
            <button type="button" className="btn" onClick={onClose}>
              닫기
            </button>
            <button type="button" className="btn btn-primary" onClick={() => onEdit(event)}>
              수정
            </button>
          </div>
        </div>
      </div>
    </Modal>
  );
}
