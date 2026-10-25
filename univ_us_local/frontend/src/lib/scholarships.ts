// F11 장학 — /api/scholarships* 응답 모양 (F11_Scholarship_agent/scholarship/service.py · api.py 와 짝).
// 판정(시스템이 계산)과 진행 상태(사용자가 움직임)는 서로 다른 축이다 (요구사항정의서 F11 5절).

import type { Tone } from "@/components/ui/Chip";

export type SchVerdict = "eligible" | "needs_review" | "ineligible" | "expired" | "not_applicable";
export type SchProgress = "draft" | "approved" | "applied" | "selected" | "not_selected" | "skipped";
export type SensitiveKey = "incomeBracket" | "residenceRegion" | "highSchoolRegion" | "flags";

export const VERDICT_TONE: Record<SchVerdict, Tone> = {
  eligible: "ok",
  needs_review: "warn",
  ineligible: "neutral",
  expired: "neutral",
  not_applicable: "neutral",
};

export const PROGRESS_TONE: Record<SchProgress, Tone> = {
  draft: "info",
  approved: "primary",
  applied: "accent",
  selected: "ok",
  not_selected: "danger",
  skipped: "neutral",
};

export interface Period {
  start: string | null;
  end: string | null;
  raw: string | null;
}

export interface SchItem {
  id: string;
  title: string;
  rawTitle: string;
  kind: "notice" | "catalog";
  url: string;
  postedAt: string | null;
  firstSeen: string;
  source: string;
  sourceName: string;
  writer: string | null;
  org: string | null;
  unit: { key: string; org: string } | null;
  scholarshipKind: string | null; // 교내 · 교외 · 국가 · 사업단
  amount: string | null;
  verdict: SchVerdict;
  systemVerdict: SchVerdict;
  label: string;
  flipped: boolean; // 내가 바꿈
  hint: string | null; // 확인 필요의 이유 — 정보 입력 필요 · 조건 충족 추정 · 원문 확인
  sensitive: SensitiveKey[];
  failCount: number;
  deadline: string | null;
  daysLeft: number | null;
  period: Period | null;
  progress: SchProgress | null;
  progressLabel: string | null;
  hasDraft: boolean;
  draftStale: boolean; // 초안을 만든 뒤 원문이 바뀌었다
  onCalendar: boolean;
  askApplied: boolean; // 승인했는데 마감이 지났다 → '신청하셨나요?'
  isNew: boolean;
  needsOcr: boolean;
  ocr: boolean; // 이미지 속 글자를 OCR 로 읽었다 — 자동 판정 대신 확인 필요
  attachmentsUnread: number;
  confidence: number;
}

export interface Reason {
  field: string;
  label: string;
  status: "pass" | "fail" | "unknown";
  message: string;
  need: string | null;
  mine: string | null;
  evidence: string | null;
  sensitive: SensitiveKey | null;
  sure: boolean;
}

export interface SchDetail extends SchItem {
  reasons: Reason[];
  warning: string | null;
  documents: string[];
  applyMethod: string | null;
  applyUrl: string | null;
  contact: string | null;
  selectionCount: string | null;
  notes: string[];
  otherConditions: string[];
  body: string;
  bodyTruncated: boolean;
  attachments: { name: string; url: string; ext: string; read: boolean; ocr?: boolean }[];
  ocrText: string | null; // 이미지에서 OCR 로 읽은 글자
  alsoPostedAt: { id: string; source_name: string; url: string }[];
  changedAt: string | null;
  state: {
    override: "eligible" | "ineligible" | null;
    overrideReason: string | null;
    overrideAt: string | null;
    progress: SchProgress | null;
    progressAt: string | null;
    appliedAt: string | null;
    resultAt: string | null;
    amount: string | null;
    note: string | null;
    calendarId: string | null;
    todos: Record<string, string>;
  };
  draft: {
    body: string;
    generatedBy: "template" | "llm" | "borrowed";
    borrowed: { from: string; title: string }[];
    updatedAt: string;
    createdAt: string;
    stale: boolean;
  } | null;
  otherDrafts: { id: string; title: string; updatedAt: string }[];
}

