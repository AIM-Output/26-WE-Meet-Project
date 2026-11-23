// F12 대외활동 — /api/opportunities* 응답 모양 (F12_Activity_agent/activity/service.py · api.py 와 짝).
// 관심사 등급(시스템이 계산)과 진행 상태(사용자가 움직임)는 서로 다른 축이다 — F11 장학과 같은 구조.
// 원천은 F11 과 같고, 장학이 아닌 공지(교내 프로그램·공모전·대외활동·취업·해외·창업·기자재 대여 …)를 다룬다.
// 신청서 초안·초안 재료는 2026-11-19 폐기 — 진행 상태는 담음 → 지원함 → 선정/탈락 · 관심 없음.

import type { Tone } from "@/components/ui/Chip";
import type { Interests } from "./profile";
import type { SchSource, SchSources, SchSync } from "./scholarships";

export type ActGrade = "match" | "related" | "other";
export type ActStatus = "open" | "expired" | "result" | "stale" | "not_for_me";
export type ActProgress = "saved" | "applied" | "selected" | "not_selected" | "skipped";

export const GRADE_TONE: Record<ActGrade, Tone> = { match: "ok", related: "info", other: "neutral" };
export const PROGRESS_TONE: Record<ActProgress, Tone> = {
  saved: "primary",
  applied: "accent",
  selected: "ok",
  not_selected: "danger",
  skipped: "neutral",
};

export interface Hit {
  type: "tag" | "keyword" | "exclude" | "llm" | "affiliation";
  label: string;
  word?: string;
  where?: "title" | "body";
  reason?: string | null;
}

export interface ActItem {
  id: string;
  title: string;
  rawTitle: string;
  url: string;
  postedAt: string | null;
  firstSeen: string;
  source: string;
  sourceName: string;
  sourceGroup: SchSource["group"] | null;
  isProgram: boolean; // 사업단 원천(또는 사업단이 학교 공지에 올린 글) — '사업단' 탭
  writer: string | null;
  org: string | null;
  unit: { key: string; org: string } | null;
  category: string | null;
  categoryLabel: string | null;
  boardCategory: string | null;
  grade: ActGrade | null; // 관심사를 아직 안 골랐으면 null
  systemGrade: ActGrade | null;
  gradeLabel: string | null; // 내 관심사 · 관련 있음 · 관심 밖
  flipped: boolean;
  hits: Hit[];
  chips: string[]; // 이유 칩 — 걸린 태그·“키워드”·LLM 판단·내 학과 관련 원천
  by: "keyword" | "llm" | "affiliation" | "exclude" | "none" | null;
  status: ActStatus;
  statusLabel: string;
  deadline: string | null;
  daysLeft: number | null;
  period: { start: string | null; end: string | null; raw: string | null } | null;
  target: string | null;
  place: string | null;
  benefit: string | null;
  audienceNote: string | null; // '3·4학년 대상 — 내 2학년'
  progress: ActProgress | null;
  progressLabel: string | null;
  saved: boolean;
  onCalendar: boolean;
  askApplied: boolean; // 담아 둔 글의 마감이 지났다 → '지원하셨나요?'
  isNew: boolean;
  needsOcr: boolean;
  ocr: boolean; // 이미지 속 글자를 OCR 로 읽었다
}

export interface ActDetail extends ActItem {
  reasons: string[];
  grades: number[] | null;
  eventPeriod: string | null;
  fee: string | null;
  capacity: string | null;
  documents: string[];
  applyMethod: string | null;
  applyUrl: string | null;
  contact: string | null;
  notes: string[];
  evidence: Record<string, string>;
  body: string;
  bodyTruncated: boolean;
  attachments: { name: string; url: string; ext: string; read: boolean; ocr?: boolean }[];
  ocrText: string | null; // 이미지에서 OCR 로 읽은 글자
  alsoPostedAt: { id: string; source_name: string; url: string }[];
  changedAt: string | null;
  state: {
    override: ActGrade | null;
    progress: ActProgress | null;
    savedAt: string | null;
    appliedAt: string | null;
    calendarId: string | null;
    todos: Record<string, string>;
    note: string | null;
  };
}

export interface ActOverview {
  items: ActItem[];
  counts: {
    match: number;
    related: number;
    other: number;
    open: number;
    closed: number;
    total: number;
    program: number;
    programMatch: number;
    saved: number;
    categories: Record<string, number>;
  };
  interests: Interests & { set: boolean };
  tags: { key: string; words: string[] }[];
  categories: Record<string, string>;
  wide: { keyword: string; count: number }[];
  profile: { exists: boolean; missing: string[] };
  updatedAt: string | null;
  lastOkAt: string | null;
  baselineAt: string | null;
  llm: boolean;
  sync: ActSync;
  log: string[];
}

export type ActSync = SchSync & { waiting?: boolean };
export type ActSources = Omit<SchSources, "sync"> & { sync: ActSync };

export interface ActHistory {
  semesters: {
    semester: string;
    saved: number;
    applied: number;
    selected: number;
    items: { id: string; title: string; progress: ActProgress; progressLabel: string; at: string; note: string | null; categoryLabel: string | null; url: string | null }[];
  }[];
}

/** /api/status 의 activity 칸 — 기능 타일 */
export interface ActivityStatus {
  available: boolean;
  error?: string;
  updatedAt?: string | null;
  lastOkAt?: string | null;
  interestsSet?: boolean;
  open?: number;
  match?: number;
  related?: number;
  newMatch?: number;
  saved?: number;
  soon?: number;
  profileExists?: boolean;
  next?: { id: string; title: string; daysLeft: number } | null;
  sync?: ActSync;
}

export function actSyncText(s: ActSync | undefined | null): string {
  if (!s) return "";
  if (s.running) return s.waiting ? "장학 공지 수집이 끝나기를 기다리는 중…" : "대외활동 공지를 모으는 중…";
  if (s.exit_code === 0) return "수집 완료";
  if (s.exit_code === 2) return "일부 게시판을 읽지 못했습니다";
  if (s.exit_code === 4) return "수집 실패 — 네트워크를 확인하세요";
  if (s.exit_code === 3) return "이미 수집 중입니다";
  return "";
}
