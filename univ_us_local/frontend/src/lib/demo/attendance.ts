// F3 출결 예시 — Frontend-Route 8-3. 한도는 시수(교시) 기준 1/4, 지각 3회 = 결석 1회.

export type AttendState = "출석" | "결석" | "지각" | "공결";
export type RiskLevel = "안전" | "주의" | "위험" | "초과";

export interface Session {
  id: string;
  date: string; // YYYY-MM-DD
  periods: string; // '3·4교시'
  hours: number;
  state: AttendState | null;
  canceled?: boolean;
  makeup?: boolean;
}

export interface AttendCourse {
  courseId: string; // e클래스 과목 id
  name: string;
  code: string;
  slots: { day: string; periods: string; auto: boolean }[];
  planned: number; // 예정 시수
  canceled: number;
  makeup: number;
  absent: number;
  late: number;
  lateRule: number; // 지각 n회 = 결석 1
  manualAdjust: number;
  sessions: Session[];
}

function sessions(prefix: string, rows: [string, string, number, AttendState | null, boolean?][]): Session[] {
  return rows.map(([date, periods, hours, state, canceled], i) => ({ id: `${prefix}-${i}`, date, periods, hours, state, canceled }));
}

export const demoAttendance: AttendCourse[] = [
  {
    courseId: "74245",
    name: "운영체제[2]",
    code: "CIS2001",
    slots: [
      { day: "월", periods: "5·6교시", auto: true },
      { day: "수", periods: "5교시", auto: true },
    ],
    planned: 45,
    canceled: 2,
    makeup: 0,
    absent: 7,
    late: 3,
    lateRule: 3,
    manualAdjust: 0,
    sessions: sessions("os", [
      ["2026-09-02", "5교시", 1, "출석"],
      ["2026-09-07", "5·6교시", 2, "결석"],
      ["2026-09-09", "5교시", 1, "지각"],
      ["2026-09-14", "5·6교시", 2, null, true],
      ["2026-09-16", "5교시", 1, "지각"],
      ["2026-09-21", "5·6교시", 2, "출석"],
      ["2026-09-23", "5교시", 1, null],
      ["2026-09-28", "5·6교시", 2, null],
      ["2026-09-30", "5교시", 1, null],
    ]),
  },
  {
    courseId: "74261",
    name: "소프트웨어공학론[1]",
    code: "CIS3030",
    slots: [{ day: "화", periods: "3·4교시", auto: true }],
    planned: 40,
    canceled: 0,
    makeup: 0,
    absent: 6,
    late: 0,
    lateRule: 3,
    manualAdjust: 0,
    sessions: sessions("se", [
      ["2026-09-01", "3·4교시", 2, "출석"],
      ["2026-09-08", "3·4교시", 2, "결석"],
      ["2026-09-15", "3·4교시", 2, "출석"],
      ["2026-09-22", "3·4교시", 2, null],
      ["2026-09-29", "3·4교시", 2, null],
    ]),
  },
  {
    courseId: "75381",
    name: "컴퓨터네트워크[1]",
    code: "ECE3026",
    slots: [{ day: "수", periods: "1·2교시", auto: true }],
    planned: 44,
    canceled: 0,
    makeup: 0,
    absent: 1,
    late: 1,
    lateRule: 3,
    manualAdjust: 0,
    sessions: sessions("cn", [
      ["2026-09-02", "1·2교시", 2, "출석"],
      ["2026-09-09", "1·2교시", 2, "결석"],
      ["2026-09-16", "1·2교시", 2, "지각"],
      ["2026-09-23", "1·2교시", 2, null],
      ["2026-09-30", "1·2교시", 2, null],
    ]),
  },
  {
    courseId: "74926",
    name: "동양의역사와문화[2]",
    code: "CLT0835",
    slots: [],
    planned: 0,
    canceled: 0,
    makeup: 0,
    absent: 0,
    late: 0,
    lateRule: 3,
    manualAdjust: 0,
    sessions: [],
  },
];

/** 한도 = (예정 − 휴강 + 보강) × 1/4. 사용 = 결석 시수 + ⌊지각/환산⌋. */
export function attendanceStats(c: AttendCourse) {
  const total = c.planned - c.canceled + c.makeup;
  const limit = total / 4;
  const used = c.absent + Math.floor(c.late / c.lateRule) + c.manualAdjust;
  const ratio = limit > 0 ? used / limit : 0;
  const level: RiskLevel = ratio > 1 ? "초과" : ratio >= 0.7 ? "위험" : ratio >= 0.5 ? "주의" : "안전";
  const perSession = c.sessions.length ? c.sessions.reduce((s, x) => s + x.hours, 0) / c.sessions.length : 2;
  const spare = Math.max(0, Math.floor((limit - used) / perSession)); // 남은 여유 회차
  return { total, limit, used, ratio, level, spare };
}

export const demoSemesterRange = { start: "2026-09-01", end: "2026-12-19", source: "학사일정" };
