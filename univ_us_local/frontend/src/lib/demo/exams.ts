// F5 시험 예시 — Frontend-Route 10-3·10-4.

export interface Exam {
  id: string; // ex:…
  courseId: string;
  course: string;
  kind: "중간고사" | "기말고사" | "퀴즈";
  date: string; // YYYY-MM-DDTHH:MM
  room: string;
  range: string | null;
  pages: number | null;
  status: "confirmed" | "review";
  source: "notice" | "manual";
  noticeUrl?: string;
  plan?: { done: number; total: number; behindDays: number };
}

export const demoExams: Exam[] = [
  {
    id: "ex:74245:mid",
    courseId: "74245",
    course: "운영체제[2]",
    kind: "중간고사",
    date: "2026-10-21T14:00",
    room: "공7-223",
    range: "3~7주차",
    pages: 120,
    status: "confirmed",
    source: "notice",
    noticeUrl: "https://sel.jnu.ac.kr/mod/ubboard/view.php?id=1446165",
    plan: { done: 45, total: 120, behindDays: 2 },
  },
  {
    id: "ex:75381:mid",
    courseId: "75381",
    course: "컴퓨터네트워크[1]",
    kind: "중간고사",
    date: "2026-10-23T10:00",
    room: "공6-105",
    range: null,
    pages: null,
    status: "confirmed",
    source: "manual",
  },
  {
    id: "ex:74261:mid",
    courseId: "74261",
    course: "소프트웨어공학론[1]",
    kind: "중간고사",
    date: "2026-10-20T13:00",
    room: "미정",
    range: "1~6주차",
    pages: 180,
    status: "review",
    source: "notice",
    noticeUrl: "https://sel.jnu.ac.kr/mod/ubboard/view.php?id=1442577",
  },
  {
    id: "ex:74259:mid",
    courseId: "74259",
    course: "컴퓨터그래픽스[2]",
    kind: "중간고사",
    date: "2026-10-22T15:00",
    room: "융대 301",
    range: null,
    pages: null,
    status: "review",
    source: "notice",
    noticeUrl: "https://sel.jnu.ac.kr/mod/ubboard/view.php?id=1443808",
  },
];

/** 미리보기 표 예시 (POST /api/study-plans/preview 응답 모양) */
export const demoPlanPreview = [
  { date: "2026-10-12", label: "3주차 1~15쪽", pages: 15, minutes: 38 },
  { date: "2026-10-13", label: "3주차 16~30쪽", pages: 15, minutes: 38 },
  { date: "2026-10-14", label: "제외일", pages: 0, minutes: 0, excluded: true },
  { date: "2026-10-15", label: "4주차 1~18쪽", pages: 18, minutes: 45 },
  { date: "2026-10-16", label: "4~5주차 19~36쪽", pages: 18, minutes: 45 },
  { date: "2026-10-17", label: "5~6주차", pages: 18, minutes: 45 },
  { date: "2026-10-18", label: "6~7주차", pages: 18, minutes: 45 },
  { date: "2026-10-19", label: "7주차 마무리", pages: 18, minutes: 56 },
  { date: "2026-10-20", label: "전체 복습", pages: 0, minutes: 90, review: true },
];
