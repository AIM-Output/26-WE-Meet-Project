"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ExternalLink, PencilLine, TriangleAlert } from "lucide-react";
import { Chip } from "@/components/ui/Chip";
import { ProgressBar } from "@/components/ui/Progress";
import { LevelBadge } from "./AttendanceChips";
import { SessionList } from "./SessionList";
import type { AttendanceApi } from "@/lib/useAttendance";
import { LEVEL_BAR, num, ratioLabel, type AttCourse, type PeriodView } from "@/lib/attendance";
import { navigateQuery } from "@/lib/useQueryState";

// 과목별 현황 카드 (F3-S01·S02·S05) — 막대(결석 횟수 / 허용 횟수) · 남은 여유 · 상태 배지(글자 병기) · 근거 줄 · 누적 직접 수정.
// 단위는 '회'(수업한 날). 공지에서 휴강을 찾았지만 걸 날짜를 못 찾은 것은 카드 안에 '확인 필요'로 링크만 띄운다.
// 위험·초과는 테두리를 강조하고 목록 맨 위로(8-3). 시간표가 없으면 숫자 대신 '—' 와 입력 버튼(F3-S10).

export function CourseStatusCard({
  course: c,
  att,
  periods,
  expanded,
}: {
  course: AttCourse;
  att: AttendanceApi;
  periods: PeriodView | null;
  expanded: boolean;
}) {
  const s = c.summary;
  const noTable = !c.timetable.meetings.length;
  const hot = s.level === "danger" || s.level === "over";
  const adj = s.manualAdjust;
  const toggle = () => navigateQuery({ course: expanded ? null : c.id }, "replace");

  return (
    <li
      id={`course-${c.id}`}
      className={`card overflow-hidden ${s.level === "over" ? "border-danger" : hot ? "border-accent" : ""} ${c.excluded ? "opacity-60" : ""}`}
    >
      <div className="p-4 md:p-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <h3 className="flex min-w-[160px] flex-1 items-center gap-2 text-[16px] font-bold">
            <span className="size-2.5 flex-none rounded-full" style={{ background: c.color ?? "var(--faint)" }} aria-hidden />
            <span className="min-w-0 truncate">{c.short}</span>
            {c.section && <span className="text-[13px] font-medium text-faint">[{c.section}]</span>}
            {c.source === "manual" && (
              <Chip square className="font-medium">
                수기
              </Chip>
            )}
            {c.excluded && <Chip tone="neutral">계산 제외</Chip>}
          </h3>
          {noTable ? (
            <span className="flex flex-wrap items-center gap-2 text-[13px] text-muted">
              <span className="num">—</span>
              요일·교시를 넣으면 수업 횟수를 자동으로 셉니다
              <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ tab: "timetable" }, "replace")}>
                입력하기
              </button>
            </span>
          ) : s.level === null ? (
            <span className="text-[13px] text-muted">이번 학기 수업이 없어 계산할 수 없습니다</span>
          ) : (
            <>
              <div className="w-full max-w-[280px] min-w-[140px] flex-1">
                <ProgressBar
                  value={s.effectiveAbsent}
                  max={s.allowed}
                  tone={LEVEL_BAR[s.level]}
                  label={`${c.short} 결석 ${s.effectiveAbsent}회 / 허용 ${num(s.allowed)}회`}
                />
              </div>
              <span className="num text-[14px] whitespace-nowrap">
                결석 {s.effectiveAbsent} / {num(s.allowed)}회
              </span>
              <span className={`text-[13px] whitespace-nowrap ${hot ? "font-semibold text-accent-text" : "text-muted"}`}>
                {s.level === "over" ? `${num(-s.remaining)}회 초과` : `남은 여유 ${s.spareSessions}회`}
              </span>
              <LevelBadge level={s.level} />
            </>
          )}
        </div>
        {!noTable && s.level !== null && (
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
            <span className="num">
              {s.basis}
              <span className="ml-2 text-faint">
                · 한도 {ratioLabel(c.settings.limitRatio)}
                {c.settings.lateToAbsence ? ` · 지각 ${c.settings.lateToAbsence}회 = 결석 1회` : " · 지각 환산 안 함"}
              </span>
            </span>
            <span className="flex flex-wrap items-center gap-2">
              {s.level === "danger" && (
                <span className="inline-flex items-center gap-1 font-semibold text-accent-text">
                  <TriangleAlert className="size-3.5" aria-hidden />한 번 더 빠지면 F
                </span>
              )}
              {(adj.absent !== 0 || adj.late !== 0) && (
                <Chip tone="accent" dashed title="회차 기록과 따로 더한 값">
                  직접 조정 {adj.absent ? `결석 ${adj.absent > 0 ? "+" : ""}${adj.absent}` : ""}
                  {adj.absent && adj.late ? " · " : ""}
                  {adj.late ? `지각 ${adj.late > 0 ? "+" : ""}${adj.late}` : ""}
                </Chip>
              )}
              {s.uncheckedSessions > 0 && <Chip tone="accent">미입력 {s.uncheckedSessions}</Chip>}
              <button
                type="button"
                className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 font-semibold hover:bg-surface-3"
                aria-expanded={expanded}
                aria-controls={`sessions-${c.id}`}
                onClick={toggle}
              >
                결석 {s.absentCount + adj.absent} · 지각 {s.lateCount + adj.late} · 휴강 {s.canceledCount}
                <ChevronDown className={`size-4 transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden />
              </button>
            </span>
          </div>
        )}
        {c.noticeHints.length > 0 && (
          <ul className="mt-2 space-y-1">
            {c.noticeHints.map((h) => (
              <li key={`${h.url}-${h.date ?? ""}`} className="flex flex-wrap items-center gap-1.5 text-[12px] text-warn-text">
                <TriangleAlert className="size-3.5 flex-none" aria-hidden />
                e클래스 공지
                {h.url ? (
                  <a href={h.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-semibold underline-offset-2 hover:underline">
                    &lsquo;{h.reason}&rsquo;
                    <ExternalLink className="size-3" aria-hidden />
                  </a>
                ) : (
                  <b>&lsquo;{h.reason}&rsquo;</b>
                )}
                — {h.why}. 맞는 날에 휴강을 눌러 주세요
              </li>
            ))}
          </ul>
        )}
      </div>
      <AnimatePresence initial={false}>
        {expanded && !noTable && (
          <motion.div
            key="sessions"
            id={`sessions-${c.id}`}
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            transition={{ type: "spring", bounce: 0, visualDuration: 0.25 }}
            style={{ overflow: "hidden" }}
          >
            <AdjustEditor course={c} att={att} />
            <SessionList course={c} att={att} periods={periods} />
          </motion.div>
        )}
      </AnimatePresence>
    </li>
  );
}

/** 누적 직접 수정 (F3-R23·S05) — 몇 주 밀렸을 때 회차를 하나씩 누르지 않고 숫자만 맞춘다. 기록과의 차이만 '직접 조정'으로 저장. */
function AdjustEditor({ course: c, att }: { course: AttCourse; att: AttendanceApi }) {
  const s = c.summary;
  const recAbsent = s.absentCount;
  const recLate = s.lateCount;
  const [open, setOpen] = useState(false);
  const [absent, setAbsent] = useState(recAbsent + c.adjust.absent);
  const [late, setLate] = useState(recLate + c.adjust.late);
  const [busy, setBusy] = useState(false);

  if (!open)
    return (
      <div className="flex flex-wrap items-center gap-2 border-t border-border bg-surface-2 px-4 py-2 text-[13px] text-muted md:px-5">
        회차 기록: 출석 {s.presentCount} · 결석 {recAbsent} · 지각 {recLate}
        {s.convertedCount > 0 && ` (→ 결석 ${s.convertedCount}회로 환산)`} · 공결 {s.excusedCount} · 휴강 {s.canceledCount}
        {s.autoCanceledCount > 0 && ` (자동 ${s.autoCanceledCount})`}
        <button
          type="button"
          className="btn btn-ghost btn-sm ml-auto"
          onClick={() => {
            setAbsent(recAbsent + c.adjust.absent);
            setLate(recLate + c.adjust.late);
            setOpen(true);
          }}
        >
          <PencilLine aria-hidden />
          누적 숫자 직접 고치기
        </button>
      </div>
    );

  return (
    <form
      className="flex flex-wrap items-end gap-3 border-t border-border bg-surface-2 px-4 py-3 md:px-5"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        const ok = await att.patchCourse(c.id, { adjust: { absent: absent - recAbsent, late: late - recLate } });
        setBusy(false);
        if (ok) setOpen(false);
      }}
    >
      <label className="text-[12px] font-semibold text-muted">
        결석 (회)
        <input type="number" min={0} max={60} className="field field-sm mt-1 w-[84px]" value={absent} onChange={(e) => setAbsent(Number(e.target.value))} />
      </label>
      <label className="text-[12px] font-semibold text-muted">
        지각 (회)
        <input type="number" min={0} max={60} className="field field-sm mt-1 w-[84px]" value={late} onChange={(e) => setLate(Number(e.target.value))} />
      </label>
      <p className="min-w-[200px] flex-1 pb-1 text-[12px] text-faint">
        회차 기록(결석 {recAbsent} · 지각 {recLate})과의 차이만 &lsquo;직접 조정&rsquo;으로 더합니다. 회차 기록은 바뀌지 않습니다.
      </p>
      {(c.adjust.absent !== 0 || c.adjust.late !== 0) && (
        <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={async () => (await att.patchCourse(c.id, { adjust: { absent: 0, late: 0 } })) && setOpen(false)}>
          조정 지우기
        </button>
      )}
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
        취소
      </button>
      <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
        저장
      </button>
    </form>
  );
}
