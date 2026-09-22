"use client";

import { useMemo } from "react";
import { Callout } from "./ui";
import type { CalEvent, DeadlineProps, Status } from "@/lib/types";

interface Props {
  events: CalEvent[];
  status: Status | null;
  syncing: boolean;
  backendDown: boolean;
  onNewEvent: () => void;
  onNewTodo: () => void;
  onSync: () => void;
}

/** 왼쪽 컬럼 — 참고 페이지의 "일정, 할 일 등록"(버튼 2) / "하루 루틴 체크 하기"(버튼 4) / 월별 달성률 차트 */
export default function ActionPanel({ events, status, syncing, backendDown, onNewEvent, onNewTodo, onSync }: Props) {
  return (
    <div className="flex flex-col gap-4">
      <Callout icon="📝" title="일정, 할 일 등록">
        <div className="pill-list">
          <button type="button" className="pill" onClick={onNewEvent}>
            <span className="ico">↻</span>새 일정 등록 +
          </button>
          <button type="button" className="pill" onClick={onNewTodo}>
            <span className="ico">↻</span>새 할일 추가 +
          </button>
        </div>
      </Callout>

      <Callout icon="⏱️" title="빠른 실행">
        <div className="pill-list">
          <button type="button" className="pill" onClick={onSync} disabled={syncing || backendDown} title="eclass_agent/run-sync.cmd 실행">
            <span className="ico">{syncing ? <span className="spin spin-dark" /> : "↻"}</span>
            {syncing ? (status?.sync.source === "external" ? "예약 동기화 진행 중…" : "e클래스 동기화 중…") : "e클래스 동기화"}
            {!syncing && status?.updated_at && <span className="text-[12px] text-faint">{status.updated_at.slice(5, 16)}</span>}
          </button>
          <button type="button" className="pill" disabled title="F10 · 준비 중">
            <span className="ico">↻</span>아침 브리핑
          </button>
          <button type="button" className="pill" disabled title="F7 · 준비 중">
            <span className="ico">↻</span>과제 우선순위
          </button>
          <button type="button" className="pill" disabled title="F9 · 준비 중">
            <span className="ico">↻</span>자연어 질의
          </button>
        </div>
      </Callout>

      <CompletionChart events={events} status={status} />
    </div>
  );
}

/** 월별 완료율 — 참고 페이지의 "루틴 월별 달성률" 차트 자리. 이번 달 + 지난 3개월, 자료 없는 달은 숨긴다. */
function CompletionChart({ events, status }: { events: CalEvent[]; status: Status | null }) {
  const bars = useMemo(() => {
    const now = new Date();
    const months: { key: string; label: string; total: number; done: number }[] = [];
    for (let i = 3; i >= 0; i--) {
      const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
      months.push({ key: `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`, label: `${d.getMonth() + 1}월`, total: 0, done: 0 });
    }
    for (const e of events) {
      if (e.extendedProps.kind === "deadline") {
        const p = e.extendedProps as DeadlineProps;
        const m = months.find((x) => x.key === p.due.slice(0, 7));
        if (m) {
          m.total += 1;
          if (p.submitted) m.done += 1;
        }
      } else if (e.extendedProps.isTodo) {
        const m = months.find((x) => x.key === e.start.slice(0, 7)); // 로컬 문자열이라 그대로 자른다
        if (m) {
          m.total += 1;
          if (e.extendedProps.done) m.done += 1;
        }
      }
    }
    return months.filter((m) => m.total > 0);
  }, [events]);

  const todos = status?.counts.todos ?? 0;
  const todosDone = status?.counts.todosDone ?? 0;

  return (
    <Callout icon="📊" title="월별 완료율">
      {bars.length === 0 ? (
        <p className="py-6 text-[14px] text-faint">아직 집계할 과제·할 일이 없습니다.</p>
      ) : (
        <div className="flex h-44 items-end gap-3 pt-2">
          {bars.map((m) => {
            const pct = Math.round((m.done / m.total) * 100);
            return (
              <div key={m.key} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <span className="text-[13px] font-semibold tabular-nums text-text">{pct}%</span>
                <div className="flex h-24 w-full items-end rounded-md bg-[#f7f7f5]">
                  <div
                    className="w-full rounded-md bg-[#cbe3f7]"
                    style={{ height: `${Math.max(pct, 4)}%` }}
                    title={`${m.label}: ${m.done}/${m.total} 완료`}
                  />
                </div>
                <span className="text-[13px] text-muted">{m.label}</span>
                <span className="text-[11px] tabular-nums text-faint">
                  {m.done}/{m.total}
                </span>
              </div>
            );
          })}
        </div>
      )}
      <p className="mt-3 text-[12.5px] text-faint">
        과제 + 할 일 · 할 일 {todosDone}/{todos} 완료 · e클래스 마감 {status?.counts.deadlines ?? 0}건
      </p>
    </Callout>
  );
}
