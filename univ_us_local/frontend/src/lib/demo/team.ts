// F16 팀플 예시 — Frontend-Route 18절. 공유되는 것은 '바쁜 시간대(시각만)·표시 이름·팀 할 일' 뿐이다.

export interface Member {
  id: string;
  name: string;
  role: "팀장" | "팀원";
  me?: boolean;
  updated: string; // '2시간 전'
  stale?: boolean;
  sharing: boolean;
}

export const demoTeam = {
  id: "cap5",
  name: "캡스톤 5조",
  code: "K7Q2MX",
  members: [
    { id: "m1", name: "하람", role: "팀장", me: true, updated: "방금", sharing: true },
    { id: "m2", name: "지훈", role: "팀원", updated: "2시간 전", sharing: true },
    { id: "m3", name: "서연", role: "팀원", updated: "30분 전", sharing: true },
    { id: "m4", name: "민준", role: "팀원", updated: "3일 전", stale: true, sharing: true },
    { id: "m5", name: "유나", role: "팀원", updated: "—", sharing: false },
  ] as Member[],
};

export const TEAM_DAYS = ["월", "화", "수", "목", "금"] as const;
export const TEAM_HOURS = [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21] as const;

/** 요일×시간 → 바쁜 사람 수 (이름·제목 없음) */
export const demoBusy: number[][] = [
  // 09 10 11 12 13 14 15 16 17 18 19 20 21
  [3, 3, 2, 1, 4, 4, 2, 1, 0, 0, 1, 1, 0], // 월
  [2, 2, 1, 0, 3, 3, 3, 2, 1, 0, 0, 1, 1], // 화
  [4, 4, 1, 1, 2, 1, 1, 0, 0, 1, 0, 0, 0], // 수
  [1, 1, 3, 2, 0, 0, 2, 2, 1, 1, 0, 0, 1], // 목
  [3, 2, 2, 1, 1, 1, 0, 0, 2, 2, 1, 0, 0], // 금
];

export interface Candidate {
  id: string;
  label: string;
  available: number;
  total: number;
  note: string;
  best?: boolean;
  day: number;
  hour: number;
}

export const demoCandidates: Candidate[] = [
  { id: "c1", label: "10/1(목) 14:00~15:00", available: 5, total: 5, note: "전원 가능", best: true, day: 3, hour: 14 },
  { id: "c2", label: "9/30(수) 16:00~17:00", available: 4, total: 5, note: "4/5 — 민준 불가", day: 2, hour: 16 },
  { id: "c3", label: "10/2(금) 19:00~20:00", available: 3, total: 5, note: "3/5 · 2명 정보 없음", day: 4, hour: 19 },
];

export type Vote = "가능" | "어려움" | "불가" | null;

export const demoPoll = {
  id: "poll1",
  closes: "내일 18:00",
  options: ["10/1(목) 14:00", "9/30(수) 16:00", "10/2(금) 19:00"],
  votes: {
    m1: [null, null, null],
    m2: ["가능", "가능", "불가"],
    m3: ["가능", "어려움", "가능"],
    m4: [null, null, null],
    m5: ["가능", "불가", "어려움"],
  } as Record<string, Vote[]>,
};

export const demoTeamTasks = [
  { id: "t1", title: "기획서 초안 작성", owners: ["m1"], due: "2026-09-29", done: false },
  { id: "t2", title: "경쟁 서비스 조사", owners: ["m2", "m3"], due: "2026-09-28", done: true, doneBy: "지훈", doneAt: "9/26" },
  { id: "t3", title: "발표 슬라이드", owners: ["m3"], due: "2026-10-02", done: false },
  { id: "t4", title: "데이터 수집 스크립트", owners: ["m4"], due: "2026-09-25", done: false },
  { id: "t5", title: "회의록 정리", owners: ["m5"], due: "2026-10-05", done: false },
];
