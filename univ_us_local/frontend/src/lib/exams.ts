// F5 시험 공부 일정 — /api/exams · /api/study-plans 가 주는 모양
// (F5_Test_agent/exams/service.py 의 exam_view · plan_view · day_view, plan.py 의 compute 와 1:1).
//
// 계산은 전부 백엔드에서 한다. 이 파일에는 **화면이 그대로 그릴 값**만 오고, 여기서 다시 계산하지 않는다
// (요구사항정의서 F5-R26 · Frontend-Route 10-7). 미리보기와 등록이 나뉜 이유도 같다 —
// `preview` 는 저장하지 않는 계산 결과이고, `createPlan` 만 캘린더를 바꾼다.

import type { Tone } from "@/components/ui/Chip";

export type ExamType = "midterm" | "final" | "quiz" | "presentation" | "etc";
export type Difficulty = "easy" | "normal" | "hard";
export type PlanState = "draft" | "active" | "done" | "canceled";
/** ok 정상 · over 하루 상한 초과 · overlap 다른 과목과 겹침 · no_time 시험이 오늘·내일 */
export type Verdict = "ok" | "over" | "overlap" | "no_time";
export type DayKind = "study" | "review" | "excluded";

export interface Evidence {
  quote: string;
  url: string;
}

/** 범위 → 분량 (F4 자료 쪽수 합계, F5-R10). available=false 면 사용자가 직접 넣는다(F5-R11) */
export interface ScopeMeasure {
  available: boolean;
  error: string | null;
  pages: number;
  files: number;
  counted: number;
  noPages: number; // 쪽수를 세지 못한 자료 수 — 합계에서 빠졌다
  noPagesTitles: string[];
  materials: { id: string; title: string; week: number | null; pages: number | null; kind: string; ext: string }[];
  weeks: number[];
  note: string;
}

export interface Exam {
  id: string; // ex:<과목>:<해시8>
  courseId: string;
  courseName: string;
  course: string; // 짧은 이름
  courseCode: string;
  section: string;
  color: string;
  type: ExamType;
  typeLabel: string;
  title: string;
  date: string; // YYYY-MM-DD
  weekday: string;
  time: string; // HH:MM · 빈 값이면 '시각 미정'
  endTime: string;
  timeUnknown: boolean;
  /** 공지에 시각이 없어 그 과목 수업 시간으로 채웠다 (2026-10-01) */
  timeFromClass?: boolean;
  /** 날짜가 확정됐나 — 임의 일정·확인 필요는 아니다(전체 캘린더에 안 들어간다) */
  confirmed?: boolean;
  place: string;
  dday: number;
  ddayLabel: string;
  past: boolean;
  soon: boolean; // 7일 이내
  scope: {
    weeks: number[];
    materialIds: string[];
    note: string; // 공지·사용자가 말한 범위 문구
    specified: boolean;
    pages?: number; // 범위 안 F4 자료 쪽수
    files?: number;
    noPages?: number;
    autoNote?: string; // '자료 7개 291쪽 (쪽수를 세지 못한 1개는 빠졌습니다)'
  };
  pages?: number;
  source: "notice" | "manual" | "auto";
  sourceLabel: string;
  /** 임의 일정 — 학사일정 수업평가 기간 안에서 그 과목의 수업 요일로 잡아 둔 자리. 공지가 나오면 바뀌고, 직접 고칠 수 있다 */
  isAuto: boolean;
  /** 임의 일정이면 어떻게 잡았는지 */
  note: string;
  status: "confirmed" | "review";
  statusLabel: string;
  needsReview: boolean;
  confidence: number;
  evidence: Evidence[];
  noticeUrl: string;
  postedAt: string;
  edited: boolean;
  /** 공지에서 날짜가 바뀌었다 — kind=confirmed 면 임의 일정 자리에 진짜 일정이 처음 나온 것(연기가 아니다) */
  changed: { field: string; from: string; to: string; at: string; kind?: "confirmed" } | null;
  canDelete: boolean;
  addedAt: string;
  plan: StudyPlan | null;
  planState: PlanState | "none";
  /** 수정 뒤에만 — 등록된 계획이 지금 시험·자료와 어긋난다 */
  planStale?: { reasons: string[]; message: string } | null;
}

