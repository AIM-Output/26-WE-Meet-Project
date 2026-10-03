"use client";

import Link from "next/link";
import { useState } from "react";
import { CalendarRange, Clock, Download, ExternalLink, Pencil, Plus, RotateCcw, Trash2, TriangleAlert, X } from "lucide-react";
import { Banner } from "@/components/ui/Feedback";
import { Chip } from "@/components/ui/Chip";
import { Section, Toggle } from "@/components/ui/Layout";
import { useToast } from "@/components/ui/Toast";
import type { AttendanceApi } from "@/lib/useAttendance";
import { useTimetableImport } from "@/lib/useAttendance";
import {
  LATE_OPTIONS,
  LIMIT_OPTIONS,
  maxPeriod,
  meetingText,
  periodTime,
  ratioLabel,
  WEEKDAYS,
  type AttCourse,
  type AttendanceOverview,
  type Meeting,
  type PeriodView,
} from "@/lib/attendance";
import { fmtMD, fmtShortStamp, parseLocal, toDateStr } from "@/lib/dates";

// 시간표 설정 탭 (F3-S06·S10, Frontend-Route 8-5).
//   시간표 자동으로 가져오기 → 학사정보시스템 시간표 조회(로그인 불필요)에서 학수번호+분반으로 요일·교시를 채운다(자동 칩).
//   못 찾은 과목만 직접 입력(수정함 칩). 저장하는 순간 회차를 다시 만들고 '운영체제 총 32회' 토스트.
//   과목별 한도 비율·지각 환산 · 수기 과목 · 개강·종강·휴업일(자동 휴강) · 교시 ↔ 시각(캘린더 주 뷰) 까지 여기서.

const STATUS_MSG: Record<string, string> = {
  not_found: "시간표에서 찾지 못했습니다",
  no_time: "시간표에 강의시간이 없습니다 (원격·집중강의일 수 있음)",
  parse_error: "강의시간을 읽지 못했습니다",
  no_code: "학수번호·분반을 몰라 찾을 수 없습니다",
  error: "조회 중 오류가 났습니다",
};

