// F1 학사일정 — GET /api/academic/events 가 주는 모양 (F1_Bachelor_agent/bachelor/service.py build_event 와 짝).
// 요구사항정의서 F1 6절 `AcademicEvent`. 날짜는 캘린더와 같은 규칙: 종일 일정의 end 는 exclusive.

import { addDays, fmtMD, fmtTime, parseLocal } from "./dates";

export type AcademicType = "registration" | "tuition" | "course_reg" | "grade" | "exam" | "vacation" | "holiday" | "event" | "etc";

// 색은 요구사항정의서 F1 '색·아이콘' 표 — 과목 색·내 일정 색과 겹치지 않는 어두운 톤 (백엔드 TYPE_META 와 같은 값)
export const ACADEMIC_TYPE_META: Record<AcademicType, { label: string; color: string }> = {
  registration: { label: "학적", color: "#334155" },
  tuition: { label: "등록·납부", color: "#b45309" },
  course_reg: { label: "수강신청·정정", color: "#4338ca" },
  grade: { label: "성적", color: "#0f766e" },
  exam: { label: "시험", color: "#9a3412" },
  vacation: { label: "개강·방학", color: "#64748b" },
  holiday: { label: "휴업일", color: "#9f1239" },
  event: { label: "행사", color: "#7e22ce" },
  etc: { label: "기타", color: "#475569" },
};

export const typeMeta = (t: string) => ACADEMIC_TYPE_META[t as AcademicType] ?? ACADEMIC_TYPE_META.etc;

export type ReminderCode = "d7" | "d3" | "d1" | "end1" | "m30";

export interface ReminderOpt {
  code: ReminderCode;
  label: string; // D-7 · 종료 전날 · 시작 30분 전
  enabled: boolean;
}

export interface AcademicSource {
  key: string;
  name: string;
  url: string;
  postedAt: string | null;
  fetchedAt: string;
  removed: boolean; // 원문(표 행·공지)에서 사라짐
}

export interface Audience {
  grades: number[] | null;
  colleges: string[] | null;
  departments: string[] | null;
  enrollment: string[] | null;
  roles: string[] | null; // faculty · graduate
  raw: string;
}

export type AcademicStatusKey = "auto" | "review" | "approved" | "hidden";

export interface AcademicEvent {
  id: string; // ac:<source>:<hash>
  title: string;
  start: string | null; // null = 날짜를 못 읽음(이미지 공지) — 확인 필요에만 나온다
  end: string | null; // 종일이면 exclusive
  allDay: boolean;
  endTime: string | null; // 종일 기간인데 끝 시각만 있는 경우 '16:00' (지어내지 않는다)
  type: AcademicType;
  typeLabel: string;
  color: string;
  sources: AcademicSource[];
  evidence: { field: string; quote: string; source: string }[];
  confidence: number;
  weak: boolean; // 신뢰도 < 0.5
  needsOcr: boolean;
  audience: Audience;
  appliesToMe: boolean | null; // null = 판단 불가(프로필 부족)
  status: AcademicStatusKey;
  onCalendar: boolean;
  pinned: boolean; // 해당 없음이어도 '내 캘린더에 담기'
  changed: { at: string; before: { start: string | null; end: string | null; allDay: boolean; endTime: string | null } | null } | null;
  removed: boolean;
  userEdited: boolean;
  reminders: ReminderOpt[];
  memo: string;
  actionUrl: string | null;
  actionLabel: string | null;
  semester: string; // 2026-2
  flags: string[];
  firstSeen: string;
  /** 마지막 수집에서 처음 찾음 — 목록의 '신규' 칩 */
  isNew: boolean;
}

export interface AcademicOverview {
  semesters: string[];
  currentSemester: string;
  updatedAt: string | null;
  profileMissing: boolean;
  items: AcademicEvent[];
}

export interface AcademicPatch {
  status?: "approved" | "hidden" | "restore";
  start?: string; // 승인할 때 고친 날짜 — YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM
  end?: string | null; // 마지막 날(포함) 또는 끝 시각
  memo?: string;
  pinned?: boolean;
  reminders?: Partial<Record<ReminderCode, boolean>>;
}

export const isConfirmed = (e: AcademicEvent) => e.status === "auto" || e.status === "approved";

/** 마지막 날(포함). 종일 일정의 exclusive end 를 하루 당긴다. */
export function lastDay(e: Pick<AcademicEvent, "start" | "end" | "allDay">): Date | null {
  if (!e.start) return null;
  const s = parseLocal(e.start);
  if (!e.end) return s;
  const end = parseLocal(e.end);
  if (e.allDay) return addDays(end, -1);
  // 끝이 '다음 날 00:00' 이면 그 전날까지
  return end.getHours() === 0 && end.getMinutes() === 0 && end > s ? addDays(end, -1) : end;
}

/** '8/24(월) ~ 8/28(금)' · '8/5(화) 10:00' · '10/1(목) ~ 10/2(금) 16:00' */
export function academicPeriod(e: Pick<AcademicEvent, "start" | "end" | "allDay" | "endTime">): string {
  if (!e.start) return "날짜 미확인";
  const s = parseLocal(e.start);
  const last = lastDay(e)!;
  const head = e.allDay ? fmtMD(s) : `${fmtMD(s)} ${fmtTime(s)}`;
  const endHasTime = !e.allDay && e.end && !(parseLocal(e.end).getHours() === 0 && parseLocal(e.end).getMinutes() === 0);
  const sameDay = last.toDateString() === s.toDateString();
  if (sameDay) {
    if (endHasTime) return `${head} ~ ${fmtTime(parseLocal(e.end!))}`;
    return e.endTime ? `${head} ${e.endTime} 마감` : head;
  }
  const tail = endHasTime ? `${fmtMD(last)} ${fmtTime(parseLocal(e.end!))}` : `${fmtMD(last)}${e.endTime ? ` ${e.endTime}` : ""}`;
  return `${head} ~ ${tail}`;
}

/** 대상 문구 — 비어 있으면 전체 학생 */
export function audienceText(a: Audience): string {
  if (a.raw) return a.raw;
  if (a.roles?.includes("faculty")) return "교원";
  if (a.roles?.includes("graduate")) return "대학원생";
  return "전체 학생";
}

/** '2026-2' → '2026학년도 2학기' */
export const semesterLabel = (s: string) => {
  const [y, n] = s.split("-");
  return n ? `${y}학년도 ${n}학기` : s;
};

/** 확인 필요 카드의 입력 초기값 — 종일이면 날짜, 시각이 있으면 datetime-local, 끝은 마지막 날(포함) */
export function toInputs(e: AcademicEvent): { start: string; end: string; withTime: boolean } {
  if (!e.start) return { start: "", end: "", withTime: false };
  const withTime = !e.allDay;
  if (!withTime) {
    const last = lastDay(e)!;
    const pad = (n: number) => String(n).padStart(2, "0");
    const end = e.end ? `${last.getFullYear()}-${pad(last.getMonth() + 1)}-${pad(last.getDate())}` : "";
    return { start: e.start.slice(0, 10), end, withTime };
  }
  return { start: e.start.slice(0, 16), end: e.end ? e.end.slice(0, 16) : "", withTime };
}
