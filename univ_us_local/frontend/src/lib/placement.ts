// F8 공강 학습 플랜 — 계산은 전부 서버(F8_Plan_agent, POST /api/placement/preview)가 한다. 화면은 그 값을 그대로 그린다.
//   공강 = 낮 시간대(기본 09:00~18:00) − 수업(±여유) − 일정 − 점심, 30분 미만은 버림. 저녁 19~24시는 F5 시험 공부 계획 몫
//   ① 과제(F7 순서 그대로) · 할 일(C1, 30분)을 이른 공강부터  ② 남는 공강은 공부 블록 —
//      과목 점수 = 남은 진도율 ÷ 시험까지 남은 날수 (같은 날 같은 과목은 감점). 블록 30분~2시간 · 같은 작업 하루 2블록
//   하루 상한은 없다(2026-10-06) — 하루 합계는 보여 주기만 한다.
// 미리보기는 저장하지 않는다. 캘린더를 바꾸는 것은 '배치하기'(POST /api/placement) 뿐이다.

export type SlotSource = "gap";
/** exam = 2026-10-06 판의 F5 하루치 배치 (옛 블록만) */
export type TaskType = "assignment" | "todo" | "study" | "exam";

export const TASK_LABEL: Record<TaskType, string> = { assignment: "과제", todo: "할 일", study: "공부", exam: "시험 공부" };

/** 미리보기의 새 블록 (아직 저장 전) — key 로 개별 제외한다 */
export interface PlannedBlock {
  key: string;
  taskType: TaskType;
  refId: string;
  title: string;
  course: string;
  color: string;
  date: string; // YYYY-MM-DD
  start: string; // HH:MM
  end: string; // HH:MM (24:00 까지)
  minutes: number;
  slot: SlotSource;
  slotMinutes: number;
  reason: string; // '남은 진도 85% · 시험 D-12 · 공강 60분'
  href: string | null;
  part?: string; // '1/2'
  percent?: number | null; // 공부 블록 — 그 과목 진도율
  examDate?: string; // 공부 블록 — 시험 날짜
}

/** 공부 블록 과목 고르는 순서 — 오늘 기준 점수(남은 진도율 ÷ 남은 날수) */
export interface StudyTarget {
  examId: string;
  title: string;
  course: string;
  color: string;
  date: string;
  dday: number;
  percent: number;
  isAuto: boolean;
  href: string;
  score: number;
}

/** 등록된 블록 (캘린더 kind=study 의 extendedProps 와 같은 칸) */
export interface SavedBlock {
  id: string; // pb:<n>
  blockId: number;
  taskType: TaskType;
  refId: string;
  title: string;
  course: string;
  color: string;
  date: string;
  start: string;
  end: string;
  minutes: number;
  reason: string;
  slot: string;
  href: string | null;
  placedBy: "auto" | "user";
  auto: boolean;
  done: boolean;
}

export interface Unplaced {
  refId: string;
  taskType: TaskType;
  title: string;
  course: string;
  remainingMinutes: number;
  totalMinutes: number;
  reasonKey: "noSlot" | "short" | "overdue" | "sameTask" | "excluded";
  reason: string;
  href: string | null;
  text: string;
}

export interface Adjustment {
  key: "day" | "weekend" | "lunch";
  label: string;
  text: string;
  patch: Partial<AvailabilitySettings>;
}

export interface PreviewDay {
  date: string;
  weekday: string;
  weekend: boolean;
  classes: { start: string; end: string; title: string; canceled: boolean }[];
  events: { start: string; end: string; title: string; kind: string }[];
  slots: { start: string; end: string; minutes: number; source: SlotSource }[];
}

export interface PlacementPreview {
  range: { start: string; end: string; days: number };
  days: PreviewDay[];
  blocks: PlannedBlock[];
  kept: SavedBlock[];
  unplaced: Unplaced[];
  deferred: { refId: string; title: string; course: string; remainingMinutes: number; due: string; text: string }[];
  dailyTotals: { date: string; minutes: number; newMinutes: number; studyMinutes: number; keptMinutes: number }[];
  totalMinutes: number;
  studyMinutes: number;
  studyTargets: StudyTarget[];
  adjustments: Adjustment[];
  existing: number; // 다시 계산되면 바뀌는 자동 배치 블록 수
  /** tasks = 과제·할 일 수 · study = 공부 블록을 만들 수 있는 시험 수 */
  state: { timetable: boolean; tasks: number; study: number; fillStudy: boolean; allUnplaced: boolean };
  settings: AvailabilitySettings;
  exclude: string[];
  signature: string;
  at: string;
}

export interface RegisterResult {
  created: number;
  studyCreated: number; // 그중 공부 블록 — 공부 캘린더에만 들어간다(전체 캘린더와 따로, F5 D7)
  removed: number;
  batch: string;
  range: { start: string; end: string; days: number };
  unplaced: number;
  totalMinutes: number;
}

/** /api/events 의 F8 블록 (C1 kind=study) — id 는 'pb:<n>'. **과제·할 일 블록만** 온다 — 공부 블록은 공부 캘린더에만 */
export interface StudyProps extends Omit<SavedBlock, "id" | "title" | "date" | "start" | "end"> {
  kind: "study";
  conflict: string | null; // 겹침 · 끝낸 작업 · 마감 뒤 (F8-S08)
}

export interface AvailabilitySettings {
  dayStart: string; // 기본 09:00
  dayEnd: string; // 기본 18:00 — 19:00 까지 (저녁은 F5 몫)
  lunchBreak: boolean;
  lunchStart: string;
  lunchEnd: string;
  bufferMinutes: number;
  minSlotMinutes: number;
  maxBlockMinutes: number;
  useWeekend: boolean;
  rangeDays: number;
  fillStudy: boolean; // 남는 공강에 공부 블록
}

export interface AvailabilityView extends AvailabilitySettings {
  defaults: AvailabilitySettings;
  changed: (keyof AvailabilitySettings)[];
  choices: { bufferMinutes: number[]; rangeDays: number[]; minSlotMinutes: [number, number]; maxBlockMinutes: [number, number]; dayEarliest: string; dayLatest: string };
}

/** /api/status 의 placement 칸 */
export interface PlacementStatus {
  available: boolean;
  error?: string;
  updatedAt?: string | null;
  upcoming?: number;
  auto?: number;
  fixed?: number;
  todayCount?: number;
  todayMinutes?: number;
  todayText?: string;
}

export function hm(m: number): string {
  const h = Math.floor(m / 60);
  const r = Math.round(m % 60);
  return h && r ? `${h}시간 ${r}분` : h ? `${h}시간` : `${r}분`;
}

export const toMin = (t: string) => Number(t.slice(0, 2)) * 60 + Number(t.slice(3, 5));
