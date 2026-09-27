// F10 브리핑. 원래는 서버가 08:00 에 스냅샷을 만들고(GET /api/briefing/today) 프론트는 그리기만 한다.
// 서버가 생기기 전까지 오늘 것은 실제 일정·마감으로 같은 모양을 조립하고(composeBriefing), 지난 것은 예시를 쓴다.

import type { CalEvent } from "../types";
import { addDays, fmtDue, fmtTime, isSameDay, parseLocal, startOfDay, toDateStr } from "../dates";
import { buildAssignments, isOpen, sortByPriority } from "../priority";

export interface BriefingLine {
  text: string;
  href: string;
}

export interface Briefing {
  date: string; // YYYY-MM-DD
  generatedAt: string; // HH:MM
  source: "schedule" | "catchup";
  headline: string | null; // LLM 한 줄 — 실패하면 null (그 줄만 빠진다)
  live?: boolean; // 서버 스냅샷이 아니라 화면에서 임시로 조립함
  classes: BriefingLine[];
  events: BriefingLine[];
  deadlines: BriefingLine[];
  top: BriefingLine[];
}

export function composeBriefing(events: CalEvent[], now = new Date()): Briefing {
  const today = startOfDay(now);
  const tomorrow = addDays(today, 1);
  const on = (ev: CalEvent) => {
    const s = parseLocal(ev.start);
    if (ev.allDay) {
      const endEx = ev.end ? parseLocal(ev.end) : addDays(startOfDay(s), 1);
      return startOfDay(s) <= today && today < endEx;
    }
    return isSameDay(s, today);
  };
  const mine = events
    .filter((e) => e.extendedProps.kind === "user" && on(e))
    .sort((a, b) => a.start.localeCompare(b.start))
    .map((e) => ({ text: `${e.allDay ? "종일" : fmtTime(parseLocal(e.start))} ${e.title}`, href: `/?event=${encodeURIComponent(e.id)}` }));

  const list = buildAssignments(events, {}, {}, now).filter(isOpen);
  const soon = list
    .filter((a) => a.due >= now && a.due < addDays(tomorrow, 3))
    .sort((a, b) => a.due.getTime() - b.due.getTime())
    .map((a) => ({ text: `${fmtDue(a.due, now)} ${a.title}`, href: `/?event=${encodeURIComponent(a.id)}` }));
  const top = sortByPriority(list.filter((a) => a.group !== "overdue"))
    .slice(0, 3)
    .map((a, i) => ({ text: `${i + 1}) ${a.title}`, href: "/assignments?sort=priority" }));

  return {
    date: toDateStr(today),
    generatedAt: fmtTime(now),
    source: "schedule",
    live: true,
    headline: null,
    classes: [],
    events: mine,
    deadlines: soon,
    top,
  };
}

export const demoPastBriefings: Briefing[] = [
  {
    date: "2026-09-26",
    generatedAt: "08:00",
    source: "schedule",
    headline: "오늘은 과제 2건이 급합니다.",
    classes: [
      { text: "09:00 운영체제[2]", href: "/?date=2026-09" },
      { text: "13:00 소프트웨어공학론[1]", href: "/?date=2026-09" },
    ],
    events: [
      { text: "11:00 학습 블록(운영체제 15쪽)", href: "/?date=2026-09" },
      { text: "19:00 스터디", href: "/?date=2026-09" },
    ],
    deadlines: [
      { text: "오늘 23:59 퀴즈 2회", href: "/assignments" },
      { text: "내일 23:59 3주차 실습", href: "/assignments" },
      { text: "9/28(월) 18:00 품질 보고서", href: "/assignments" },
    ],
    top: [
      { text: "1) 퀴즈 2회", href: "/assignments?sort=priority" },
      { text: "2) 3주차 실습", href: "/assignments?sort=priority" },
      { text: "3) 품질 보고서", href: "/assignments?sort=priority" },
    ],
  },
  {
    date: "2026-09-25",
    generatedAt: "10:24",
    source: "catchup",
    headline: null,
    classes: [],
    events: [],
    deadlines: [{ text: "9/26(토) 23:59 퀴즈 2회", href: "/assignments" }],
    top: [{ text: "1) 퀴즈 2회", href: "/assignments?sort=priority" }],
  },
  {
    date: "2026-09-24",
    generatedAt: "08:00",
    source: "schedule",
    headline: "추석 연휴 첫날입니다. 급한 마감은 없습니다.",
    classes: [],
    events: [{ text: "종일 추석 연휴", href: "/academic" }],
    deadlines: [],
    top: [],
  },
  {
    date: "2026-09-23",
    generatedAt: "08:00",
    source: "schedule",
    headline: "수업 3개와 마감 1건이 있습니다.",
    classes: [
      { text: "09:00 컴퓨터네트워크[1]", href: "/?date=2026-09" },
      { text: "13:00 운영체제[2]", href: "/?date=2026-09" },
      { text: "15:00 컴퓨터그래픽스[2]", href: "/?date=2026-09" },
    ],
    events: [],
    deadlines: [{ text: "오늘 23:59 4주차 동영상 시청", href: "/assignments" }],
    top: [{ text: "1) 4주차 동영상 시청", href: "/assignments?sort=priority" }],
  },
];
