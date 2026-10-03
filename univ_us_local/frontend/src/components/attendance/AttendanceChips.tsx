"use client";

import { StatusBadge } from "@/components/ui/Chip";
import {
  ATT_CHIP_CLASS,
  ATT_CHIPS,
  ATT_LABEL,
  CANCEL_CHIP_CLASS,
  chipPatch,
  LEVEL_LABEL,
  LEVEL_TONE,
  type Attendance,
  type Level,
  type SessionPatch,
  type SessionState,
} from "@/lib/attendance";

// 출결 칩 한 줄 — 출석 · 결석 · 지각 · 공결 · 휴강 (2026-09-29 수정 ② — 조퇴는 없고 휴강이 같은 줄에 있다).
// 회차 목록 · 이번 주 · 캘린더 수업 상세가 같이 쓴다 (Frontend-Route 8-3 '누른 것이 채워진 칩').
//   같은 칩을 다시 누르면 미입력(휴강이면 휴강 해제). 휴강인 회차에서 출결 칩을 누르면 휴강을 풀고 그 출결로.
//   아직 시작 전인 수업은 공결·휴강만 누를 수 있다. 상태는 색만으로 전하지 않는다(글자 그대로).

export function AttendanceChips({
  state,
  value,
  onChange,
  disabled,
  future,
  size = "md",
  label = "출결",
}: {
  state: SessionState;
  value: Attendance | null;
  onChange: (p: SessionPatch) => void;
  disabled?: boolean;
  future?: boolean;
  size?: "sm" | "md";
  label?: string;
}) {
  const canceled = state === "canceled";
  const cls = `rounded-md border font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
    size === "sm" ? "h-7 px-2 text-[12px]" : "h-8 px-2.5 text-[13px]"
  }`;
  const off = "border-border bg-surface text-muted hover:bg-surface-2";
  const s = { state, attendance: value };
  return (
    <div className="flex flex-wrap gap-1" role="radiogroup" aria-label={label}>
      {ATT_CHIPS.map((a) => {
        const on = !canceled && value === a;
        return (
          <button
            key={a}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={disabled || (future && a !== "excused")}
            onClick={() => onChange(chipPatch(s, a))}
            title={on ? "다시 누르면 미입력으로" : canceled ? "휴강을 풀고 이 출결로" : undefined}
            className={`${cls} ${on ? ATT_CHIP_CLASS[a] : off}`}
          >
            {ATT_LABEL[a]}
          </button>
        );
      })}
      <button
        type="button"
        role="radio"
        aria-checked={canceled}
        disabled={disabled}
        onClick={() => onChange(chipPatch(s, "canceled"))}
        title={canceled ? "다시 누르면 휴강 해제 (수업함)" : "휴강으로 표시 — 총 횟수에서 빠진다"}
        className={`${cls} ${canceled ? `${CANCEL_CHIP_CLASS} line-through decoration-1` : `${off} border-dashed`}`}
      >
        휴강
      </button>
    </div>
  );
}

export function LevelBadge({ level }: { level: Level | null }) {
  if (!level) return <StatusBadge tone="neutral">—</StatusBadge>;
  return <StatusBadge tone={LEVEL_TONE[level]}>{LEVEL_LABEL[level]}</StatusBadge>;
}
