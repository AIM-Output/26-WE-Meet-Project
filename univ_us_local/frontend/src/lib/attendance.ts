// F3 출결 — /api/attendance/* 가 돌려주는 모양 (F3_Attendance_agent/attendance/service.py 와 짝).
// 계산(총 횟수·허용·상태)은 백엔드 규칙 코드(calc.py) 한 곳에서만 한다. 화면은 받은 숫자를 그대로 쓴다.
// 단위는 '회' — 수업한 날 하나가 1회다(전남대는 출석을 하루 단위로 부른다, 2026-09-29 수정).

import type { Tone } from "@/components/ui/Chip";

export type Attendance = "present" | "absent" | "late" | "excused";
export type Level = "safe" | "caution" | "danger" | "over";
export type SessionState = "scheduled" | "canceled";
export type CancelSource = "academic" | "eclass" | "user";

/** 사용자가 적는 칸 = 출석 · 결석 · 지각 · 공결 + 휴강 (조퇴는 없다) */
export const ATT_LABEL: Record<Attendance, string> = { present: "출석", absent: "결석", late: "지각", excused: "공결" };
export const ATT_CHIPS: Attendance[] = ["present", "absent", "late", "excused"];
export const ATT_CHIP_CLASS: Record<Attendance, string> = {
  present: "bg-ok-soft text-ok-text border-ok",
  absent: "bg-danger-soft text-danger-text border-danger",
  late: "bg-warn-soft text-warn-text border-warn",
  excused: "bg-info-soft text-info-text border-info",
};
export const CANCEL_CHIP_CLASS = "bg-surface-3 text-text border-border-strong";
export const CANCEL_SOURCE_LABEL: Record<CancelSource, string> = { academic: "학사일정", eclass: "e클래스 공지", user: "내가 표시" };

/** 칩 한 번이 서버에 보내는 것 — 출결만, 휴강만, 또는 휴강을 풀면서 출결 */
export type SessionPatch = { attendance?: Attendance | null; state?: SessionState };

export const LEVEL_LABEL: Record<Level, string> = { safe: "안전", caution: "주의", danger: "위험", over: "초과" };
export const LEVEL_TONE: Record<Level, Tone> = { safe: "ok", caution: "warn", danger: "accent", over: "danger" };
export const LEVEL_BAR: Record<Level, "ok" | "warn" | "accent" | "danger"> = { safe: "ok", caution: "warn", danger: "accent", over: "danger" };
export const LEVEL_RANK: Record<Level, number> = { safe: 0, caution: 1, danger: 2, over: 3 };

export const WEEKDAYS = ["월", "화", "수", "목", "금", "토", "일"]; // 백엔드 weekday 0 = 월
export const LIMIT_OPTIONS: { value: number; label: string }[] = [
  { value: 0.25, label: "1/4" },
  { value: 1 / 3, label: "1/3" },
  { value: 0.2, label: "1/5" },
];
export const LATE_OPTIONS: { value: number; label: string }[] = [
  { value: 3, label: "3회 = 결석1" },
  { value: 2, label: "2회 = 결석1" },
  { value: 4, label: "4회 = 결석1" },
  { value: 0, label: "환산 안 함" },
];

export interface Meeting {
  weekday: number; // 0 월 ~ 6 일
  periods: number[];
  room?: string;
}

export interface AutoCancel {
  source: "academic" | "eclass";
  reason: string | null; // 휴업일 이름 · 공지 제목
  url: string | null; // 공지 링크
  posted?: string;
}

export interface AttSession {
  id: string; // cl:<courseId>:<날짜> (보강은 :mk) — 캘린더 class 일정 id 와 같다
  courseId: string;
  date: string;
  weekday: number;
  periods: number[];
  start: string; // 'HH:MM'
  end: string;
  room: string;
  kind: "regular" | "makeup";
  origin: "timetable" | "school" | "user";
  state: SessionState;
  baseState: SessionState;
  autoCancel: AutoCancel | null; // 학사일정·공지가 휴강이라고 한 근거 (되돌려도 남는다)
  cancelSource: CancelSource | null; // 지금 휴강이면 누가
  makeupFor: string | null;
  makeupName: string | null;
  attendance: Attendance | null;
  recorded?: Attendance | null; // 휴강으로 바꿔도 남아 있는 기록
  memo: string;
  started: boolean;
  ended: boolean;
}

