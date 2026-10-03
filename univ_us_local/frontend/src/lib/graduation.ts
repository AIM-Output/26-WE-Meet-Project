// F2 졸업요건 — GET /api/graduation/status 가 주는 모양 (F2_Graduation_agent/graduation/calc.py · service.py 와 짝).
// 요구사항정의서 F2 6절 `GraduationStatus`. 계산은 백엔드 규칙 코드 한 곳에서만 한다 — 이 파일에 계산 규칙을 두지 않는다.

import type { Gpa, JobState, Track } from "./profile";

export type Verdict = "충족" | "부족" | "확인 필요";
export type RulesetLevel = "user" | "exact" | "dept" | "nearest" | "track" | "none";
export type CertState = "done" | "todo" | "unknown";

export interface CourseBrief {
  id: string;
  name: string;
  code: string | null;
  credits: number;
  grade: string | null;
  year: number | null;
  semester: string | null;
  source: "hakstd" | "manual";
}

export interface RequiredCourse {
  code: string | null;
  name: string;
  credits: number;
  grade?: number | null; // 권장 학년
  term?: string | null;
  done?: boolean;
}

export interface GradArea {
  key: string;
  label: string;
  required: number;
  own: number; // 이 영역으로 분류된 학점
  earned: number; // 초과 이월까지 반영한 학점
  outflow: number;
  inflow: number;
  overflowTo: string | null;
  short: number;
  courses: CourseBrief[];
  requiredCourses: RequiredCourse[];
  missingCourses: RequiredCourse[];
  coursesSource: "curriculum" | "ruleset" | null;
  listUnknown: boolean; // 교육과정을 아직 받지 않아 과목 목록을 모름
  ok: boolean;
  evidence: string;
}

export interface GradCheck {
  key: string;
  label: string;
  required: number;
  earned: number;
  short: number;
  state: "ok" | "short" | "unknown";
  approximate: boolean;
  courses: CourseBrief[];
  evidence: string;
  common: string | null;
}

export interface GradCert {
  key: string;
  label: string;
  detail: string;
  required: boolean;
  state: CertState;
  memo: string;
  updatedAt: string | null;
  evidence: string;
  hintFound: string[]; // 이수 과목에서 찾은 관련 과목 (예: 생활영어1) — 체크는 사용자가
}

export interface GradCourseRow {
  id: string;
  year: number | null;
  semester: string | null; // 1 · 2 · 여름 · 겨울
  code: string | null;
  name: string;
  credits: number;
  grade: string | null;
  rawCategory: string | null; // 학사시스템 교과구분 원문
  geArea: string | null; // 교양영역
  status: string | null;
  retake: string | null;
  source: "hakstd" | "manual";
  memo: string | null;
  area: string | null; // null = 미분류
  areaSetBy: "user" | "map" | "none";
  excluded: boolean;
  excludedReason: string | null;
  excludedByUser: boolean;
  areaOverride: string | null;
}

export interface RulesetSource {
  docName?: string;
  url?: string;
  related?: { docName: string; url: string }[];
  checkedAt?: string | null;
}

export interface RulesetMeta {
  id: string | null;
  label: string; // '2021~2022 입학 · 인공지능학부 기준'
  level: RulesetLevel;
  levelLabel: string;
  warnings: string[];
  edited: boolean;
  baseChanged: boolean;
  verified: boolean;
  track: Track;
  trackLabel: string;
  totalCredits: number | null;
  areas: { key: string; label: string }[];
  notes: string[];
  source: RulesetSource | null;
  commonSources: (RulesetSource & { id: string })[];
  curriculum: { sources: { code: string; year: number; origin: string; url?: string }[]; missing: string[]; year: number | null } | null;
  totalEvidence: string;
  minGpaEvidence: string;
}

export interface GraduationStatus {
  verdict: Verdict;
  reasons: { doubts: string[]; shorts: string[]; unknowns: string[] };
  total: { required: number | null; earned: number; short: number | null; remaining: number | null; areaShort: number };
  gpa: { required: { value: number; scale: number } | null; current: Gpa | null; ok: boolean | null; note: string };
  areas: GradArea[];
  checks: GradCheck[];
  certifications: GradCert[];
  unmapped: CourseBrief[];
  courses: GradCourseRow[];
  headline: string;
  computedAt: string;
  ruleset: RulesetMeta;
  profile: { department: string | null; major: string | null; admissionYear: number | null; track: Track | null; deptCode: string | null; majorCode: string | null };
  profileMissing: string[];
  data: { importedAt: string | null; hakstdCount: number; manualCount: number; count: number };
  updatedAt: string | null;
}

/** /api/status 의 graduation 칸 — 기능 타일 */
export interface GraduationSummary {
  available: boolean;
  error?: string;
  updatedAt?: string | null;
  verdict?: Verdict;
  remaining?: number | null;
  earned?: number;
  required?: number | null;
  headline?: string;
  level?: RulesetLevel;
  hasData?: boolean;
  unmapped?: number;
  profileMissing?: string[];
  importedAt?: string | null;
  import?: GradImportState;
}

export interface GradImportState extends JobState {
  result: { count: number; added: number; removed: number; importedAt: string; profile: { changed?: string[]; skipped?: string[] } | null } | null;
}

