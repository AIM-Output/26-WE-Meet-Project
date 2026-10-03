"use client";

import { useMemo, useState } from "react";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { Chip } from "@/components/ui/Chip";
import { AttendanceChips } from "./AttendanceChips";
import type { AttendanceApi } from "@/lib/useAttendance";
import { autoCancelText, maxPeriod, periodsText, periodTime, WEEKDAYS, type AttCourse, type AttSession, type PeriodView } from "@/lib/attendance";
import { addDays, fmtMD, parseLocal, toDateStr } from "@/lib/dates";

// 회차 목록 (F3-S03) — 과목을 펼치면 날짜별 회차(수업한 날 하나 = 1회)와 상태. 상세 모달 없이 행에서 바로 고른다.
// 칩 = 출석 · 결석 · 지각 · 공결 · 휴강. 학사일정·e클래스 공지에서 찾은 휴강은 칩이 미리 켜져 있고 근거를 옆에 적는다.
// 지난 미입력은 점으로 강조, 다가올 회차는 공결·휴강만. 2주 뒤부터는 접어 둔다.

const AHEAD_DAYS = 14;

export function SessionList({ course, att, periods }: { course: AttCourse; att: AttendanceApi; periods: PeriodView | null }) {
  const [showAll, setShowAll] = useState(false);
  const horizon = toDateStr(addDays(new Date(), AHEAD_DAYS));
  const shown = showAll ? course.sessions : course.sessions.filter((s) => s.date <= horizon);
  const hidden = course.sessions.length - shown.length;

  if (!course.sessions.length)
    return <p className="px-4 py-4 text-[13px] text-muted md:px-5">이번 학기 수업 일정이 없습니다 — 시간표 설정에서 요일·교시를 넣어 주세요.</p>;

  return (
    <div className="border-t border-border bg-surface-2">
      <ul className="px-4 py-1 md:px-5">
        {shown.map((s) => (
          <SessionRow key={s.id} s={s} course={course} att={att} />
        ))}
      </ul>
      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border px-4 py-2 md:px-5">
        {hidden > 0 ? (
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => setShowAll(true)}>
            다가올 회차 {hidden}회 더 보기
          </button>
        ) : (
          <span />
        )}
        <MakeupForm course={course} att={att} periods={periods} />
      </div>
    </div>
  );
}