export interface AttSummary {
  totalCount: number;
  plannedCount: number;
  canceledCount: number;
  makeupCount: number;
  autoCanceledCount: number;
  autoCanceled: { academic: number; eclass: number };
  absentCount: number;
  lateCount: number;
  excusedCount: number;
  presentCount: number;
  lateCounted: number;
  convertedCount: number;
  manualAdjust: { absent: number; late: number };
  effectiveAbsent: number;
  allowed: number;
  remaining: number;
  spareSessions: number | null;
  level: Level | null;
  levelLabel: string;
  uncheckedSessions: number;
  upcomingSessions: number;
  sessionCount: number;
  basis: string;
}

export interface CourseSettings {
  limitRatio: number;
  lateToAbsence: number;
}

export interface NoticeHint {
  reason: string; // 공지 제목
  url: string | null;
  posted: string;
  date?: string;
  why: string;
}

export type TimetableStatus = "found" | "not_found" | "no_time" | "parse_error" | "no_code" | "error" | null;

export interface AttCourse {
  id: string;
  semester: string;
  name: string;
  short: string;
  code: string;
  section: string;
  color: string | null;
  source: "eclass" | "manual";
  excluded: boolean;
  settings: CourseSettings;
  adjust: { absent: number; late: number };
  timetable: {
    meetings: Meeting[];
    text: string;
    filledBy: "auto" | "user" | null;
    versions: { validFrom: string; meetings: Meeting[]; filledBy: string; text: string; updatedAt: string }[];
    status: TimetableStatus;
    message: string | null;
    raw: { times: string; rooms: string[]; professor: string; campus: string; credits: string; category: string } | null;
    auto: Meeting[] | null;
    autoText: string;
    checkedAt: string | null;
  };
  summary: AttSummary;
  sessions: AttSession[];
  orphans: { id: string; date: string; attendance: Attendance | null; state: string | null; memo: string | null }[];
  alertLevel: Level | null;
  noticeHints: NoticeHint[]; // 공지에 휴강이 있지만 걸 회차를 못 찾은 것 — 확인 필요
}

export interface SemesterInfo {
  id: string;
  label: string;
  start: string | null;
  end: string | null;
  startSource: "user" | "academic" | null;
  endSource: "user" | "academic" | null;
  auto: { start: string | null; end: string | null };
  holidays: { date: string; name: string; source: "fixed" | "academic" | "user" }[];
  makeupDays: { date: string; original: string; name: string }[];
  userHolidays: { date: string; name: string }[];
  academicAvailable: boolean;
  warnings: string[];
}

export interface PeriodView {
  mwf: Record<string, [string, string]>;
  tt: Record<string, [string, string]>;
  edited: boolean;
  source: string;
  sourceUrl: string;
  weekdayModule: Record<string, "mwf" | "tt">;
}

export interface AttAlert {
  courseId: string;
  name: string;
  level: Level;
  levelLabel: string;
  title: string;
  body: string;
  href: string;
}

export interface AttTotals {
  courses: number;
  withTimetable: number;
  needsTimetable: string[];
  unchecked: number;
  risky: { id: string; name: string; level: Level; levelLabel: string; remaining: number; spareSessions: number | null }[];
  caution: string[];
  worstLevel: Level | null;
  worstLabel: string;
  sessions: number;
}

export interface AttendanceOverview {
  semester: SemesterInfo;
  current: string;
  semesters: { id: string; label: string; start: string | null; end: string | null; current: boolean }[];
  courses: AttCourse[];
  totals: AttTotals;
  periods: PeriodView;
  academicWarning: { threshold: number; scale: number; sourceUrl: string; gpa: { value: number; scale: number } | null; below: boolean | null; message: string | null };
  notices: { available: boolean }; // e클래스 게시판(자동 휴강 원천)을 읽었는지
  eclassCourses: number | null;
  updatedAt: string | null;
  alerts: AttAlert[];
  now: string;
}

export interface TimetableImportState {
  running: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  ok: boolean | null;
  semester: string | null;
  progress: { done: number; total: number } | null;
  error: string | null;
  alreadyRunning?: boolean;
  result: {
    filled: { name: string; text: string }[];
    kept: { name: string; text: string }[];
    same: string[];
    missing: { name: string; message: string }[];
    errors: { name: string; message: string }[];
    found: number;
    total: number;
  } | null;
}

