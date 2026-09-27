// F2 졸업요건 예시 — Frontend-Route 7-3 의 숫자(98/130, 전공필수 30/36 …).
// 계산은 백엔드 규칙 코드(POST /api/graduation/simulate)만 한다. 여기 값은 그 응답의 예시다.

export type AreaKey = "major_required" | "major_elective" | "core_liberal" | "general_elective";

export interface GradArea {
  key: AreaKey;
  label: string;
  earned: number;
  required: number;
  remainingCourses?: number;
}

export interface GradCourse {
  id: string;
  year: number;
  term: "1" | "2" | "여름" | "겨울";
  name: string;
  credits: number;
  grade: string;
  area: AreaKey | null; // null = 미분류
  source: "auto" | "manual";
  excluded?: boolean;
}

export interface Certification {
  id: string;
  label: string;
  state: "done" | "todo" | "unknown";
  note: string;
}

export const AREA_LABEL: Record<AreaKey, string> = {
  major_required: "전공필수",
  major_elective: "전공선택",
  core_liberal: "핵심교양",
  general_elective: "일반선택",
};

export const demoGradStatus = {
  total: { earned: 98, required: 130 },
  gpa: { value: 3.42, min: 1.75 },
  verdict: "부족" as "부족" | "충족" | "확인 필요",
  ruleset: { year: 2023, dept: "인공지능학부", track: "single" as const, matchLevel: "정확" },
  areas: [
    { key: "major_required", label: "전공필수", earned: 30, required: 36, remainingCourses: 2 },
    { key: "major_elective", label: "전공선택", earned: 33, required: 39 },
    { key: "core_liberal", label: "핵심교양", earned: 9, required: 12 },
    { key: "general_elective", label: "일반선택", earned: 26, required: 0 },
  ] satisfies GradArea[],
};

export const demoCertifications: Certification[] = [
  { id: "eng", label: "영어인증", state: "done", note: "TOEIC 780 (2025-04)" },
  { id: "vol", label: "봉사 30시간", state: "todo", note: "" },
  { id: "cap", label: "캡스톤디자인", state: "unknown", note: "" },
];

export const demoGradCourses: GradCourse[] = [
  { id: "g1", year: 2023, term: "1", name: "컴퓨터프로그래밍", credits: 3, grade: "A+", area: "major_required", source: "auto" },
  { id: "g2", year: 2023, term: "1", name: "대학글쓰기", credits: 3, grade: "A0", area: "core_liberal", source: "auto" },
  { id: "g3", year: 2023, term: "2", name: "자료구조", credits: 3, grade: "B+", area: "major_required", source: "auto" },
  { id: "g4", year: 2023, term: "2", name: "이산수학", credits: 3, grade: "A0", area: "major_elective", source: "auto" },
  { id: "g5", year: 2024, term: "1", name: "알고리즘", credits: 3, grade: "B0", area: "major_required", source: "auto" },
  { id: "g6", year: 2024, term: "1", name: "현대사회와윤리", credits: 2, grade: "P", area: null, source: "auto" },
  { id: "g7", year: 2024, term: "2", name: "기계학습", credits: 3, grade: "A0", area: "major_elective", source: "auto" },
  { id: "g8", year: 2024, term: "여름", name: "창업과리더십", credits: 1, grade: "P", area: null, source: "auto" },
  { id: "g9", year: 2025, term: "1", name: "데이터베이스", credits: 3, grade: "A+", area: "major_required", source: "auto" },
  { id: "g10", year: 2025, term: "1", name: "교내 AI 캠프(학점인정)", credits: 2, grade: "P", area: null, source: "manual" },
  { id: "g11", year: 2025, term: "2", name: "컴퓨터비전", credits: 3, grade: "B+", area: "major_elective", source: "auto" },
];

export const demoAreaCourses: Record<AreaKey, string[]> = {
  major_required: ["컴퓨터프로그래밍", "자료구조", "알고리즘", "데이터베이스", "…외 6과목"],
  major_elective: ["이산수학", "기계학습", "컴퓨터비전", "…외 8과목"],
  core_liberal: ["대학글쓰기", "…외 2과목"],
  general_elective: ["…9과목"],
};

export const demoRuleset = {
  year: 2023,
  dept: "AI융합대학 › 인공지능학부 › 인공지능전공",
  track: "single" as const,
  edited: false,
  rows: [
    { key: "total", label: "졸업 학점", value: 130, unit: "학점", basis: "학칙 별표1 · 2023 요람 12쪽" },
    { key: "gpa", label: "최저 평점", value: 1.75, unit: "/4.5", basis: "학칙 제54조" },
    { key: "major_required", label: "전공필수", value: 36, unit: "학점", basis: "2023 요람 인공지능학부 148쪽" },
    { key: "major_elective", label: "전공선택", value: 39, unit: "학점", basis: "2023 요람 인공지능학부 148쪽" },
    { key: "core_liberal", label: "핵심교양", value: 12, unit: "학점", basis: "교양교육과정 운영지침 제7조" },
  ],
  mapping: [
    { from: "전필", to: "major_required" as AreaKey },
    { from: "전선", to: "major_elective" as AreaKey },
    { from: "핵교", to: "core_liberal" as AreaKey },
    { from: "일선", to: "general_elective" as AreaKey },
  ],
};