function SessionRow({ s, course, att }: { s: AttSession; course: AttCourse; att: AttendanceApi }) {
  const d = parseLocal(s.date);
  const canceled = s.state === "canceled";
  const unchecked = !canceled && s.ended && !s.attendance;
  const future = !s.started;
  const faded = canceled || future;
  const auto = s.autoCancel;
  return (
    <li className="flex flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border py-2 last:border-b-0">
      <span className="flex min-w-[168px] items-center gap-2 text-[14px]">
        <span className={`size-1.5 flex-none rounded-full ${unchecked ? "bg-accent" : "bg-transparent"}`} aria-label={unchecked ? "확인하지 않음" : undefined} />
        <span className={`num font-semibold ${faded ? "text-faint" : ""} ${canceled ? "line-through" : ""}`}>{fmtMD(d)}</span>
        <span className={`num text-[13px] ${faded ? "text-faint" : "text-muted"}`} title={`${periodsText(s)}${s.room ? ` · ${s.room}` : ""}`}>
          {s.start}~{s.end}
        </span>
      </span>
      {s.kind === "makeup" && (
        <Chip tone="info" square title={s.makeupFor ? `${s.makeupFor} 수업을 이날 합니다` : undefined}>
          {s.origin === "school" ? `학교 보강일${s.makeupName ? ` · ${s.makeupName}` : ""}` : "보강"}
        </Chip>
      )}
      <span className="ml-auto flex flex-wrap items-center gap-2">
        {future && !canceled && <span className="text-[12px] text-faint">다가옴</span>}
        <AttendanceChips state={s.state} value={s.attendance} future={future} onChange={(p) => void att.mark(course.id, s.id, p)} label={`${fmtMD(d)} 출결`} />
        {s.origin === "user" && (
          <button type="button" className="btn btn-ghost btn-icon btn-sm btn-danger" onClick={() => void att.deleteMakeup(s.id)} aria-label="이 보강 지우기">
            <Trash2 aria-hidden />
          </button>
        )}
      </span>
      {auto && (
        <span className="basis-full pl-[14px] text-[12px] text-faint md:pl-[176px]">
          {canceled && s.cancelSource !== "user" ? "자동 휴강 — " : "자동 휴강이었지만 수업함으로 바꿈 — "}
          {auto.url ? (
            <a href={auto.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-primary hover:underline">
              {autoCancelText(auto)}
              <ExternalLink className="size-3" aria-hidden />
            </a>
          ) : (
            autoCancelText(auto)
          )}
        </span>
      )}
      {!canceled && s.attendance === "excused" && (
        <input
          key={`${s.id}-${s.memo}`}
          className="field field-sm basis-full md:ml-[176px] md:basis-auto md:flex-1"
          placeholder="공결 사유 (예: 예비군 · 진단서 제출)"
          defaultValue={s.memo}
          aria-label="공결 사유"
          onBlur={(e) => {
            if (e.target.value.trim() !== (s.memo ?? "")) void att.setMemo(s.id, e.target.value.trim());
          }}
        />
      )}
    </li>
  );
}

/** 보강 추가 (F3-R16) — 날짜 + 교시(캘린더에 그릴 시각). 총 횟수에 1회 더해진다. */
function MakeupForm({ course, att, periods }: { course: AttCourse; att: AttendanceApi; periods: PeriodView | null }) {
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(() => toDateStr(new Date()));
  const [from, setFrom] = useState(1);
  const [to, setTo] = useState(1);
  const [memo, setMemo] = useState("");
  const [busy, setBusy] = useState(false);
  const wd = useMemo(() => (parseLocal(date).getDay() + 6) % 7, [date]);
  const max = maxPeriod(periods, wd);
  const opts = Array.from({ length: max }, (_, i) => i + 1);
  const t0 = periodTime(periods, wd, from);
  const t1 = periodTime(periods, wd, Math.max(from, to));

  if (!open)
    return (
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(true)}>
        <Plus aria-hidden />
        보강 추가
      </button>
    );

  return (
    <form
      className="flex w-full flex-wrap items-end gap-2 md:w-auto"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        const periodsList = Array.from({ length: Math.max(from, to) - from + 1 }, (_, i) => from + i);
        const ok = await att.addMakeup({ courseId: course.id, date, periods: periodsList, memo });
        setBusy(false);
        if (ok) {
          setOpen(false);
          setMemo("");
        }
      }}
    >
      <label className="text-[12px] font-semibold text-muted">
        날짜
        <input type="date" className="field field-sm mt-1 w-[150px]" value={date} onChange={(e) => setDate(e.target.value)} required />
      </label>
      <label className="text-[12px] font-semibold text-muted">
        교시 ({WEEKDAYS[wd]})
        <span className="mt-1 flex items-center gap-1">
          <select className="field field-sm w-[72px]" value={from} onChange={(e) => setFrom(Number(e.target.value))} aria-label="시작 교시">
            {opts.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          ~
          <select className="field field-sm w-[72px]" value={Math.max(from, to)} onChange={(e) => setTo(Number(e.target.value))} aria-label="끝 교시">
            {opts.filter((p) => p >= from).map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </span>
      </label>
      <label className="min-w-[140px] flex-1 text-[12px] font-semibold text-muted">
        메모
        <input className="field field-sm mt-1" value={memo} onChange={(e) => setMemo(e.target.value)} placeholder="토요일 보강 등" />
      </label>
      <span className="pb-2 text-[12px] text-faint num">{t0 && t1 ? `${t0[0]}~${t1[1]}` : ""}</span>
      <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
        추가
      </button>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
        취소
      </button>
    </form>
  );
}
