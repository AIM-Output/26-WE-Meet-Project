// F7 과제 우선순위 — 계산은 전부 서버(F7_Task_agent, GET /api/priority)가 한다. 화면은 그 값을 그대로 그린다.
//   h = 마감 − 지금, w = 예상 소요 × 안전계수, s = h − w
//   놓친 마감: h < 0 · 지금 해야 함: s ≤ 0 또는 h ≤ 24 · 이번 주: s ≤ 7일 · 나중에: 그 외 · 마감 없음: 순위 밖
// 사용자가 고친 소요시간·'내가 체크함'은 F6 과제 원장(서버)에 있고 /api/events 의 deadline 에 실려 온다.
// 여기서는 그 둘을 합친다: 진행 중인 과제는 서버 순위·이유를, 완료한 과제는 /api/events 의 값을 쓴다.

import type { CalEvent, DeadlineProps } from "./types";
import { parseLocal } from "./dates";

export const ESTIMATE_OPTIONS = [0.5, 1, 2, 3, 5, 8] as const;

export type PriorityGroup = "overdue" | "now" | "week" | "later" | "nodue";
export type TaskKind = "assignment" | "quiz" | "video" | "project";

export const GROUP_META: Record<PriorityGroup, { label: string; tone: "danger" | "accent" | "neutral" }> = {
  overdue: { label: "놓친 마감", tone: "danger" },
  now: { label: "지금 해야 함", tone: "accent" },
  week: { label: "이번 주", tone: "neutral" },
  later: { label: "나중에", tone: "neutral" },
  nodue: { label: "마감 없음", tone: "neutral" },
};
export const GROUP_ORDER: PriorityGroup[] = ["overdue", "now", "week", "later", "nodue"];

/** GET /api/priority 의 items — F6 과제 원장 값 + F7 계산 결과(응답 전용, 요구사항정의서 F7 6절) */
export interface PriorityItem extends Omit<DeadlineProps, "kind" | "due"> {
  id: string;
  title: string;
  due: string | null;
  kind: TaskKind;
  kindLabel: string;
  estimatedHours: number;
  estimateSource: "default" | "user";
  remainingHours: number | null;
  neededHours: number;
  slackHours: number | null;
  group: PriorityGroup;
  groupLabel: string;
  reason: string;
  short: boolean; // 안전계수 없이도 남은 시간보다 오래 걸린다
  stale: boolean; // 2주 넘게 지난 놓친 마감 — 접어 둔다
  rank: number; // 그룹 안 순서 (1부터)
}

export interface PriorityGroupInfo {
  key: PriorityGroup;
  label: string;
  tone: "danger" | "accent" | "neutral";
  count: number;
  totalHours: number;
  staleCount: number;
  collapsed: boolean;
}

export interface PriorityTop {
  id: string;
  title: string;
  courseShort: string;
  courseColor: string;
  kindLabel: string;
  due: string | null;
  group: PriorityGroup;
  groupLabel: string;
  reason: string;
  estimatedHours: number;
  estimateSource: "default" | "user";
  url: string;
}

/** 오늘 남은 시간 = 취침 − 지금 − 수업·일정(겹침 한 번) − 오늘 학습 분량 (F7-R21) */
export interface TodayBudget {
  bedTime: string;
  bedAt: string;
  untilBedHours: number;
  busyHours: number;
  studyHours: number;
  leftHours: number;
  needHours: number;
  over: boolean;
  busy: { title: string; kind: string; start: string; end: string }[];
}

export interface PrioritySettings {
  safetyFactor: number;
  defaultHours: Record<TaskKind, number>;
  bedTime: string;
}

export interface PrioritySettingsPatch {
  safetyFactor?: number | null;
  defaultHours?: Partial<Record<TaskKind, number | null>> | null;
  bedTime?: string | null;
  reset?: boolean;
}

export interface PrioritySettingsView extends PrioritySettings {
  defaults: PrioritySettings;
  changed: string[];
  kinds: { key: TaskKind; label: string }[];
  limits: { safetyFactor: [number, number]; defaultHours: [number, number]; bedTime: [string, string] };
}

export interface PriorityOverview {
  items: PriorityItem[];
  groups: PriorityGroupInfo[];
  counts: Record<PriorityGroup | "open", number>;
  top: PriorityTop[];
  today: TodayBudget;
  settings: PrioritySettings;
  course: string | null;
  computedAt: string;
}

