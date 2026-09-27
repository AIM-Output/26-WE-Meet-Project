// 알림 팝오버 예시 — Frontend-Route 6-5. PC 가 꺼져 있던 동안의 알림은 '놓친 알림'으로 따로 묶는다.

export interface AppNotification {
  id: string;
  kind: "academic" | "deadline" | "change" | "briefing" | "opportunity" | "attendance";
  title: string;
  at: string; // YYYY-MM-DDTHH:MM
  missed: boolean;
  read: boolean;
  href: string; // 알림 클릭 → 상세 모달이 열린 URL (19절 5번)
}

export const demoNotifications: AppNotification[] = [
  { id: "n1", kind: "academic", title: "D-3 · 1학기 성적 이의신청", at: "2026-09-25T09:00", missed: true, read: false, href: "/academic?event=ac:2026-2-grade-objection" },
  { id: "n2", kind: "opportunity", title: "해당 장학 2건 · 두을장학재단 제29기 외", at: "2026-09-26T06:10", missed: true, read: false, href: "/opportunities?tab=scholarship" },
  { id: "n3", kind: "change", title: "등록금 납부 기간이 바뀌었습니다", at: "2026-09-27T08:10", missed: false, read: false, href: "/academic?event=ac:2026-2-tuition" },
  { id: "n4", kind: "briefing", title: "오늘 브리핑이 도착했습니다", at: "2026-09-27T08:00", missed: false, read: true, href: "/briefing" },
  { id: "n5", kind: "attendance", title: "운영체제[2] 결석 한도 '주의' 단계입니다", at: "2026-09-27T07:40", missed: false, read: true, href: "/attendance?course=74245" },
];
