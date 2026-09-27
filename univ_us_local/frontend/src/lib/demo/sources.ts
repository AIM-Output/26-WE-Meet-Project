// 수집 원천 예시 — Frontend-Route 6-6·11-6·17-5. e클래스 행은 실제 /api/status 를 쓴다.

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
  { key: "haksa", name: "전남대 학사일정", kind: "학사일정표", interval: "06·18시", last: "오늘 06:00", count: "24건", state: "ok", enabled: true, builtin: true },
  { key: "haksa-notice", name: "학사공지 게시판", kind: "공지", interval: "06·18시", last: "오늘 06:00", count: "12건", state: "ok", enabled: true, builtin: true },
  { key: "hakstd", name: "학사정보시스템 (이수내역·장학 카탈로그)", kind: "학사시스템", interval: "주 1회", last: "9/21 22:10", count: "과목 38", state: "login", enabled: true, builtin: true },
  { key: "dept-ai", name: "인공지능학부 공지", kind: "학과", interval: "06·18시", last: "오늘 06:00", count: "5건", state: "ok", enabled: true, builtin: true },
];

export const demoBoards: SourceRow[] = [
  { key: "home-scholar", name: "전남대 홈페이지 › 장학안내", kind: "게시판", interval: "06·18시", last: "오늘 06:00", count: "12건", state: "ok", enabled: true, builtin: true },
  { key: "aicoss", name: "AICOSS 사업단", kind: "게시판", interval: "06·18시", last: "오늘 06:00", count: "3건", state: "ok", enabled: true, builtin: true },
  { key: "my-board", name: "우리 학과 산학협력단", kind: "게시판", interval: "06·18시", last: "오늘 06:00", count: "—", state: "failed", enabled: true, builtin: false, error: "게시판 목록을 찾지 못했습니다" },
];

export const demoRunHistory = [
  { at: "12:00", result: "성공", detail: "38초", tone: "ok" as const },
  { at: "08:00", result: "재시도 2회 후 성공", detail: "네트워크", tone: "warn" as const },
  { at: "04:00", result: "세션 만료", detail: "로그인 필요", tone: "danger" as const },
];
