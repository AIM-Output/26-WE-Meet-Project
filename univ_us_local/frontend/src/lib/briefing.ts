// C4 브리핑 (요구사항 F10 아침 브리핑) — C4_Briefing_agent/briefing/api.py 와 짝.
// 브리핑은 서버가 하루 한 번 만드는 **스냅샷**이다. 화면은 그리기만 하고 숫자를 다시 계산하지 않는다(Frontend-Route 15-6).

import type { CalEvent } from "./types";
import { addDays, daysUntil, isSameDay, parseLocal, startOfDay } from "./dates";
import { buildAssignments, isOpen } from "./priority";

export type BriefingSectionKey = "attention" | "classes" | "events" | "deadlines" | "priority" | "alerts";
export type BriefingIcon = "alert" | "class" | "calendar" | "clock" | "flame" | "bell";
export type BriefingSource = "scheduled" | "catchup" | "manual";

export interface BriefingItem {
  text: string;
  sub?: string | null;
  href: string;
  tone?: "danger" | "warn" | "muted" | null;
  tag?: string | null; // 과제 · 학사 · 장학 · 대외활동 · 시험 · 학습 블록 · 할 일 · 출결 …
}

export interface BriefingSection {
  key: BriefingSectionKey;
  label: string;
  icon: BriefingIcon;
  link: string | null; // '+N건 더' 가 가는 곳
  count: number;
  items: BriefingItem[];
  more: number; // 스냅샷에 다 싣지 않은 줄 수
  empty: string | null; // 비었을 때 한 줄 (마감 임박만)
  footer: string | null; // 먼저 할 것 '합계 7시간'
}

export type BriefingCounts = Record<BriefingSectionKey | "total", number>;

export interface Briefing {
  id: string; // br:2026-10-26
  date: string;
  generatedAt: string; // ISO
  scheduledFor: string; // HH:MM
  source: BriefingSource;
  firstSource: BriefingSource;
  firstGeneratedAt: string;
  missed: boolean; // 처음에 놓친 브리핑(catchup)이었다 — 다시 만들어도 남는다
  headline: string | null; // LLM 한 줄 — 실패하면 null (그 줄만 빠진다)
  summary: string; // '수업 3 · 마감 3' — 접힘·알림 본문
  sections: BriefingSection[];
  counts: BriefingCounts;
  gaps: string[]; // 못 읽은 재료(기능 이름)
  empty: boolean;
  emptyText: string | null;
  model: string | null;
  promptVersion: string | null;
}

export type BriefingListItem = Pick<
  Briefing,
  "id" | "date" | "generatedAt" | "scheduledFor" | "source" | "firstSource" | "firstGeneratedAt" | "missed" | "headline" | "summary" | "counts" | "empty"
>;

/** ready 있음 · before 예정 시각 전(카드 없음) · pending 수집이 끝나기를 기다림(스켈레톤) · off 꺼짐(카드 없음) */
export type BriefingState = "ready" | "before" | "pending" | "off";

export interface BriefingToday {
  state: BriefingState;
  date: string;
  enabled: boolean;
  scheduledFor: string;
  scheduledAt: string;
  waitingFor: string[];
  created: boolean;
  briefing: Briefing | null;
}

export interface BriefingHistory {
  items: BriefingListItem[];
  keepDays: number;
  today: string;
}

export interface BriefingSettings {
  enabled: boolean;
  time: string;
  keepDays: number;
  defaults: { enabled: boolean; time: string; keepDays: number };
  changed: string[];
  keepDaysChoices: number[];
  llm: boolean; // 한 줄 요약 LLM 이 설정돼 있나
}

export interface BriefingSettingsPatch {
  enabled?: boolean | null;
  time?: string | null;
  keepDays?: number | null;
  reset?: boolean;
}

/** /api/status 의 briefing 칸 — 기능 타일 · 오늘 브리핑을 다시 받을 신호(updatedAt) */
export interface BriefingStatus {
  available: boolean;
  error?: string;
  enabled?: boolean;
  time?: string;
  state?: BriefingState;
  waitingFor?: string[];
  updatedAt?: string | null;
  llm?: boolean;
  today?: Pick<Briefing, "date" | "generatedAt" | "source" | "missed" | "summary" | "counts" | "headline"> | null;
}

const hm = (iso: string) => iso.slice(11, 16);

/** 생성 표시 — '08:00 생성' · '놓친 브리핑 · 08:00 예정 → 10:24 생성' · '11:02 다시 만듦' (F10-R23) */
export function generatedLabel(b: Pick<Briefing, "source" | "missed" | "scheduledFor" | "generatedAt" | "firstGeneratedAt">): string {
  if (b.source === "manual") return `${hm(b.generatedAt)} 다시 만듦`;
  if (b.missed) return `놓친 브리핑 · ${b.scheduledFor} 예정 → ${hm(b.firstGeneratedAt)} 생성`;
  return `${hm(b.generatedAt)} 생성`;
}

/** 대시보드 '오늘 한눈에' 숫자 — 브리핑 스냅샷이 아니라 지금 캘린더 기준(브리핑 전·후 모두 보인다).
 *  오늘 일정 = 오늘에 걸친 내 일정·학사 일정 · 3일 안 마감 = 열린 과제 마감 + 알림이 켜진 학사 D-1~3 */
export function todayGlance(events: CalEvent[], now = new Date()): { today: number; soon: number } {
  const today = startOfDay(now);
  const tomorrow = addDays(today, 1);
  const on = (ev: CalEvent) => {
    const s = parseLocal(ev.start);
    if (ev.allDay) {
      const endEx = ev.end ? parseLocal(ev.end) : addDays(startOfDay(s), 1);
      return startOfDay(s) <= today && today < endEx;
    }
    return isSameDay(s, today);
  };
  const mine = events.filter((e) => (e.extendedProps.kind === "user" || e.extendedProps.kind === "academic") && on(e)).length;
  const academicSoon = events.filter((e) => {
    if (e.extendedProps.kind !== "academic" || e.extendedProps.reminders.length === 0) return false;
    const d = daysUntil(parseLocal(e.start), now);
    return d >= 1 && d <= 3;
  }).length;
  const soon = buildAssignments(events, null, now)
    .filter(isOpen)
    .filter((a) => a.due && a.due >= now && a.due < addDays(tomorrow, 3)).length;
  return { today: mine, soon: soon + academicSoon };
}