/** /api/status 의 attendance 칸 (기능 타일) */
export interface AttendanceStatus extends Partial<AttTotals> {
  available: boolean;
  error?: string;
  semester?: string;
  label?: string;
  semesterMissing?: boolean;
  updatedAt?: string | null;
  import?: TimetableImportState;
}

export interface MutationResult {
  course: AttCourse;
  alerts: AttAlert[];
  updatedAt: string | null;
}

/** 캘린더에 섞여 오는 수업 회차 (C1 kind=class) */
export interface ClassProps {
  kind: "class";
  courseId: string;
  semester: string;
  courseName: string;
  courseCode: string;
  section: string;
  color: string;
  periods: number[];
  periodsText: string;
  room: string;
  state: SessionState;
  cancelSource: CancelSource | null;
  autoCancel: AutoCancel | null;
  attendance: Attendance | null;
  sessionKind: "regular" | "makeup";
  origin: "timetable" | "school" | "user";
  makeupName: string | null;
  makeupFor: string | null;
  memo: string;
  started: boolean;
  level: Level | null;
  levelLabel: string;
  remaining: number;
  spareSessions: number | null;
}

/* ---------------------------------------------------------------- 표시 도우미 */

/** 0.25 → '1/4' */
export function ratioLabel(r: number): string {
  const hit = LIMIT_OPTIONS.find((o) => Math.abs(o.value - r) < 1e-6);
  return hit ? hit.label : `${Math.round(r * 100)}%`;
}

/** 횟수 숫자 — 7.75 · 32 */
export function num(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return Number.isInteger(n) ? String(n) : String(Math.round(n * 100) / 100);
}

export function meetingText(m: Meeting): string {
  return `${WEEKDAYS[m.weekday]} ${m.periods.join("·")}교시`;
}

export function periodsText(s: Pick<AttSession, "periods">): string {
  return `${s.periods.join("·")}교시`;
}

/** 교시 표에서 그 요일·교시의 시각 */
export function periodTime(pv: PeriodView | null | undefined, weekday: number, period: number): [string, string] | null {
  if (!pv) return null;
  const mod = pv.weekdayModule[WEEKDAYS[weekday]] ?? "mwf";
  return (pv[mod] ?? pv.mwf)[String(period)] ?? pv.mwf[String(period)] ?? null;
}

/** 요일마다 고를 수 있는 교시 수 — 화·목(75분)은 10교시까지, 나머지 15교시 */
export function maxPeriod(pv: PeriodView | null | undefined, weekday: number): number {
  if (!pv) return weekday === 1 || weekday === 3 ? 10 : 15;
  const mod = pv.weekdayModule[WEEKDAYS[weekday]] ?? "mwf";
  return Object.keys(pv[mod]).length;
}

export function sameMeetings(a: Meeting[], b: Meeting[]): boolean {
  const k = (ms: Meeting[]) => JSON.stringify(ms.map((m) => [m.weekday, m.periods]));
  return k(a) === k(b);
}

/** 칩 하나가 보낼 것 — 휴강이면 출결 칩은 '휴강 풀고 출결', 같은 칩을 다시 누르면 미입력/휴강 해제 */
export function chipPatch(s: { state: SessionState; attendance: Attendance | null }, chip: Attendance | "canceled"): SessionPatch {
  if (chip === "canceled") return { state: s.state === "canceled" ? "scheduled" : "canceled" };
  if (s.state === "canceled") return { state: "scheduled", attendance: chip };
  return { attendance: s.attendance === chip ? null : chip };
}

/** 화면에서 먼저 반영(낙관적)하는 한 칸 — 숫자는 서버 응답이 오면 바뀐다 */
export function applyPatch(c: AttCourse, id: string, p: SessionPatch): AttCourse {
  return {
    ...c,
    sessions: c.sessions.map((s) =>
      s.id !== id
        ? s
        : {
            ...s,
            ...(p.state ? { state: p.state, cancelSource: p.state === "canceled" ? (s.cancelSource ?? "user") : null } : {}),
            ...(p.attendance !== undefined ? { attendance: p.attendance } : p.state === "canceled" ? { attendance: null } : {}),
          },
    ),
  };
}

/** 자동 휴강 근거 한 줄 — '학사일정 · 추석연휴' / 'e클래스 공지 · 오늘 수업 휴강(9/16)' */
export function autoCancelText(a: AutoCancel | null | undefined): string {
  if (!a) return "";
  return `${CANCEL_SOURCE_LABEL[a.source]}${a.reason ? ` · ${a.reason}` : ""}`;
}