export interface SchSync {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  by: string | null;
  results: Record<string, { ok: boolean; listed?: number; matched?: number; new?: number; status?: string; reason?: string; error?: string }> | null;
  already_running?: boolean;
}

export interface SchOverview {
  items: SchItem[];
  counts: {
    eligible: number;
    review: number;
    ineligible: number;
    expired: number;
    notApplicable: number;
    notices: number;
    catalogEligible: number;
    catalogReview: number;
    catalog: number;
    inProgress: number;
  };
  profile: { exists: boolean; missing: string[]; campus: string | null; fields: string[] };
  updatedAt: string | null;
  lastOkAt: string | null;
  catalogAt: string | null;
  baselineAt: string | null;
  llm: boolean;
  sync: SchSync;
  log: string[];
}

export interface SchSource {
  key: string;
  name: string;
  org: string | null;
  group: "school" | "office" | "project" | "mine";
  kind: string;
  url: string | null;
  why: string | null;
  relevance: { level: "all" | "campus" | "related" | "open" | "other" | "mine" | "needs_profile"; why: string; default: boolean };
  enabled: boolean;
  userSet: boolean;
  lastRunAt: string | null;
  lastOkAt: string | null;
  lastCount: number | null;
  lastNew: number | null;
  error: string | null;
  stored: number;
  target: { name: string | null; homepage: string | null; listedAs: string | null; board: string | null; boardLabel: string | null; categoryLabel: string | null } | null;
  relay: boolean;
}

export interface SchSources {
  sources: SchSource[];
  sync: SchSync;
  log: string[];
  slots: string[];
  autosync: boolean;
}

export interface SchHistory {
  semesters: {
    semester: string;
    applied: number;
    selected: number;
    amountTotal: number;
    items: { id: string; title: string; progress: SchProgress; progressLabel: string; at: string; amount: string | null; note: string | null; url: string | null }[];
  }[];
}

/** 초안 기본 정보 — 장학·대외활동 초안 재료에 같이 들어간다. 이 PC 의 초안 재료에만 두고 LLM 에는 보내지 않는다(F11 basicinfo) */
export interface DraftBasic {
  name: string;
  studentId: string;
  department: string;
  grade: string;
  phone: string;
  email: string;
}

export interface SchMaterials {
  exists: boolean;
  careerGoal: string;
  activities: string;
  hardship: string;
  highlights: string;
  basic: DraftBasic;
  basicFrom: "activity" | "profile" | null; // 기본 정보 빈 칸을 미리 채운 곳
  updatedAt: string | null;
  fromProfile: boolean;
}

/** /api/status 의 scholarship 칸 — 기능 타일 */
export interface ScholarshipStatus {
  available: boolean;
  error?: string;
  updatedAt?: string | null;
  lastOkAt?: string | null;
  eligible?: number;
  review?: number;
  soon?: number;
  inProgress?: number;
  profileExists?: boolean;
  next?: { id: string; title: string; daysLeft: number; label: string } | null;
  sync?: SchSync;
}

export const GROUP_LABEL: Record<SchSource["group"], string> = {
  school: "학교 전체",
  office: "부서·센터",
  project: "사업단",
  mine: "내 단과대학·학과",
};

export const RELEVANCE: Record<SchSource["relevance"]["level"], { label: string; tone: Tone }> = {
  all: { label: "모두", tone: "neutral" },
  campus: { label: "내 캠퍼스", tone: "primary" },
  related: { label: "내 학과 관련", tone: "ok" },
  open: { label: "전공 무관 참여", tone: "info" },
  other: { label: "다른 학과 대상", tone: "neutral" },
  mine: { label: "내 소속", tone: "primary" },
  needs_profile: { label: "프로필 필요", tone: "warn" },
};

export function syncText(s: SchSync | undefined | null): string {
  if (!s) return "";
  if (s.running) return "장학 공지를 모으는 중…";
  if (s.exit_code === 0) return "수집 완료";
  if (s.exit_code === 2) return "일부 게시판을 읽지 못했습니다";
  if (s.exit_code === 4) return "수집 실패 — 네트워크를 확인하세요";
  if (s.exit_code === 3) return "이미 수집 중입니다";
  return "";
}
