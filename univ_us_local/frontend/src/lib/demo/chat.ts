// F9 대화 예시 — Frontend-Route 14절. 쓰기는 미리보기 카드를 확인해야만 실행된다.

export type ChatMsg =
  | { id: string; role: "user"; text: string; at: string }
  | {
      id: string;
      role: "assistant";
      text: string;
      at: string;
      list?: { title: string; when: string; sub: string }[];
      link?: { label: string; href: string };
    }
  | {
      id: string;
      role: "preview";
      at: string;
      title: string;
      start: string;
      end: string;
      category: string;
      conflict?: string;
      state: "pending" | "confirmed" | "canceled" | "expired";
    }
  | { id: string; role: "system"; text: string; at: string };

export const demoChat: ChatMsg[] = [
  { id: "u1", role: "user", text: "이번 주 마감 뭐 남았어?", at: "2026-09-26T21:02" },
  {
    id: "a1",
    role: "assistant",
    text: "3건 있습니다",
    at: "2026-09-26T21:02",
    list: [
      { title: "퀴즈 2회", when: "오늘 23:59", sub: "컴퓨터네트워크" },
      { title: "3주차 실습", when: "내일 23:59", sub: "운영체제" },
      { title: "품질 보고서", when: "9/28 18:00", sub: "소프트웨어공학론" },
    ],
    link: { label: "과제 목록 열기", href: "/assignments" },
  },
  { id: "s1", role: "system", text: "e클래스 동기화를 시작했습니다", at: "2026-09-26T21:04" },
  { id: "u2", role: "user", text: "다음 주 목요일 발표 리허설 저녁 8시", at: "2026-09-27T09:12" },
  {
    id: "p1",
    role: "preview",
    at: "2026-09-27T09:12",
    title: "발표 리허설",
    start: "2026-10-01T20:00",
    end: "2026-10-01T22:00",
    category: "개인",
    conflict: "팀 회의 20:00~21:00",
    state: "pending",
  },
];

export const CHAT_EXAMPLES = ["이번 주 마감 뭐 남았어?", "내일 오후 3시 스터디 2시간", "학사일정 열어줘"];