export interface PlanDay {
  date: string;
  weekday: string;
  pages: number;
  minutes: number;
  kind: DayKind;
  quiz: number;
  done: boolean;
  moved: boolean;
  kindLabel?: string; // 등록된 계획에만
  doneAt?: string | null;
  blockId?: string; // st:<계획>:<날짜>
}

export interface PlanProgress {
  plannedPages: number;
  donePages: number;
  behindPages: number;
  totalUnits: number | null;
  percent: number;
  doneDays: number;
  totalDays: number;
  behindDays: number;
  behindDates: string[];
  remainingDays: number;
  remainingPages: number;
  todayPages: number;
  todayMinutes: number;
}

/** 등록된 계획 (F5 6절 StudyPlan) */
export interface StudyPlan {
  id: string; // pl:<n>
  planId: number;
  examId: string;
  examDate: string;
  examDday: number;
  state: PlanState;
  stateLabel: string;
  unit: "pages" | "minutes";
  totalPages: number | null;
  totalMinutes: number | null;
  pageMinutes: number;
  difficulty: Difficulty;
  difficultyLabel: string;
  reviewDays: number;
  excludedDates: string[];
  capMinutes: number;
  includeQuiz: boolean;
  quizCount: number;
  scopeWeeks: number[];
  scopeMaterialIds: string[];
  sourcePages: number | null;
  days: PlanDay[];
  progress: PlanProgress;
  behind: boolean;
  behindMessage: string;
  createdAt: string;
  rebalancedAt: string | null;
  closedAt: string | null;
}

/** 계획을 만들 때 사용자가 고르는 값 — 조정안의 `apply` 도 이 모양이다 */
export interface PlanOptionsInput {
  unit?: "pages" | "minutes";
  totalPages?: number;
  totalMinutes?: number;
  pageMinutes?: number;
  difficulty?: Difficulty;
  reviewDays?: number;
  excludedDates?: string[];
  capMinutes?: number;
  includeQuiz?: boolean;
  quizCount?: number;
  startDate?: string;
  scopeWeeks?: number[];
  scopeMaterialIds?: string[];
  /** 며칠 공부할지 — 마무리 복습 바로 앞 N일 (null = 남은 날 전부). 날짜를 직접 고르면 무시된다 */
  studyDays?: number | null;
  /** 공부할 날짜 — 사용자가 달력에서 고른 날 (비우면 studyDays 로 자동) */
  studyDates?: string[];
}

/** 시험 추가·수정 본문 (POST·PATCH /api/exams) */
export interface ExamInput {
  courseId: string;
  type: ExamType;
  date: string;
  time?: string;
  endTime?: string;
  place?: string;
  title?: string;
  scopeWeeks?: number[];
  scopeMaterialIds?: string[];
  scopeNote?: string;
}

export interface PlanWarning {
  level: "error" | "warn" | "info";
  code: string;
  message: string;
}

export interface PlanAdjustment {
  key: "start_earlier" | "drop_excluded" | "less_review" | "less_scope" | "more_review" | "less_quiz" | "raise_cap";
  label: string;
  detail: string;
  apply: PlanOptionsInput;
}

