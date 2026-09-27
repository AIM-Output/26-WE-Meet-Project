"use client";

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, ChevronLeft, ChevronRight, Download, Plus, TriangleAlert, UserCheck } from "lucide-react";
import { Page, PageHeader } from "@/components/ui/Layout";
import { Tabs } from "@/components/ui/Tabs";
import { Banner, DemoNotice, EmptyState } from "@/components/ui/Feedback";
import { Chip, StatusBadge, type Tone } from "@/components/ui/Chip";
import { ProgressBar } from "@/components/ui/Progress";
import { useToast } from "@/components/ui/Toast";
import { useAppData } from "@/components/app/AppData";
import { navigateQuery, useQueryParam, useQueryValue } from "@/lib/useQueryState";
import { attendanceStats, demoAttendance, demoSemesterRange, type AttendCourse, type AttendState, type RiskLevel } from "@/lib/demo";
import { fmtMD, parseLocal } from "@/lib/dates";

// /attendance — 과목별 현황 / 이번 주 / 시간표 설정 (Frontend-Route 8절). 입력을 얼마나 쉽게 만드느냐가 화면의 전부다.

const TABS = ["status", "week", "timetable"] as const;
const STATES: AttendState[] = ["출석", "결석", "지각", "공결"];
const LEVEL_TONE: Record<RiskLevel, Tone> = { 안전: "ok", 주의: "warn", 위험: "accent", 초과: "danger" };
const BAR_TONE: Record<RiskLevel, "ok" | "warn" | "accent" | "danger"> = { 안전: "ok", 주의: "warn", 위험: "accent", 초과: "danger" };

function StateChips({ value, onChange, disabled }: { value: AttendState | null; onChange: (s: AttendState) => void; disabled?: boolean }) {
  return (
    <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="출결">
      {STATES.map((s) => {
        const on = value === s;
        const tone = s === "출석" ? "bg-ok-soft text-ok-text border-ok" : s === "결석" ? "bg-danger-soft text-danger-text border-danger" : s === "지각" ? "bg-warn-soft text-warn-text border-warn" : "bg-info-soft text-info-text border-info";
        return (
          <button
            key={s}
            type="button"
            role="radio"
            aria-checked={on}
            disabled={disabled}
            onClick={() => onChange(s)}
            className={`h-8 rounded-md border px-2.5 text-[13px] font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${on ? tone : "border-border bg-surface text-muted hover:bg-surface-2"}`}
          >
            {s}
          </button>
        );
      })}
    </div>
  );
}

