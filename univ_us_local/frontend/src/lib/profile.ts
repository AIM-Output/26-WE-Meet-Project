// C2 사용자 프로필 — GET /api/profile 이 주는 모양 (C2_Profile_agent/student/service.py get() 과 짝).
// 요구사항정의서 C2 4절. 이름·학번 항목은 없다(C2-D5).

export type Track = "single" | "double" | "minor";
export const TRACK_LABEL: Record<Track, string> = { single: "단일전공", double: "복수전공", minor: "부전공" };

export const ENROLLMENT = ["재학", "휴학", "졸업유예", "수료"] as const;
export type Enrollment = (typeof ENROLLMENT)[number];

// 학자금 지원구간 0~10 (한국장학재단). 모르면 비워 둔다.
export const INCOME_BRACKETS = Array.from({ length: 11 }, (_, i) => i);
export const REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"] as const;
export const FLAG_LABEL: Record<string, string> = {
  disability: "장애",
  veteranFamily: "국가보훈 대상",
  multiChild: "다자녀 가정",
  singleParent: "한부모 가정",
  basicLivelihood: "기초생활수급·차상위",
};

export interface Gpa {
  value: number;
  scale: number; // 4.5 · 4.3 · 4.0 — 임의 환산하지 않는다
  basis: string;
}

export interface ProfileFields {
  collegeCode: string | null;
  deptCode: string | null;
  majorCode: string | null;
  college: string | null;
  department: string | null;
  major: string | null;
  deptPath: string | null; // 'AI융합대학 › 인공지능학부 › 인공지능전공'
  affiliationRetired: boolean; // 학과 개편으로 지금 목록에 없는 코드
  admissionYear: number | null;
  track: Track | null;
  grade: number | null;
  enrollmentStatus: Enrollment | null;
  semestersCompleted: number | null;
  gpa: Gpa | null;
  lastSemesterGpa: Gpa | null;
  earnedCredits: number | null;
  lastSemesterCredits: number | null;
  incomeBracket: number | null;
  residenceRegion: string | null;
  highSchoolRegion: string | null;
  flags: Record<string, boolean> | null;
  interests: string[] | null;
  draftContext: Record<string, string> | null;
}

export interface ProfileDoc {
  exists: boolean;
  profile: ProfileFields;
  filledBy: Record<string, "auto" | "user">; // 학사시스템에서 자동 / 내가 입력
  edited: string[]; // 자동으로 채운 값을 내가 고친 항목 → '수정함'
  complete: boolean; // 필수(학과·입학년도·이수유형) 입력됨
  missing: string[];
  onboardingSkipped: boolean;
  updatedAt: string | null;
  importedAt: string | null;
  changed?: string[];
}

type Editable = Omit<ProfileFields, "collegeCode" | "deptCode" | "majorCode" | "college" | "department" | "major" | "deptPath" | "affiliationRetired">;

/** PATCH /api/profile — 보낸 항목만 저장, null 이면 지운다 */
export type ProfilePatch = { [K in keyof Editable]?: Editable[K] | null } & {
  affiliation?: { deptCode: string; majorCode: string | null } | null;
  onboardingSkipped?: boolean;
};

/** 학과 선택기의 한 줄 (GET /api/master/departments) */
export interface DeptEntry {
  code: string; // 고르는 줄의 키 = 전공 코드 또는 학과 코드
  collegeCode: string;
  college: string;
  deptCode: string;
  department: string;
  majorCode: string | null;
  major: string | null;
  path: string;
  retired: boolean;
  note?: string | null; // '전공 배정 전'
}

export interface MasterSummary {
  updatedAt: string | null;
  year: number | null;
  source: "bundled" | "local" | "none";
  colleges: number;
  count: number;
}

export interface JobState {
  running: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  ok: boolean | null;
  error: string | null;
  needLogin: boolean;
  alreadyRunning?: boolean;
}

export interface ImportState extends JobState {
  result: {
    found: string[]; // 학사시스템에서 읽은 항목
    changed: string[];
    skipped: string[]; // 내가 입력한 값이라 덮지 않음
    invalid: string[];
    affiliationFound: string | null;
    importedAt: string;
  } | null;
}

export const FIELD_LABEL: Record<string, string> = {
  deptCode: "소속",
  admissionYear: "입학년도",
  track: "이수유형",
  grade: "학년",
  enrollmentStatus: "학적",
  semestersCompleted: "이수 학기",
  gpa: "평점",
  earnedCredits: "취득 학점",
  lastSemesterCredits: "직전 학기 학점",
};

export const fmtGpa = (g: Gpa | null) => (g ? `${g.value.toFixed(2)} / ${g.scale}` : null);