/** 미리보기 (POST /api/study-plans/preview) — **저장하지 않는다** */
export interface PlanPreview extends Required<Omit<PlanOptionsInput, "startDate" | "studyDays" | "studyDates">> {
  /** 실제로 나눈 학습일 수 */
  studyDays: number;
  /** 실제로 나눈 학습 날짜 */
  studyDates: string[];
  /** 사용자가 달력에서 날짜를 골랐나 */
  studyDatesPicked: boolean;
  /** 학습일로 쓸 수 있는 날 수 — 학습일 수 입력의 최댓값 */
  studyPool: number;
  /** 달력에서 고를 수 있는 날 (오늘 ~ 시험 전날, 이미 완료한 날 제외) */
  selectableDates: string[];
  examId: string;
  courseId: string;
  courseName: string;
  examDate: string;
  examTime: string;
  examType: ExamType;
  examTypeLabel: string;
  state: "draft";
  startDate: string;
  availableDays: number;
  reviewDayDates: string[];
  dailyPages: number;
  dailyMinutes: number;
  days: PlanDay[];
  totals: { pages: number; minutes: number; quiz: number; blocks: number };
  carried: { pages: number; minutes: number; days: number };
  peakMinutes: number;
  peakDate: string | null;
  verdict: Verdict;
  verdictLabel: string;
  warnings: PlanWarning[];
  overlap: { date: string; minutes: number; mine: number; others: number; cap: number; courses: string[] }[];
  adjustments: PlanAdjustment[];
  canRegister: boolean;
  needsConfirm: boolean;
  scope: ScopeMeasure;
  exam: Exam;
  otherLoad: { date: string; minutes: number; pages: number; courses: string[] }[];
  /** 재조정으로 부른 결과일 때만 */
  rebalanceOf?: { planId: number; id: string; progress: PlanProgress; behindMessage: string };
  note?: string;
}

/** 오늘 공부 (F5-R36 · S09) — /api/exams/today, /api/status 의 exams 칸도 같은 값을 쓴다 */
export interface TodayBlock {
  date: string;
  blocks: {
    planId: number;
    examId: string;
    course: string;
    color: string;
    pages: number;
    minutes: number;
    quiz: number;
    kind: DayKind;
    kindLabel: string;
    done: boolean;
    examDate: string;
    dday: number;
    text: string;
  }[];
  totalPages: number;
  totalMinutes: number;
  remainingMinutes: number;
  text: string;
  nextExam: NextExam | null;
}

export interface NextExam {
  examId: string;
  course: string;
  type: ExamType;
  typeLabel: string;
  date: string;
  time: string;
  place: string;
  dday: number;
  ddayLabel: string;
}

/** 과목별 시험 유무 (2026-10-01) — 모든 과목은 중간·기말을 본다고 두고, 안 보는 과목은 끈다 */
export interface CourseExamSetting {
  courseId: string;
  course: string;
  courseName: string;
  color: string;
  midterm: boolean;
  final: boolean;
  midtermExam: CourseExamRef | null;
  finalExam: CourseExamRef | null;
}

export interface CourseExamRef {
  id: string;
  date: string;
  time: string;
  source: "notice" | "manual" | "auto";
  sourceLabel: string;
  past: boolean;
}

/** 임의 일정을 잡는 학사일정 기간 */
export interface ExamPeriods {
  available: boolean;
  semester: string;
  start: string | null;
  end: string | null;
  midterm: PeriodPart;
  final: PeriodPart;
}

export interface PeriodPart {
  evaluation: [string, string] | null;
  exam: [string, string] | null;
  window: [string, string] | null;
  label: string;
}

export interface ExamsOverview {
  semester: { id: string; label: string; start: string; end: string };
  semesters: string[];
  exams: Exam[]; // 다가오는 시험
  past: Exam[];
  review: Exam[]; // 확인 필요 (공지에서 찾았지만 신뢰도가 낮다)
  counts: { total: number; upcoming: number; past: number; review: number; planned: number; behind: number };
  today: TodayBlock;
  source: {
    eclass: { available: boolean; manifest: string; stamp: string | null; syncedAt: string | null; note: string };
    materials: { available: boolean; error: string | null; note: string };
  };
  types: { key: ExamType; label: string; reviewDays: number }[];
  /** 난이도별 쪽당 시간 — 사용자가 '난이도 시간 설정'에서 바꾼 값 (defaultMinutes = 기본 1·2·3분) */
  difficulties: { key: Difficulty; label: string; pageMinutes: number; defaultMinutes?: number }[];
  capChoices: number[];
  /** 2026-10-01 에 생긴 칸 — 그 전의 백엔드가 떠 있으면 없다(화면은 디스크의 새 빌드를 쓰므로 둘이 어긋날 수 있다) */
  courseSettings?: CourseExamSetting[];
  defaults?: {
    periods: ExamPeriods;
    hints: string[];
    auto: number; // 다가오는 임의 일정 수
    created: { examId: string; course: string; type: ExamType; label: string; date: string; time: string }[];
    moved: { examId: string; course: string; type: ExamType; label: string; from: string; to: string }[];
  };
  updatedAt: string | null;
  sync?: SyncNotices;
}