export default function AttendancePage() {
  const [tab, setTab] = useQueryParam("tab", "status", TABS);
  const [data, setData] = useState<AttendCourse[]>(demoAttendance);
  const toast = useToast();
  const todayKey = new Date().toISOString().slice(0, 10);
  const unchecked = data.flatMap((c) => c.sessions.filter((s) => !s.state && !s.canceled && s.date < todayKey)).length;

  // 칩을 누르면 즉시 저장(낙관적) → 숫자·막대가 같은 프레임에서 갱신. 상태가 올라가면 알림 1회(8-1).
  const setSession = (courseId: string, sid: string, state: AttendState) => {
    const c = data.find((x) => x.courseId === courseId);
    if (!c) return;
    const prev = c.sessions.find((s) => s.id === sid);
    const hours = prev?.hours ?? 1;
    let { absent, late } = c;
    if (prev?.state === "결석") absent -= hours;
    if (prev?.state === "지각") late -= 1;
    if (state === "결석") absent += hours;
    if (state === "지각") late += 1;
    const next = { ...c, absent, late, sessions: c.sessions.map((s) => (s.id === sid ? { ...s, state } : s)) };
    const before = attendanceStats(c).level;
    const after = attendanceStats(next).level;
    setData((xs) => xs.map((x) => (x.courseId === courseId ? next : x)));
    if (after !== before && ["주의", "위험", "초과"].includes(after)) toast(`${c.name} 결석 한도 '${after}' 단계입니다`, { tone: "error" });
  };

  const markPresent = (pairs: { courseId: string; sid: string }[]) =>
    setData((xs) =>
      xs.map((c) => {
        const ids = pairs.filter((p) => p.courseId === c.courseId).map((p) => p.sid);
        return ids.length ? { ...c, sessions: c.sessions.map((s) => (ids.includes(s.id) && !s.state ? { ...s, state: "출석" as const } : s)) } : c;
      }),
    );

  return (
    <Page>
      <PageHeader
        icon={<UserCheck />}
        title="출결"
        actions={
          <>
            <select className="field field-sm w-auto" aria-label="학기" defaultValue="2026-2">
              <option value="2026-2">2026-2학기</option>
            </select>
            <button type="button" className="btn btn-sm" onClick={() => setTab("timetable")}>
              시간표 설정
            </button>
          </>
        }
      />
      <div className="mb-5 space-y-3">
        <DemoNotice what="출결" />
        <Banner tone="neutral">학교 공식 출결 기록이 아닙니다 — 내가 입력한 값 기준입니다.</Banner>
        {unchecked > 0 && (
          <Banner
            tone="warn"
            action={
              <button type="button" className="btn btn-sm" onClick={() => setTab("week")}>
                지금 입력
              </button>
            }
          >
            확인하지 않은 수업 {unchecked}회
          </Banner>
        )}
      </div>
      <Tabs
        className="mb-5"
        label="출결 보기"
        value={tab}
        onChange={(t) => setTab(t)}
        items={[
          { key: "status", label: "과목별 현황" },
          { key: "week", label: "이번 주" },
          { key: "timetable", label: "시간표 설정" },
        ]}
      />
      {tab === "status" && <StatusTab data={data} setSession={setSession} />}
      {tab === "week" && <WeekTab data={data} setSession={setSession} markPresent={markPresent} />}
      {tab === "timetable" && <TimetableTab data={data} />}
    </Page>
  );
}