export interface CurriculumState {
  codes: string[];
  year: number | null;
  have: string[];
  missing: string[];
  collegeCode: string | null;
  sync: JobState & { result: { year: number; codes: { code: string; count: number }[]; empty: string[] } | null };
}

export interface CourseInput {
  name: string;
  credits: number;
  year?: number | null;
  semester?: string | null;
  grade?: string | null;
  code?: string | null;
  area?: string | null;
  memo?: string;
}

export interface CoursePatch extends Partial<CourseInput> {
  applyToCategory?: boolean;
  excluded?: boolean;
}

export interface Assumptions {
  areas: Record<string, number>;
  courses: string[];
}

export interface SimSide {
  verdict: Verdict;
  total: GraduationStatus["total"];
  headline: string;
  areas: { key: string; label: string; required: number; earned: number; short: number; ok: boolean; missing: string[] }[];
}

export interface Plan {
  id: string;
  name: string;
  track: Track;
  assumptions: Assumptions;
  createdAt: string;
}

/* ---------------------------------------------------------------- 룰셋 (/settings/requirements) */

export interface RulesetArea {
  key: string;
  label: string;
  minCredits: number;
  overflowTo?: string;
  coursesFrom?: string; // 교과구분 — 교육과정검색에서 과목 목록을 채운다
  courses?: RequiredCourse[];
  coursesSource?: "curriculum" | "ruleset";
  evidence: string;
}

export interface RulesetCert {
  key: string;
  label: string;
  detail: string;
  required: boolean;
  evidence: string;
  hintCourses?: string[];
}

export interface RulesetDoc {
  id: string | null;
  university?: string;
  college?: string | null;
  deptCode?: string | null;
  department?: string | null;
  majorCode?: string | null;
  major?: string | null;
  admissionYear?: number | null;
  admissionYearTo?: number | null;
  track?: Track;
  totalCredits: number | null;
  totalEvidence: string;
  minGpa: { value: number; scale: number } | null;
  minGpaEvidence: string;
  areas: RulesetArea[];
  checks: { key: string; label: string; minCredits: number; match: string[]; evidence: string; common?: string; approximate?: boolean }[];
  certifications: RulesetCert[];
  categoryMap: Record<string, string>;
  notes: string[];
  source: RulesetSource | null;
  version?: number;
  verified?: boolean;
  curriculum?: RulesetMeta["curriculum"];
  commonSources?: RulesetMeta["commonSources"];
}

export interface RulesetListItem {
  id: string;
  department: string | null;
  major: string | null;
  admissionYear: number;
  admissionYearTo: number | null;
  track: Track;
  totalCredits: number | null;
  label: string;
}

export interface RulesetView {
  target: { deptCode: string | null; majorCode: string | null; admissionYear: number | null; track: Track; label: string };
  level: RulesetLevel;
  levelLabel: string;
  warnings: string[];
  edited: boolean;
  editedAt: string | null;
  base: { id: string; version: number; label: string } | null;
  baseChanged: boolean;
  ruleset: RulesetDoc | null; // 펼친 것(과목 목록·공통 조건 포함) — 보기용
  editable: RulesetDoc; // 편집용 원본 (없으면 빈 템플릿)
  isTemplate: boolean;
  similar: RulesetListItem[];
  categoryMapMine: Record<string, string>;
  label: string;
}

export interface CategoryView {
  rows: { raw: string; base: string | null; mine: string | null; area: string | null; courses: number }[];
  areas: { key: string; label: string }[];
}

/* ---------------------------------------------------------------- 표시 도우미 */

export const VERDICT_TONE: Record<Verdict, "ok" | "accent" | "warn"> = { 충족: "ok", 부족: "accent", "확인 필요": "warn" };

export const LEVEL_TONE: Record<RulesetLevel, "ok" | "primary" | "warn" | "neutral"> = {
  user: "primary",
  exact: "ok",
  dept: "ok",
  nearest: "warn",
  track: "warn",
  none: "neutral",
};

export const CERT_LABEL: Record<CertState, string> = { done: "충족", todo: "미충족", unknown: "모름" };

/** 3 → '3', 2.5 → '2.5' */
export const num = (n: number | null | undefined) => (n === null || n === undefined ? "—" : Number.isInteger(n) ? String(n) : n.toFixed(1));

/** '2024-1' · '2024-여름' 을 학기 순서대로 */
const SEM_ORDER: Record<string, number> = { "1": 1, 여름: 2, "2": 3, 겨울: 4 };
export const termKey = (c: { year: number | null; semester: string | null }) => `${c.year ?? 0}-${c.semester ?? ""}`;
export const termSort = (a: string, b: string) => {
  const [ya, sa] = a.split("-");
  const [yb, sb] = b.split("-");
  return Number(ya) - Number(yb) || (SEM_ORDER[sa] ?? 9) - (SEM_ORDER[sb] ?? 9);
};
export const termLabel = (k: string) => {
  const [y, s] = k.split("-");
  if (y === "0") return "학기 미상";
  return s === "여름" || s === "겨울" ? `${y}년 ${s}계절` : `${y}년 ${s}학기`;
};

export const SEMESTER_OPTIONS = [
  { value: "1", label: "1학기" },
  { value: "여름", label: "여름 계절" },
  { value: "2", label: "2학기" },
  { value: "겨울", label: "겨울 계절" },
];