/** /api/status 의 priority 칸 — 기능 타일 숫자 */
export interface PriorityStatus {
  available: boolean;
  error?: string | null;
  now?: number;
  nowHours?: number;
  overdue?: number;
  week?: number;
  later?: number;
  nodue?: number;
  open?: number;
  top?: PriorityTop[];
  computedAt?: string;
}

/** 과제 목록 화면·대시보드가 쓰는 한 줄 */
export interface Assignment {
  id: string;
  title: string;
  p: DeadlineProps;
  due: Date | null; // 마감 없는 과제는 null (순위 밖, '마감 없음' 그룹)
  kindLabel: string;
  submitted: boolean; // e클래스 제출 완료
  userDone: boolean; // 내가 체크함 (e클래스 밖에서 제출)
  estimate: number | null; // 서버를 못 부르면 사용자가 고친 값만 (null = 기본값)
  estimateSource: "default" | "user";
  remainingHours: number | null;
  group: PriorityGroup | null; // 완료했거나 서버 순위를 아직 못 받았으면 null
  rank: number | null;
  reason: string | null;
  stale: boolean;
}

const KIND_LABEL: Record<string, string> = { 퀴즈: "퀴즈", 동영상: "동영상" };

/** 서버 순위(진행 중) + /api/events 의 과제(완료 포함)를 합친다. 순서는 정하지 않는다 — 화면이 탭·정렬에 맞춰 정한다. */
export function buildAssignments(events: CalEvent[], overview: PriorityOverview | null, now = new Date()): Assignment[] {
  const ranked = new Map((overview?.items ?? []).map((r) => [r.id, r]));
  const out: Assignment[] = [];
  const seen = new Set<string>();
  for (const ev of events) {
    if (ev.extendedProps.kind !== "deadline") continue;
    const p = ev.extendedProps;
    const done = p.submitted || !!p.userDone;
    // 화면이 먼저 바뀐 값(내가 체크함)이 서버 순위보다 앞선다 — 체크하자마자 목록에서 빠져야 한다
    const r = done ? undefined : ranked.get(ev.id);
    const due = parseLocal(p.due);
    seen.add(ev.id);
    out.push({
      id: ev.id,
      title: ev.title,
      p,
      due,
      kindLabel: r?.kindLabel ?? KIND_LABEL[p.type] ?? "과제",
      submitted: p.submitted,
      userDone: !p.submitted && !!p.userDone,
      // 소요시간은 화면 값(방금 고친 값)을 먼저 — 서버 재계산이 오기 전에도 고른 값이 보인다
      estimate: p.estimateHours ?? r?.estimatedHours ?? null,
      estimateSource: p.estimateHours !== null && p.estimateHours !== undefined ? "user" : "default",
      remainingHours: r?.remainingHours ?? (due.getTime() - now.getTime()) / 3_600_000,
      group: r?.group ?? null,
      rank: r?.rank ?? null,
      reason: r?.reason ?? null,
      stale: !!r?.stale,
    });
  }
  // 마감 없는 과제는 캘린더(/api/events)에 없다 — 서버 목록에서만 온다
  for (const r of overview?.items ?? []) {
    if (seen.has(r.id)) continue;
    out.push({
      id: r.id,
      title: r.title,
      p: { ...r, kind: "deadline", due: r.due ?? "" } as DeadlineProps,
      due: r.due ? parseLocal(r.due) : null,
      kindLabel: r.kindLabel,
      submitted: r.submitted,
      userDone: r.userDone,
      estimate: r.estimatedHours,
      estimateSource: r.estimateSource,
      remainingHours: r.remainingHours,
      group: r.group,
      rank: r.rank,
      reason: r.reason,
      stale: r.stale,
    });
  }
  return out;
}

export const isOpen = (a: Assignment) => !a.submitted && !a.userDone;
export const isOverdue = (a: Assignment, now = new Date()) => isOpen(a) && !!a.due && a.due.getTime() < now.getTime();

/** 급한 순 — 서버가 정한 그룹·그룹 안 순서 그대로. 순위를 아직 못 받은 것은 마감 순으로 뒤에. */
export function sortByPriority(list: Assignment[]): Assignment[] {
  const g = (a: Assignment) => (a.group ? GROUP_ORDER.indexOf(a.group) : GROUP_ORDER.length);
  return [...list].sort(
    (a, b) => g(a) - g(b) || (a.rank ?? 0) - (b.rank ?? 0) || (a.due?.getTime() ?? Infinity) - (b.due?.getTime() ?? Infinity),
  );
}
