// F4 강의자료 — /api/materials 가 주는 모양 (F4_Textbook_agent/textbook/service.py 의 view·overview 와 1:1).
// 1차 범위는 **자료를 모아 두고 열어 보는 것까지**다. 요약·문제·질문(RAG)은 analysis.available 이 false 인 동안 예시로 둔다.

import type { Tone } from "@/components/ui/Chip";

export type MaterialKind = "lecture" | "board" | "assignment" | "upload";
/** pending 대기 · running 분석 중 · done 준비됨 · failed 실패 · ocr_needed 텍스트 없음 · locked 암호 · unsupported 분석 제외 · duplicate 중복 · missing 파일 없음 */
export type MaterialState =
  | "pending"
  | "running"
  | "done"
  | "failed"
  | "ocr_needed"
  | "locked"
  | "unsupported"
  | "duplicate"
  | "missing";

export interface MaterialItem {
  id: string; // mt:<해시12>
  courseId: string;
  course: string;
  title: string;
  source: "eclass" | "upload";
  kind: MaterialKind;
  kindLabel: string;
  activity: string; // e클래스 활동·게시판 이름
  post: string; // 게시판 글 제목 (첨부일 때)
  ext: string;
  pages: number | null;
  size: number;
  sizeMB: number;
  week: number | null;
  weekGuess: boolean; // 이름에서 추정한 주차다 — 화면에 '추정'을 밝힌다
  stored: "link" | "copy" | "upload" | "eclass" | ""; // F4 보관함에 어떻게 들여왔나 (eclass = 못 들여와 F6 자리를 가리킴)
  detached: boolean; // e클래스 목록에서는 내려갔지만 보관본이 남아 있다 — 이때만 지울 수 있다
  state: MaterialState;
  stateLabel: string;
  note: string;
  textState: "text" | "none" | "unknown";
  dupOf: string | null;
  missing: boolean;
  indexable: boolean;
  viewable: boolean; // 앱 안에서 바로 열리는 형식인가 (아니면 내려받기만)
  canDelete: boolean; // 직접 추가한 파일만 true (e클래스 수집분은 원본이 그쪽)
  eclassUrl: string;
  fileUrl: string;
  downloadUrl: string;
  addedAt: string;
  collectedAt: string | null;
}

export interface MaterialDetail extends MaterialItem {
  path: string; // 보관함 안의 실제 경로
  originPath: string; // 어디서 들여왔나 (F6 수집 폴더)
  sameActivity: { id: string; title: string }[];
  dupWith?: { id: string; title: string } | null;
}

export interface MaterialCourse {
  id: string;
  name: string;
  short: string;
  code: string;
  section: string;
  color: string | null;
  files: number;
  pages: number;
  byKind: Record<MaterialKind, number>;
  states: Partial<Record<MaterialState, number>>;
  uploads: number;
  ready: number;
  waiting: number;
  attention: number; // 확인 필요 — 암호·실패·파일 없음 (텍스트 없는 PDF 는 안내만, 세지 않는다)
  lastCollectedAt: string | null;
}

export interface MaterialTotals {
  files: number;
  pages: number;
  sizeMB: number;
  courses: number;
  byKind: Record<MaterialKind, number>;
  states: Partial<Record<MaterialState, number>>;
  uploads: number;
  attention: number;
  stored: Partial<Record<"link" | "copy" | "upload" | "eclass", number>>;
  detached: number;
}

export interface MaterialScan {
  skipped?: boolean;
  files: number;
  new: number;
  changed: number;
  removed: number;
  missing: number;
  placed: number;
  detached: number;
  reread: number;
  duplicates: number;
  elapsedMs: number;
  updatedAt: string | null;
}

export interface MaterialsOverview {
  updatedAt: string | null;
  scannedAt: string | null;
  scan: MaterialScan | null;
  source: {
    eclass: { available: boolean; dataDir: string; manifestAt: string | null; note: string };
    libraryDir: string; // 자료가 실제로 보관되는 곳 (F4_Textbook_agent/data/materials)
    uploadDir: string;
  };
  limits: { maxFileMB: number; allowedExt: string[]; indexableExt: string[] };
  totals: MaterialTotals;
  courses: MaterialCourse[];
  materials: MaterialItem[];
  filter: { course: string | null; kind: MaterialKind | null; q: string };
  analysis: { available: boolean; note: string };
}

/** /api/status 의 materials 칸 (기능 타일) */
export interface MaterialsStatus {
  available: boolean;
  error?: string;
  updatedAt?: string | null;
  scannedAt?: string | null;
  files?: number;
  pages?: number;
  courses?: number;
  uploads?: number;
  attention?: number;
  eclassAvailable?: boolean;
}

/** 상태 색 — 색만으로 구분하지 않는다(라벨은 서버가 stateLabel 로 준다) */
export const STATE_TONE: Record<MaterialState, Tone> = {
  done: "ok",
  running: "info",
  pending: "neutral",
  failed: "danger",
  missing: "danger",
  ocr_needed: "neutral", // 조치할 것이 없다 — 경고색을 쓰지 않는다
  locked: "warn",
  unsupported: "neutral",
  duplicate: "neutral",
};

export const KIND_TONE: Record<MaterialKind, Tone> = {
  lecture: "primary",
  board: "info",
  assignment: "accent",
  upload: "study",
};

export const KIND_FILTERS: { key: MaterialKind | "all"; label: string }[] = [
  { key: "all", label: "전체" },
  { key: "lecture", label: "강의자료" },
  { key: "board", label: "게시판 첨부" },
  { key: "assignment", label: "과제 첨부" },
  { key: "upload", label: "직접 추가" },
];

export const sizeText = (m: { sizeMB: number; size: number }) =>
  m.size < 1024 * 1024 ? `${Math.max(1, Math.round(m.size / 1024))}KB` : `${m.sizeMB}MB`;

export const pagesText = (m: { pages: number | null; ext: string }) =>
  m.pages ? `${m.pages}${m.ext === ".pptx" || m.ext === ".ppt" ? "장" : "쪽"}` : "—";

/** 원문 뷰어 주소 — 브라우저 PDF 뷰어는 #page=12 로 그 쪽을 연다 (F4-S04·S05) */
export const fileSrc = (m: Pick<MaterialItem, "fileUrl">, page?: number | null) =>
  `${m.fileUrl}${page && page > 1 ? `#page=${page}` : ""}`;
