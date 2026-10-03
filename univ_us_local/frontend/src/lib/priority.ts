// F7 과제 우선순위 — 요구사항정의서 F7 5절 계산 규칙.
//   h = 마감 − 지금 (시간), w = 예상 소요 × 안전계수 1.5, s = h − w
//   놓친 마감: h < 0 · 지금 해야 함: s ≤ 0 또는 h ≤ 24 · 이번 주: s ≤ 7일 · 나중에: 그 외
// 사용자가 고친 소요시간·'내가 체크함'은 F6 과제 원장(서버)에 있고 /api/events 의 deadline 에 실려 온다.
// ⚠ 순위 계산은 F7 을 붙일 때 백엔드 GET /api/assignments?sort=priority 로 옮긴다(Frontend-Route 12-4). 그때까지 여기서.

import type { CalEvent, DeadlineProps } from "./types";
import { daysUntil, fmtHours, parseLocal } from "./dates";

export const SAFETY_FACTOR = 1.5;
export const ESTIMATE_OPTIONS = [0.5, 1, 2, 3, 5, 8] as const;

export type PriorityGroup = "overdue" | "now" | "week" | "later";

export const GROUP_META: Record<PriorityGroup, { label: string; tone: "danger" | "accent" | "neutral" }> = {
  overdue: { label: "놓친 마감", tone: "danger" },
  now: { label: "지금 해야 함", tone: "accent" },
  week: { label: "이번 주", tone: "neutral" },
  later: { label: "나중에", tone: "neutral" },
};

export interface Assignment {
  id: string;
  title: string;
  ev: CalEvent;
  p: DeadlineProps;
  due: Date;
  kindLabel: "과제" | "퀴즈" | "동영상" | "프로젝트";
  submitted: boolean; // e클래스 제출 완료
  userDone: boolean; // 내가 체크함 (e클래스 밖에서 제출)
  estimate: number;
  estimateSource: "default" | "user";
  remainingHours: number;
  neededHours: number;
  slackHours: number;
  group: PriorityGroup;
  reason: string;
}

export function kindOf(p: DeadlineProps, title: string): Assignment["kindLabel"] {
  const t = `${p.type} ${title}`;
  if (/퀴즈|quiz/i.test(t)) return "퀴즈";
  if (/동영상|영상|video|vod/i.test(t)) return "동영상";
  if (/프로젝트|project|캡스톤/i.test(t)) return "프로젝트";
  return "과제";
}

const DEFAULT_HOURS: Record<Assignment["kindLabel"], number> = { 과제: 3, 퀴즈: 0.5, 동영상: 1, 프로젝트: 5 };

function reasonOf(h: number, w: number, s: number, est: number): string {
  if (h < 0) {
    const d = Math.ceil(-h / 24);
    return d <= 1 ? `마감 ${Math.max(1, Math.round(-h))}시간 지남 · 미제출` : `마감 ${d}일 지남 · 미제출`;
  }
  if (s <= 0) return `지금 시작해도 빠듯 (${fmtHours(w)} 필요, ${fmtHours(h)} 남음)`;
  if (h <= 24) return `마감 ${Math.max(1, Math.round(h))}시간 전 · ${fmtHours(est)} 필요`;
  return `마감 ${Math.round(h / 24)}일 전 · ${fmtHours(est)} 필요`;
}

export function buildAssignments(events: CalEvent[], now = new Date()): Assignment[] {
  const out: Assignment[] = [];
  for (const ev of events) {
    if (ev.extendedProps.kind !== "deadline") continue;
    const p = ev.extendedProps;
    const due = parseLocal(p.due);
    const kindLabel = kindOf(p, ev.title);
    const est = Math.max(0.25, p.estimateHours ?? DEFAULT_HOURS[kindLabel]);
    const h = (due.getTime() - now.getTime()) / 3_600_000;
    const w = est * SAFETY_FACTOR;
    const s = h - w;
    const group: PriorityGroup = h < 0 ? "overdue" : s <= 0 || h <= 24 ? "now" : s <= 24 * 7 ? "week" : "later";
    out.push({
      id: ev.id,
      title: ev.title,
      ev,
      p,
      due,
      kindLabel,
      submitted: p.submitted,
      userDone: !p.submitted && !!p.userDone,
      estimate: est,
      estimateSource: p.estimateHours !== null && p.estimateHours !== undefined ? "user" : "default",
      remainingHours: h,
      neededHours: w,
      slackHours: s,
      group,
      reason: reasonOf(h, w, s, est),
    });
  }
  return out;
}

export const isOpen = (a: Assignment) => !a.submitted && !a.userDone;

const ORDER: PriorityGroup[] = ["overdue", "now", "week", "later"];

/** 급한 순 — 그룹 → s 오름차순 → 마감 → 과목명 (안정 정렬) */
export function sortByPriority(list: Assignment[]): Assignment[] {
  return [...list].sort(
    (a, b) =>
      ORDER.indexOf(a.group) - ORDER.indexOf(b.group) ||
      a.slackHours - b.slackHours ||
      a.due.getTime() - b.due.getTime() ||
      a.p.courseShort.localeCompare(b.p.courseShort, "ko"),
  );
}

/** 오늘 남은 시간 = 취침(24:00) − 지금 (수업·일정 차감은 백엔드가 생기면) */
export function hoursLeftToday(now = new Date()): number {
  const bed = new Date(now);
  bed.setHours(24, 0, 0, 0);
  return Math.max(0, (bed.getTime() - now.getTime()) / 3_600_000);
}

/** 2주 넘게 지난 놓친 마감은 접어 둔다 */
export const isStaleOverdue = (a: Assignment, now = new Date()) => a.group === "overdue" && daysUntil(a.due, now) < -14;
