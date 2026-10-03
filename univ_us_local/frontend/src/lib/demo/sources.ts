// 수집 원천 예시 — Frontend-Route 6-6·17-5. e클래스(F6)는 /api/sources/eclass, 학사(F1) 원천은 /api/sources, 기이수성적(F2)은 /api/status 의 graduation 으로 실제 값을 쓴다.

export interface SourceRow {
  key: string;
  name: string;
  kind: "학사일정표" | "공지" | "학과" | "학사시스템" | "게시판";
  interval: string;
  last: string;
  count: string;
  state: "ok" | "retry" | "login" | "failed";
  enabled: boolean;
  builtin: boolean;
  error?: string;
}

export const demoSources: SourceRow[] = [
  { key: "hakstd-scholar", name: "학사정보시스템 › 장학 카탈로그 (F11)", kind: "학사시스템", interval: "주 1회", last: "9/21 22:10", count: "장학 96", state: "login", enabled: true, builtin: true },
];

export const demoBoards: SourceRow[] = [
  { key: "home-scholar", name: "전남대 홈페이지 › 장학안내", kind: "게시판", interval: "06·18시", last: "오늘 06:00", count: "12건", state: "ok", enabled: true, builtin: true },
  { key: "aicoss", name: "AICOSS 사업단", kind: "게시판", interval: "06·18시", last: "오늘 06:00", count: "3건", state: "ok", enabled: true, builtin: true },
  { key: "my-board", name: "우리 학과 산학협력단", kind: "게시판", interval: "06·18시", last: "오늘 06:00", count: "—", state: "failed", enabled: true, builtin: false, error: "게시판 목록을 찾지 못했습니다" },
];
