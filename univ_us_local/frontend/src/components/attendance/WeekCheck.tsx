"use client";

import { useMemo, useState } from "react";
import { CheckCheck, ChevronLeft, ChevronRight } from "lucide-react";
import { EmptyState } from "@/components/ui/Feedback";
import { Group } from "@/components/ui/Layout";
import { AttendanceChips } from "./AttendanceChips";
import type { AttendanceApi } from "@/lib/useAttendance";
import { autoCancelText, periodsText, type AttCourse, type AttSession } from "@/lib/attendance";
import { addDays, fmtMD, parseLocal, toDateStr, WEEKDAY_KO } from "@/lib/dates";
import { useToast } from "@/components/ui/Toast";

// 이번 주 탭 (F3-R26·S04) — 이번 주 수업을 요일 순으로 모아 한 화면에서 처리한다. 밀린 입력을 빨리 끝내는 용도.
// 위에는 지난 주들에 확인하지 않은 수업을 따로 모은다('확인하지 않은 수업 N회 — 지금 입력'이 여기로 온다).
// 주 이동은 URL 없이 컴포넌트 상태(8-4).

type Row = { c: AttCourse; s: AttSession };

export function WeekCheck({ courses, att }: { courses: AttCourse[]; att: AttendanceApi }) {
  const toast = useToast();
  const [offset, setOffset] = useState(0);
  const monday = useMemo(() => {
    const t = new Date();
    return addDays(new Date(t.getFullYear(), t.getMonth(), t.getDate()), -((t.getDay() + 6) % 7) + offset * 7);
  }, [offset]);
  const from = toDateStr(monday);
  const to = toDateStr(addDays(monday, 6));
  const thisMonday = toDateStr(addDays(new Date(), -((new Date().getDay() + 6) % 7)));

  const live = courses.filter((c) => !c.excluded);
  const all: Row[] = live.flatMap((c) => c.sessions.map((s) => ({ c, s })));
  const rows = all
    .filter(({ s }) => s.date >= from && s.date <= to)
    .sort((a, b) => a.s.date.localeCompare(b.s.date) || a.s.start.localeCompare(b.s.start));
  const older = all
    .filter(({ s }) => s.date < thisMonday && s.state === "scheduled" && s.ended && !s.attendance)
    .sort((a, b) => a.s.date.localeCompare(b.s.date));
  const fillable = rows.filter(({ s }) => s.state === "scheduled" && s.started && !s.attendance);

  const days = [...new Set(rows.map((r) => r.s.date))];

  const markAll = async (list: Row[]) => {
    const r = await att.bulk(list.map(({ s }) => ({ id: s.id, attendance: "present" as const })));
    if (r) toast(`${r.updated}회를 출석으로 적었습니다 — 빠진 날만 고치세요${r.skipped.length ? ` (건너뜀 ${r.skipped.length})` : ""}`, { tone: "success" });
  };

  return (
    <div className="space-y-4">
      {older.length > 0 && (
        <section className="card p-4 md:p-5">
          <Group
            title="지난 주에 확인하지 않은 수업"
            count={older.length}
            extra={<span className="text-[13px] font-medium text-muted">미입력은 결석으로 세지 않지만, 숫자가 실제보다 좋아 보일 수 있습니다</span>}
            collapsible
            defaultOpen={older.length <= 12}
          >
            <ul className="divide-y divide-border">
              {older.map(({ c, s }) => (
                <Line key={s.id} c={c} s={s} att={att} showDate />
              ))}
            </ul>
            <div className="mt-2 flex justify-end">
              <button type="button" className="btn btn-sm" onClick={() => void markAll(older)}>
                <CheckCheck aria-hidden />
                지난 미입력 모두 출석으로
              </button>
            </div>
          </Group>
        </section>
      )}
      <section className="card p-4 md:p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOffset((o) => o - 1)}>
            <ChevronLeft aria-hidden />
            지난 주
          </button>
          <span className="num text-[14px] font-semibold" aria-live="polite">
            {fmtMD(monday)} ~ {fmtMD(addDays(monday, 6))}
            {offset === 0 && <span className="ml-1.5 font-medium text-faint">이번 주</span>}
          </span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOffset((o) => o + 1)}>
            다음 주
            <ChevronRight aria-hidden />
          </button>
          {offset !== 0 && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOffset(0)}>
              이번 주로
            </button>
          )}
          <button type="button" className="btn btn-sm ml-auto" disabled={fillable.length === 0} onClick={() => void markAll(fillable)}>
            <CheckCheck aria-hidden />
            모두 출석으로
          </button>
        </div>
        {rows.length === 0 ? (
          <EmptyState compact title="이 주에는 수업이 없습니다" />
        ) : (
          <div className="space-y-3">
            {days.map((day) => {
              const d = parseLocal(day);
              return (
                <div key={day}>
                  <h3 className="mb-1 text-[13px] font-bold text-muted">
                    {WEEKDAY_KO[d.getDay()]}요일{" "}
                    <span className="num font-medium">
                      {d.getMonth() + 1}/{d.getDate()}
                    </span>
                  </h3>
                  <ul className="divide-y divide-border rounded-lg border border-border">
                    {rows
                      .filter((r) => r.s.date === day)
                      .map(({ c, s }) => (
                        <Line key={s.id} c={c} s={s} att={att} />
                      ))}
                  </ul>
                </div>
              );
            })}
          </div>
        )}
      </section>
    </div>
  );
}

function Line({ c, s, att, showDate }: { c: AttCourse; s: AttSession; att: AttendanceApi; showDate?: boolean }) {
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 px-3 py-2.5">
      <span className="flex min-w-[180px] flex-1 items-center gap-2 text-[14px]">
        <span className="size-2 flex-none rounded-full" style={{ background: c.color ?? "var(--faint)" }} aria-hidden />
        {showDate && <span className="num w-16 flex-none font-semibold">{fmtMD(parseLocal(s.date))}</span>}
        <span className="min-w-0 truncate font-semibold">{c.short}</span>
        <span className="num text-[13px] whitespace-nowrap text-muted">
          {periodsText(s)} {s.start}~{s.end}
        </span>
        {s.kind === "makeup" && <span className="text-[12px] font-semibold text-info-text">보강</span>}
        {s.state === "canceled" && s.autoCancel && s.cancelSource !== "user" && (
          <span className="truncate text-[12px] text-faint" title={autoCancelText(s.autoCancel)}>
            자동 휴강 · {autoCancelText(s.autoCancel)}
          </span>
        )}
        {s.state === "scheduled" && !s.started && <span className="text-[12px] text-faint">다가옴</span>}
      </span>
      <AttendanceChips
        state={s.state}
        value={s.attendance}
        future={!s.started}
        onChange={(p) => void att.mark(c.id, s.id, p)}
        size="sm"
        label={`${c.short} ${fmtMD(parseLocal(s.date))} 출결`}
      />
    </li>
  );
}