/** 시험 하나 — 계획 옵션 기본값과 범위 후보까지 (F5-S04) */
export interface ExamDetail extends Exam {
  options: PlanOptionsInput;
  scopeChoices: { weeks: number[]; materials: ScopeMeasure["materials"] };
  plans: StudyPlan[]; // 지난 계획 (취소·완료)
}

export interface SyncNotices {
  available: boolean;
  stamp: string | null;
  posts: number;
  new: number;
  updated: number;
  postponed: { examId: string; courseId: string; course: string; type: ExamType; typeLabel: string; from: string; to: string }[];
  /** 임의 일정 자리에 공지의 진짜 일정이 들어왔다 */
  confirmed?: { examId: string; course: string; type: ExamType; typeLabel: string; from: string; to: string; time: string; planned: boolean }[];
  hints: { courseId: string; course: string; noticeTitle: string; noticeUrl: string; postedAt: string; why: string }[];
  reviewCount?: number;
  syncedAt?: string;
  error?: string;
  exams?: Exam[];
  updatedAt?: string | null;
}

/** 학습 블록 하나 + 그날 볼 자료 (F5-S08 · 캘린더 팝업) */
export interface DayDetail extends PlanDay {
  planId: number;
  examId: string;
  exam: Exam;
  materials: ScopeMeasure["materials"];
  materialsNote: string;
  pageMinutes: number;
}

/** /api/status 의 exams 칸 (기능 타일) */
export interface ExamsStatus {
  available: boolean;
  error?: string;
  updatedAt?: string | null;
  exams?: number;
  upcoming?: number;
  review?: number;
  activePlans?: number;
  behind?: number;
  todayPages?: number;
  todayMinutes?: number;
  todayText?: string;
  nextExam?: NextExam | null;
  eclassAvailable?: boolean;
  materialsAvailable?: boolean;
  noticeSyncedAt?: string | null;
  auto?: number;
}

/* ---------------------------------------------------------------- 화면이 쓰는 작은 것들 */

/** 판정 색 — 색만으로 구분하지 않는다(문구는 서버가 verdictLabel·warnings 로 준다) */
export const VERDICT_TONE: Record<Verdict, "danger" | "warn" | "neutral"> = {
  ok: "neutral",
  over: "danger",
  overlap: "warn",
  no_time: "danger",
};

export const TYPE_TONE: Record<ExamType, Tone> = {
  midterm: "danger",
  final: "danger",
  quiz: "accent",
  presentation: "info",
  etc: "neutral",
};

/** 분 → '38분' · '1시간 49분' (서버의 _hm 과 같은 규칙) */
export function hm(minutes: number): string {
  const m = Math.round(minutes);
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (h && r) return `${h}시간 ${r}분`;
  return h ? `${h}시간` : `${r}분`;
}

/** 하루치 한 줄 — '15쪽 · 38분' · '전체 복습 + 문제 10개' */
export function dayText(d: PlanDay): string {
  if (d.kind === "excluded") return "제외일";
  const head = d.kind === "review" ? "전체 복습" : `${d.pages}쪽`;
  return `${head}${d.quiz ? ` + 문제 ${d.quiz}개` : ""}`;
}

/** 범위 한 줄 — '3·4·5주차' · 공지 문구 · '미지정' */
export function scopeText(e: Pick<Exam, "scope">): string {
  if (e.scope.weeks.length) return `${e.scope.weeks.join("·")}주차`;
  if (e.scope.materialIds.length) return `자료 ${e.scope.materialIds.length}개`;
  return e.scope.note || "미지정";
}

/** '자료 291쪽' · '쪽수 미확인' — 자동으로 채워진 분량 */
export function pagesText(e: Pick<Exam, "scope">): string {
  const p = e.scope.pages;
  if (p === undefined) return "자료 —";
  return p ? `자료 ${p}쪽` : "쪽수 직접 입력";
}