function StatusTab({ data, setSession }: { data: AttendCourse[]; setSession: (c: string, s: string, st: AttendState) => void }) {
  const open = useQueryValue("course");
  const sorted = useMemo(() => {
    const rank: Record<RiskLevel, number> = { 초과: 0, 위험: 1, 주의: 2, 안전: 3 };
    return [...data].sort((a, b) => (a.planned === 0 ? 1 : 0) - (b.planned === 0 ? 1 : 0) || rank[attendanceStats(a).level] - rank[attendanceStats(b).level]);
  }, [data]);
  const todayKey = new Date().toISOString().slice(0, 10);

  return (
    <ul className="space-y-3">
      {sorted.map((c) => {
        const st = attendanceStats(c);
        const noTable = c.planned === 0;
        const expanded = open === c.courseId;
        const hot = st.level === "위험" || st.level === "초과";
        return (
          <li key={c.courseId} className={`card overflow-hidden ${hot ? "border-accent" : ""}`}>
            <div className="p-4 md:p-5">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                <h3 className="min-w-[160px] flex-1 text-[16px] font-bold">{c.name}</h3>
                {noTable ? (
                  <span className="flex items-center gap-2 text-[13px] text-muted">
                    <span className="num">—</span>
                    <button type="button" className="btn btn-sm" onClick={() => navigateQuery({ tab: "timetable" }, "replace")}>
                      <Download aria-hidden />
                      시간표 자동으로 가져오기
                    </button>
                  </span>
                ) : (
                  <>
                    <div className="w-full max-w-[280px] min-w-[160px] flex-1">
                      <ProgressBar value={st.used} max={st.limit} tone={BAR_TONE[st.level]} label={`${c.name} 결석 ${st.used}/${st.limit}시수`} />
                    </div>
                    <span className="num text-[14px] whitespace-nowrap">
                      {st.used} / {st.limit.toFixed(2).replace(/\.?0+$/, "")}시수
                    </span>
                    <span className="text-[13px] whitespace-nowrap text-muted">남은 여유 {st.spare}회</span>
                    <StatusBadge tone={LEVEL_TONE[st.level]}>{st.level}</StatusBadge>
                  </>
                )}
              </div>
              {!noTable && (
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[13px] text-muted">
                  <span className="num">
                    총 {st.total}시수 = 예정 {c.planned} − 휴강 {c.canceled} + 보강 {c.makeup}
                  </span>
                  <button
                    type="button"
                    className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 font-semibold hover:bg-surface-3"
                    aria-expanded={expanded}
                    onClick={() => navigateQuery({ course: expanded ? null : c.courseId }, "replace")}
                  >
                    결석 {c.absent} · 지각 {c.late}
                    <ChevronDown className={`size-4 transition-transform ${expanded ? "rotate-180" : ""}`} aria-hidden />
                  </button>
                </div>
              )}
            </div>
            <AnimatePresence initial={false}>
              {expanded && (
                <motion.div
                  key="sessions"
                  initial={{ height: 0 }}
                  animate={{ height: "auto" }}
                  exit={{ height: 0 }}
                  transition={{ type: "spring", bounce: 0, visualDuration: 0.25 }}
                  style={{ overflow: "hidden" }}
                >
                  <ul className="border-t border-border bg-surface-2 px-4 py-2 md:px-5">
                    {c.sessions.map((s) => {
                      const future = s.date > todayKey;
                      const d = parseLocal(s.date);
                      return (
                        <li key={s.id} className="flex flex-wrap items-center gap-3 border-b border-border py-2 last:border-b-0">
                          <span className="flex w-36 items-center gap-2 text-[14px]">
                            {!s.state && !s.canceled && !future && <span className="size-1.5 rounded-full bg-accent" aria-label="미입력" />}
                            <span className={`num ${future ? "text-faint" : ""}`}>
                              {fmtMD(d)} {s.periods}
                            </span>
                          </span>
                          {s.canceled ? (
                            <span className="text-[13px] text-faint">— 휴강 —</span>
                          ) : future ? (
                            <span className="text-[13px] text-faint">(다가옴)</span>
                          ) : (
                            <StateChips value={s.state} onChange={(v) => setSession(c.courseId, s.id, v)} />
                          )}
                        </li>
                      );
                    })}
                  </ul>
                  <div className="flex justify-end px-4 py-2 md:px-5">
                    <button type="button" className="btn btn-ghost btn-sm">
                      <Plus aria-hidden />
                      보강 추가
                    </button>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </li>
        );
      })}
    </ul>
  );
}

function WeekTab({
  data,
  setSession,
  markPresent,
}: {
  data: AttendCourse[];
  setSession: (c: string, s: string, st: AttendState) => void;
  markPresent: (pairs: { courseId: string; sid: string }[]) => void;
}) {
  const [offset, setOffset] = useState(0);
  const base = new Date();
  base.setDate(base.getDate() - ((base.getDay() + 6) % 7) + offset * 7);
  const from = base.toISOString().slice(0, 10);
  const toD = new Date(base);
  toD.setDate(toD.getDate() + 6);
  const to = toD.toISOString().slice(0, 10);
  const rows = data
    .flatMap((c) => c.sessions.filter((s) => s.date >= from && s.date <= to && !s.canceled).map((s) => ({ c, s })))
    .sort((a, b) => a.s.date.localeCompare(b.s.date));

  return (
    <div className="card p-4 md:p-5">
      <div className="mb-3 flex items-center gap-2">
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOffset((o) => o - 1)}>
          <ChevronLeft aria-hidden />
          지난 주
        </button>
        <span className="num text-[14px] font-semibold">
          {fmtMD(base)} ~ {fmtMD(toD)}
        </span>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOffset((o) => o + 1)}>
          다음 주
          <ChevronRight aria-hidden />
        </button>
        <button type="button" className="btn btn-sm ml-auto" disabled={rows.length === 0} onClick={() => markPresent(rows.map(({ c, s }) => ({ courseId: c.courseId, sid: s.id })))}>
          모두 출석으로
        </button>
      </div>
      {rows.length === 0 ? (
        <EmptyState compact title="이번 주 수업 일정이 없습니다" />
      ) : (
        <ul className="divide-y divide-border">
          {rows.map(({ c, s }) => (
            <li key={s.id} className="flex flex-wrap items-center gap-3 py-2.5">
              <span className="num w-20 text-[14px] font-semibold">{fmtMD(parseLocal(s.date))}</span>
              <span className="min-w-[140px] flex-1 text-[14px]">
                {c.name} <span className="text-muted">{s.periods}</span>
              </span>
              <StateChips value={s.state} onChange={(v) => setSession(c.courseId, s.id, v)} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TimetableTab({ data }: { data: AttendCourse[] }) {
  const { courses } = useAppData();
  const toast = useToast();
  const rows = courses.length
    ? courses.map((c) => ({ id: c.id, name: c.short, code: c.code, slots: data.find((d) => d.courseId === c.id)?.slots ?? [] }))
    : data.map((d) => ({ id: d.courseId, name: d.name, code: d.code, slots: d.slots }));

  return (
    <div className="space-y-4">
      {courses.length === 0 && <Banner tone="warn">e클래스 동기화를 먼저 해 주세요 — 과목 목록이 없어 예시 과목을 보여 줍니다.</Banner>}
      <div className="flex justify-end">
        <button type="button" className="btn btn-primary btn-sm" onClick={() => toast("시간표 조회 API 가 아직 없습니다")}>
          <Download aria-hidden />
          시간표 자동으로 가져오기
        </button>
      </div>
      <div className="overflow-x-auto rounded-xl border border-border bg-surface">
        <table className="w-full min-w-[640px] text-[14px]">
          <thead className="bg-surface-2 text-left text-[12px] text-muted">
            <tr>
              <th className="px-4 py-2 font-semibold">과목</th>
              <th className="px-2 py-2 font-semibold">요일·교시</th>
              <th className="w-24 px-2 py-2 font-semibold">한도</th>
              <th className="w-36 px-2 py-2 font-semibold">지각 환산</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-border">
                <td className="px-4 py-2.5">
                  <span className="font-semibold">{r.name}</span> <span className="text-[12px] text-faint">({r.code})</span>
                </td>
                <td className="px-2 py-2.5">
                  {r.slots.length ? (
                    <span className="flex flex-wrap gap-1.5">
                      {r.slots.map((s) => (
                        <Chip key={s.day + s.periods} tone="primary" square>
                          {s.day} {s.periods}
                          {s.auto && <span className="font-normal opacity-70">· 자동</span>}
                        </Chip>
                      ))}
                    </span>
                  ) : (
                    <span className="flex items-center gap-2 text-[13px] text-warn-text">
                      <TriangleAlert className="size-3.5" aria-hidden />
                      못 찾음
                      <button type="button" className="btn btn-sm">
                        <Plus aria-hidden />
                        요일·교시 입력
                      </button>
                    </span>
                  )}
                </td>
                <td className="px-2 py-2.5">
                  <select className="field field-sm" defaultValue="1/4" aria-label={`${r.name} 한도`}>
                    <option>1/4</option>
                    <option>1/3</option>
                  </select>
                </td>
                <td className="px-2 py-2.5">
                  <select className="field field-sm" defaultValue="3" aria-label={`${r.name} 지각 환산`}>
                    <option value="2">2회 = 결석1</option>
                    <option value="3">3회 = 결석1</option>
                  </select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[13px] text-muted">
        학기: 개강 {demoSemesterRange.start} · 종강 {demoSemesterRange.end} ({demoSemesterRange.source}에서) · 시험주처럼 수업이 없는 주는 회차 목록에서 &lsquo;휴강&rsquo;으로 표시하세요
      </p>
      <div className="flex justify-end">
        <button type="button" className="btn btn-primary" onClick={() => toast("운영체제 30회차(43시수)를 만들었습니다 (예시)", { tone: "success" })}>
          저장하고 회차 만들기
        </button>
      </div>
    </div>
  );
}