export function TimetableEditor({ data, att }: { data: AttendanceOverview; att: AttendanceApi }) {
  const imp = useTimetableImport(att.reload);
  const courses = data.courses;
  const missing = courses.filter((c) => !c.excluded && !c.timetable.meetings.length);
  const p = imp.state?.progress;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <p className="min-w-[240px] flex-1 text-[13px] text-muted">
          학사정보시스템 시간표 조회(로그인 불필요)에서 <b className="text-text">학수번호+분반</b>으로 요일·교시를 찾습니다. 과목당 한 번, 1.5초 간격으로 조회합니다.
          {imp.state?.finishedAt && !imp.running && <span className="ml-1 text-faint">마지막: {fmtShortStamp(imp.state.finishedAt)}</span>}
        </p>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          disabled={imp.running || courses.length === 0}
          onClick={() => void imp.start(data.semester.id)}
        >
          <Download aria-hidden />
          {imp.running ? (p?.total ? `찾는 중… ${p.done}/${p.total}` : "찾는 중…") : "시간표 자동으로 가져오기"}
        </button>
      </div>

      {courses.length === 0 ? (
        <Banner tone="warn" action={<Link href="/settings/sources" className="btn btn-sm">수집 원천</Link>}>
          e클래스 동기화를 먼저 해 주세요 — 과목 목록은 e클래스에서 가져옵니다.
        </Banner>
      ) : (
        missing.length > 0 && (
          <Banner tone="primary">요일·교시를 넣으면 수업 횟수를 자동으로 셉니다 — 아직 {missing.map((c) => c.short).join(", ")}</Banner>
        )
      )}

      {courses.length > 0 && (
        <div className="overflow-x-auto rounded-xl border border-border bg-surface">
          <table className="w-full min-w-[680px] text-[14px]">
            <thead className="bg-surface-2 text-left text-[12px] text-muted">
              <tr>
                <th className="px-4 py-2 font-semibold">과목</th>
                <th className="px-2 py-2 font-semibold">요일·교시</th>
                <th className="w-24 px-2 py-2 font-semibold">결석 한도</th>
                <th className="w-36 px-2 py-2 font-semibold">지각 환산</th>
                <th className="w-20 px-2 py-2 font-semibold">계산</th>
              </tr>
            </thead>
            <tbody>
              {courses.map((c) => (
                <CourseRow key={c.id} c={c} att={att} periods={data.periods} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <ManualCourse att={att} />
      <SemesterPanel data={data} att={att} />
      <PeriodPanel periods={data.periods} att={att} />
    </div>
  );
}

/* ---------------------------------------------------------------- 과목 한 줄 */

function CourseRow({ c, att, periods }: { c: AttCourse; att: AttendanceApi; periods: PeriodView }) {
  const [editing, setEditing] = useState(false);
  const tt = c.timetable;
  const status = tt.status && tt.status !== "found" && !tt.meetings.length ? tt.status : null;
  return (
    <>
      <tr className={`border-t border-border align-top ${c.excluded ? "opacity-60" : ""}`}>
        <td className="px-4 py-3">
          <span className="flex items-center gap-2 font-semibold">
            <span className="size-2 flex-none rounded-full" style={{ background: c.color ?? "var(--faint)" }} aria-hidden />
            {c.short}
            {c.section && <span className="font-normal text-faint">[{c.section}]</span>}
          </span>
          <span className="mt-0.5 block text-[12px] text-faint">
            {c.code ? `${c.code}${c.section ? `-${c.section}` : ""}` : "학수번호 없음"}
            {c.source === "manual" ? " · 수기 과목" : " · e클래스"}
            {tt.raw?.professor ? ` · ${tt.raw.professor}` : ""}
          </span>
        </td>
        <td className="px-2 py-3">
          {tt.meetings.length ? (
            <span className="flex flex-wrap items-center gap-1.5">
              {tt.meetings.map((m) => {
                const t0 = periodTime(periods, m.weekday, m.periods[0]);
                const t1 = periodTime(periods, m.weekday, m.periods[m.periods.length - 1]);
                return (
                  <Chip key={`${m.weekday}-${m.periods[0]}`} tone="primary" square title={t0 && t1 ? `${t0[0]}~${t1[1]}${m.room ? ` · ${m.room}` : ""}` : undefined}>
                    {meetingText(m)}
                  </Chip>
                );
              })}
              <Chip tone={tt.filledBy === "auto" ? "ok" : "accent"} dashed>
                {tt.filledBy === "auto" ? "자동" : "수정함"}
              </Chip>
              {tt.versions.length > 1 && <span className="text-[12px] text-faint">{fmtMD(parseLocal(tt.versions[tt.versions.length - 1].validFrom))}부터 바뀜</span>}
              <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => setEditing((v) => !v)} aria-label={`${c.short} 요일·교시 고치기`}>
                <Pencil aria-hidden />
              </button>
              {tt.filledBy === "user" && tt.auto && tt.auto.length > 0 && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => void att.revertTimetable(c.id)} title={`학교 시간표: ${tt.autoText}`}>
                  <RotateCcw aria-hidden />
                  자동값으로
                </button>
              )}
            </span>
          ) : (
            <span className="flex flex-wrap items-center gap-2 text-[13px]">
              {status ? (
                <span className="inline-flex items-center gap-1 text-warn-text" title={tt.message ?? undefined}>
                  <TriangleAlert className="size-3.5" aria-hidden />
                  {STATUS_MSG[status] ?? "못 찾음"}
                </span>
              ) : (
                <span className="text-faint">아직 없음</span>
              )}
              <button type="button" className="btn btn-sm" onClick={() => setEditing(true)}>
                <Plus aria-hidden />
                요일·교시 입력
              </button>
            </span>
          )}
        </td>
        <td className="px-2 py-3">
          <select
            className="field field-sm"
            aria-label={`${c.short} 결석 한도`}
            value={LIMIT_OPTIONS.find((o) => Math.abs(o.value - c.settings.limitRatio) < 1e-6)?.value ?? c.settings.limitRatio}
            onChange={(e) => void att.patchCourse(c.id, { limitRatio: Number(e.target.value) })}
          >
            {!LIMIT_OPTIONS.some((o) => Math.abs(o.value - c.settings.limitRatio) < 1e-6) && (
              <option value={c.settings.limitRatio}>{ratioLabel(c.settings.limitRatio)}</option>
            )}
            {LIMIT_OPTIONS.map((o) => (
              <option key={o.label} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </td>
        <td className="px-2 py-3">
          <select
            className="field field-sm"
            aria-label={`${c.short} 지각 환산`}
            value={c.settings.lateToAbsence}
            onChange={(e) => void att.patchCourse(c.id, { lateToAbsence: Number(e.target.value) })}
          >
            {!LATE_OPTIONS.some((o) => o.value === c.settings.lateToAbsence) && (
              <option value={c.settings.lateToAbsence}>{c.settings.lateToAbsence}회 = 결석1</option>
            )}
            {LATE_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </td>
        <td className="px-2 py-3">
          <span className="flex items-center gap-1">
            <Toggle checked={!c.excluded} onChange={(v) => void att.patchCourse(c.id, { excluded: !v })} label={`${c.short} 계산에 넣기 (끄면 수강 취소로 보고 제외)`} />
            {c.source === "manual" && (
              <button type="button" className="btn btn-ghost btn-icon btn-sm btn-danger" onClick={() => void att.deleteCourse(c.id)} aria-label={`${c.short} 지우기`}>
                <Trash2 aria-hidden />
              </button>
            )}
          </span>
        </td>
      </tr>
      {editing && (
        <tr className="border-t border-dashed border-border bg-surface-2">
          <td colSpan={5} className="px-4 py-3">
            <MeetingEditor course={c} att={att} periods={periods} onDone={() => setEditing(false)} />
          </td>
        </tr>
      )}
    </>
  );
}

/* ---------------------------------------------------------------- 요일·교시 편집 */

type Draft = { weekday: number; from: number; to: number; room: string };

function toDraft(ms: Meeting[]): Draft[] {
  return ms.map((m) => ({ weekday: m.weekday, from: m.periods[0], to: m.periods[m.periods.length - 1], room: m.room ?? "" }));
}

function MeetingEditor({ course: c, att, periods, onDone }: { course: AttCourse; att: AttendanceApi; periods: PeriodView; onDone: () => void }) {
  const toast = useToast();
  const [rows, setRows] = useState<Draft[]>(() => (c.timetable.meetings.length ? toDraft(c.timetable.meetings) : [{ weekday: 0, from: 1, to: 2, room: "" }]));
  const s = c.summary;
  const hasRecords = s.presentCount + s.absentCount + s.lateCount + s.excusedCount > 0;
  const [when, setWhen] = useState<"start" | "today">(hasRecords ? "today" : "start");
  const [busy, setBusy] = useState(false);
  const set = (i: number, patch: Partial<Draft>) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));

  const save = async () => {
    const meetings: Meeting[] = rows.map((r) => ({
      weekday: r.weekday,
      periods: Array.from({ length: Math.max(r.from, r.to) - r.from + 1 }, (_, k) => r.from + k),
      room: r.room.trim(),
    }));
    setBusy(true);
    const g = await att.saveTimetable([{ courseId: c.id, meetings }], when === "today" ? toDateStr(new Date()) : null);
    setBusy(false);
    if (g) {
      const r = g[0];
      toast(`${r.name} 회차 ${r.sessions}개를 만들었습니다 — 휴강을 빼고 보강을 더해 총 ${r.total}회${r.orphans ? ` · 맞는 날이 없어진 기록 ${r.orphans}건` : ""}`, { tone: "success" });
      onDone();
    }
  };

  return (
    <div className="space-y-3">
      {c.timetable.autoText && (
        <p className="text-[12px] text-faint">
          학교 시간표: <b className="font-semibold text-muted">{c.timetable.autoText}</b>
          {c.timetable.raw?.times && ` (원문 ${c.timetable.raw.times})`}
        </p>
      )}
      <ul className="space-y-2">
        {rows.map((r, i) => {
          const max = maxPeriod(periods, r.weekday);
          const opts = Array.from({ length: max }, (_, k) => k + 1);
          const t0 = periodTime(periods, r.weekday, r.from);
          const t1 = periodTime(periods, r.weekday, Math.max(r.from, r.to));
          return (
            <li key={i} className="flex flex-wrap items-center gap-2">
              <select className="field field-sm w-[76px]" value={r.weekday} onChange={(e) => set(i, { weekday: Number(e.target.value) })} aria-label="요일">
                {WEEKDAYS.slice(0, 6).map((w, k) => (
                  <option key={w} value={k}>
                    {w}요일
                  </option>
                ))}
              </select>
              <select className="field field-sm w-[80px]" value={Math.min(r.from, max)} onChange={(e) => set(i, { from: Number(e.target.value), to: Math.max(Number(e.target.value), r.to) })} aria-label="시작 교시">
                {opts.map((p) => (
                  <option key={p} value={p}>
                    {p}교시
                  </option>
                ))}
              </select>
              ~
              <select className="field field-sm w-[80px]" value={Math.min(Math.max(r.from, r.to), max)} onChange={(e) => set(i, { to: Number(e.target.value) })} aria-label="끝 교시">
                {opts.filter((p) => p >= r.from).map((p) => (
                  <option key={p} value={p}>
                    {p}교시
                  </option>
                ))}
              </select>
              <span className="num w-[92px] text-[12px] text-faint">{t0 && t1 ? `${t0[0]}~${t1[1]}` : ""}</span>
              <input className="field field-sm w-[120px]" value={r.room} onChange={(e) => set(i, { room: e.target.value })} placeholder="강의실" aria-label="강의실" />
              <button type="button" className="btn btn-ghost btn-icon btn-sm" onClick={() => setRows((rs) => rs.filter((_, j) => j !== i))} aria-label="이 줄 지우기" disabled={rows.length === 1}>
                <X aria-hidden />
              </button>
            </li>
          );
        })}
      </ul>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setRows((rs) => [...rs, { weekday: 2, from: 1, to: 1, room: "" }])}>
        <Plus aria-hidden />
        요일 추가
      </button>
      {hasRecords && (
        <fieldset className="flex flex-wrap gap-x-5 gap-y-1 text-[13px]">
          <legend className="sr-only">바뀐 시간표를 언제부터 쓸까요</legend>
          <label className="inline-flex items-center gap-2">
            <input type="radio" name={`when-${c.id}`} checked={when === "today"} onChange={() => setWhen("today")} />
            오늘부터 (학기 중에 시간표가 바뀜 — 지난 기록은 그대로)
          </label>
          <label className="inline-flex items-center gap-2">
            <input type="radio" name={`when-${c.id}`} checked={when === "start"} onChange={() => setWhen("start")} />
            학기 처음부터 (잘못 들어간 시간표 고치기 — 같은 날 기록은 그대로 따라감)
          </label>
        </fieldset>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onDone}>
          취소
        </button>
        <button type="button" className="btn btn-primary btn-sm" disabled={busy} onClick={() => void save()}>
          저장하고 회차 만들기
        </button>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 수기 과목 (F3-R05) */

function ManualCourse({ att }: { att: AttendanceApi }) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [section, setSection] = useState("");
  if (!open)
    return (
      <div className="flex justify-end">
        <button type="button" className="btn btn-sm" onClick={() => setOpen(true)}>
          <Plus aria-hidden />
          수기 과목 추가
        </button>
      </div>
    );
  return (
    <form
      className="card flex flex-wrap items-end gap-3 p-4"
      onSubmit={async (e) => {
        e.preventDefault();
        if (await att.addCourse({ name: name.trim(), code: code.trim(), section: section.trim() })) {
          setOpen(false);
          setName("");
          setCode("");
          setSection("");
        }
      }}
    >
      <p className="basis-full text-[13px] text-muted">e클래스에 없는 과목(계절학기·타 기관 수강 등). 추가한 뒤 요일·교시를 넣으면 회차가 생깁니다.</p>
      <label className="min-w-[180px] flex-1 text-[12px] font-semibold text-muted">
        과목 이름
        <input className="field field-sm mt-1" value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
      </label>
      <label className="text-[12px] font-semibold text-muted">
        학수번호
        <input className="field field-sm mt-1 w-[120px]" value={code} onChange={(e) => setCode(e.target.value)} placeholder="선택" />
      </label>
      <label className="text-[12px] font-semibold text-muted">
        분반
        <input className="field field-sm mt-1 w-[72px]" value={section} onChange={(e) => setSection(e.target.value)} placeholder="선택" />
      </label>
      <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
        취소
      </button>
      <button type="submit" className="btn btn-primary btn-sm">
        추가
      </button>
    </form>
  );
}

/* ---------------------------------------------------------------- 학기 · 휴업일 (F3-R11·R12, 9절) */

function SemesterPanel({ data, att }: { data: AttendanceOverview; att: AttendanceApi }) {
  const sem = data.semester;
  const [editing, setEditing] = useState(false);
  const [start, setStart] = useState(sem.start ?? "");
  const [end, setEnd] = useState(sem.end ?? "");
  const [hDate, setHDate] = useState("");
  const [hName, setHName] = useState("");
  const src = (s: string | null) => (s === "user" ? "내가 입력" : s === "academic" ? "학사일정에서" : "");
  const missing = !sem.start || !sem.end;

  return (
    <Section title={`학기 — ${sem.label}`} icon={<CalendarRange />}>
      {sem.warnings.map((w) => (
        <Banner key={w} tone="warn" className="mb-3">
          {w}
        </Banner>
      ))}
      {editing || missing ? (
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await att.setSemester({ start: start || null, end: end || null })) setEditing(false);
          }}
        >
          <label className="text-[12px] font-semibold text-muted">
            개강
            <input type="date" className="field field-sm mt-1 w-[160px]" value={start} onChange={(e) => setStart(e.target.value)} required />
          </label>
          <label className="text-[12px] font-semibold text-muted">
            종강
            <input type="date" className="field field-sm mt-1 w-[160px]" value={end} onChange={(e) => setEnd(e.target.value)} required />
          </label>
          {sem.startSource === "user" && sem.auto.start && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={async () => (await att.setSemester({ start: null, end: null })) && setEditing(false)}>
              학사일정 값으로 ({sem.auto.start} ~ {sem.auto.end})
            </button>
          )}
          {!missing && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setEditing(false)}>
              취소
            </button>
          )}
          <button type="submit" className="btn btn-primary btn-sm">
            저장
          </button>
        </form>
      ) : (
        <p className="flex flex-wrap items-center gap-2 text-[14px]">
          개강 <b className="num">{sem.start}</b> · 종강 <b className="num">{sem.end}</b>
          <span className="text-[13px] text-faint">({src(sem.startSource)})</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setStart(sem.start ?? "");
              setEnd(sem.end ?? "");
              setEditing(true);
            }}
          >
            직접 고치기
          </button>
        </p>
      )}
      {!missing && (
        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <div>
            <h3 className="label">자동 휴강 — 공휴일·휴업일 (모든 과목)</h3>
            <ul className="flex flex-wrap gap-1.5">
              {sem.holidays.map((h) => (
                <li key={h.date}>
                  <Chip square tone={h.source === "user" ? "accent" : "neutral"} title={h.source === "fixed" ? "양력 고정 공휴일" : h.source === "user" ? "내가 추가" : "학사일정"}>
                    <span className="num">{fmtMD(parseLocal(h.date))}</span> {h.name}
                    {h.source === "user" && (
                      <button
                        type="button"
                        className="ml-0.5"
                        aria-label={`${h.name} 빼기`}
                        onClick={() => void att.setSemester({ holidays: sem.userHolidays.filter((x) => x.date !== h.date) })}
                      >
                        <X aria-hidden />
                      </button>
                    )}
                  </Chip>
                </li>
              ))}
            </ul>
            <form
              className="mt-2 flex flex-wrap items-center gap-2"
              onSubmit={async (e) => {
                e.preventDefault();
                if (!hDate) return;
                if (await att.setSemester({ holidays: [...sem.userHolidays, { date: hDate, name: hName.trim() || "휴업일" }] })) {
                  setHDate("");
                  setHName("");
                }
              }}
            >
              <input type="date" className="field field-sm w-[150px]" value={hDate} onChange={(e) => setHDate(e.target.value)} aria-label="휴업일 날짜" />
              <input className="field field-sm w-[140px]" value={hName} onChange={(e) => setHName(e.target.value)} placeholder="이름 (개교기념일)" aria-label="휴업일 이름" />
              <button type="submit" className="btn btn-sm" disabled={!hDate}>
                <Plus aria-hidden />
                휴업일 추가
              </button>
            </form>
          </div>
          <div>
            <h3 className="label">학교 지정 보강일 (학사일정)</h3>
            {sem.makeupDays.length ? (
              <ul className="space-y-1 text-[13px]">
                {sem.makeupDays.map((m) => (
                  <li key={m.date} className="num">
                    <b>{fmtMD(parseLocal(m.date))}</b> ← {fmtMD(parseLocal(m.original))} {m.name} 수업
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-faint">없음</p>
            )}
            <p className="hint">휴업일에 걸린 수업은 이 날 보강 회차로 자동으로 들어갑니다. 실제로 안 했으면 회차 목록에서 &lsquo;휴강&rsquo;을 누르세요.</p>
          </div>
        </div>
      )}
      <p className="hint mt-3">
        과목 공지의 휴강도 자동으로 켭니다 — e클래스 동기화 때 받은 &lsquo;공지&rsquo; 게시판 글에서 &lsquo;휴강&rsquo;과 날짜(9월 17일 · 9/16 · 오늘 · 다음 주 화요일)를 찾아
        그 과목의 그날 회차를 휴강으로 둡니다. 틀렸으면 회차 목록에서 &lsquo;휴강&rsquo;을 다시 눌러 풀면 됩니다.
      </p>
      <p className="hint mt-1">※ 시험주처럼 수업이 없는 주는 자동으로 빼지 않습니다 — 회차 목록에서 &lsquo;휴강&rsquo;을 누르세요.</p>
    </Section>
  );
}

/* ---------------------------------------------------------------- 교시 ↔ 시각 (C1-R05a) */

function PeriodPanel({ periods, att }: { periods: PeriodView; att: AttendanceApi }) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<{ mwf: Record<string, [string, string]>; tt: Record<string, [string, string]> } | null>(null);
  const cur = draft ?? { mwf: periods.mwf, tt: periods.tt };
  const setCell = (mod: "mwf" | "tt", p: string, i: 0 | 1, v: string) =>
    setDraft((d) => {
      const base = d ?? { mwf: { ...periods.mwf }, tt: { ...periods.tt } };
      const row = [...(base[mod][p] ?? ["", ""])] as [string, string];
      row[i] = v;
      return { ...base, [mod]: { ...base[mod], [p]: row } };
    });
  const keys = Object.keys(periods.mwf).sort((a, b) => Number(a) - Number(b));

  return (
    <Section
      title="교시 ↔ 시각"
      icon={<Clock />}
      action={
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
          {open ? "접기" : "보기·고치기"}
        </button>
      }
    >
      <p className="text-[13px] text-muted">
        캘린더 주 뷰에서 수업을 이 시각에 그립니다. 출결은 시수가 아니라 <b className="text-text">수업한 날(회)</b> 단위로 셉니다.
        기본값은{" "}
        <a href={periods.sourceUrl} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-0.5 font-semibold text-primary hover:underline">
          {periods.source}
          <ExternalLink className="size-3" aria-hidden />
        </a>
        {periods.edited && <Chip tone="accent" className="ml-2">내가 고침</Chip>}
      </p>
      {open && (
        <div className="mt-3">
          <div className="overflow-x-auto">
            <table className="text-[13px]">
              <thead className="text-left text-[12px] text-muted">
                <tr>
                  <th className="py-1 pr-3 font-semibold">교시</th>
                  <th className="py-1 pr-3 font-semibold">월·수·금 (50분)</th>
                  <th className="py-1 font-semibold">화·목 (75분)</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((p) => (
                  <tr key={p}>
                    <td className="num py-0.5 pr-3 font-semibold">{p}</td>
                    {(["mwf", "tt"] as const).map((mod) => (
                      <td key={mod} className="py-0.5 pr-3">
                        {cur[mod][p] ? (
                          <span className="flex items-center gap-1">
                            <input type="time" className="field field-sm w-[104px]" value={cur[mod][p][0]} onChange={(e) => setCell(mod, p, 0, e.target.value)} aria-label={`${mod === "mwf" ? "월수금" : "화목"} ${p}교시 시작`} />
                            ~
                            <input type="time" className="field field-sm w-[104px]" value={cur[mod][p][1]} onChange={(e) => setCell(mod, p, 1, e.target.value)} aria-label={`${mod === "mwf" ? "월수금" : "화목"} ${p}교시 끝`} />
                          </span>
                        ) : (
                          <span className="text-faint">—</span>
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="mt-3 flex flex-wrap justify-end gap-2">
            {periods.edited && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={async () => (await att.savePeriods(null)) && setDraft(null)}>
                <RotateCcw aria-hidden />
                학교 기본값으로
              </button>
            )}
            <button type="button" className="btn btn-primary btn-sm" disabled={!draft} onClick={async () => draft && (await att.savePeriods(draft)) && setDraft(null)}>
              저장
            </button>
          </div>
        </div>
      )}
    </Section>
  );
}
