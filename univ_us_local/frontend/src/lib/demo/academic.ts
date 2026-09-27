// F1 학사일정 예시 — Frontend-Route 6절 와이어프레임의 항목들.

export type AcademicType = "register" | "payment" | "semester" | "exam" | "leave" | "grade" | "holiday" | "etc";

export interface AcademicEvent {
  id: string; // ac:…
  title: string;
  type: AcademicType;
  start: string; // YYYY-MM-DD 또는 YYYY-MM-DDTHH:MM
  end: string | null; // 마지막 날(포함) 또는 종료 일시
  allDay: boolean;
  target: string;
  appliesToMe: boolean | null; // null = 판단 불가
  status: "confirmed" | "review" | "hidden";
  source: string;
  sourceUrl: string;
  evidence: string;
  confidence: number;
  changedFrom?: string; // 이전 일정(변경됨 칩)
  reminders: number[]; // D-n
  memo: string;
}

// 색은 요구사항정의서 F1 '색·아이콘' 표 — 과목 색·내 일정 색과 겹치지 않는 어두운 톤
export const ACADEMIC_TYPE_META: Record<AcademicType, { label: string; color: string }> = {
  register: { label: "수강신청·정정", color: "#4338ca" },
  payment: { label: "등록·납부", color: "#b45309" },
  semester: { label: "개강·방학", color: "#64748b" },
  exam: { label: "시험", color: "#9a3412" },
  leave: { label: "학적", color: "#334155" },
  grade: { label: "성적", color: "#0f766e" },
  holiday: { label: "휴업일", color: "#9f1239" },
  etc: { label: "행사", color: "#7e22ce" },
};

const HAKSA = "https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx?boardID=5";
const NOTICE = "https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx?boardID=5&cate=5";

function ev(
  id: string,
  title: string,
  type: AcademicType,
  start: string,
  end: string | null,
  extra: Partial<AcademicEvent> = {},
): AcademicEvent {
  return {
    id: `ac:${id}`,
    title,
    type,
    start,
    end,
    allDay: !start.includes("T"),
    target: "재학생 전체",
    appliesToMe: true,
    status: "confirmed",
    source: "전남대 학사일정",
    sourceUrl: HAKSA,
    evidence: "",
    confidence: 0.93,
    reminders: [7, 3, 1],
    memo: "",
    ...extra,
  };
}

export const DEMO_SEMESTER = "2026-2";
export const DEMO_SEMESTERS = ["2026-2", "2026-1"] as const;

export const demoAcademic: AcademicEvent[] = [
  ev("2026-2-register", "2026학년도 2학기 수강신청", "register", "2026-08-05T10:00", "2026-08-07T17:00", {
    source: "학사공지",
    sourceUrl: NOTICE,
    evidence: "수강신청은 8월 5일(화) 10:00부터 7일(목) 17:00까지",
    confidence: 0.88,
  }),
  ev("2026-2-tuition", "등록금 납부 기간", "payment", "2026-08-24", "2026-08-28", {
    evidence: "납부기간: 2026. 8. 24.(월) ~ 8. 28.(금)",
    changedFrom: "2026-08-24 ~ 2026-08-26",
  }),
  ev("2026-2-start", "2학기 개강", "semester", "2026-09-01", null, { evidence: "2학기 개강 9. 1.(화)" }),
  ev("2026-2-leave", "휴·복학 신청 기간", "leave", "2026-09-01", "2026-09-05", {
    target: "공과대학 재학생",
    appliesToMe: false,
    source: "공과대학",
    evidence: "공과대학 휴·복학 신청: 9. 1. ~ 9. 5.",
  }),
  ev("2026-2-change", "수강 정정 기간", "register", "2026-09-02", "2026-09-08", { evidence: "수강정정 9. 2.(수) ~ 9. 8.(화)" }),
  ev("2026-2-chuseok", "추석 연휴", "holiday", "2026-09-24", "2026-09-26", { evidence: "추석 9. 24. ~ 9. 26. (휴업)", reminders: [] }),
  ev("2026-2-grade-objection", "1학기 성적 이의신청", "grade", "2026-09-28", "2026-09-30", {
    source: "학사공지",
    sourceUrl: NOTICE,
    evidence: "성적 이의신청 기간: 9. 28.(월) ~ 9. 30.(수)",
    confidence: 0.81,
  }),
  ev("2026-2-withdraw", "수강 철회 기간", "register", "2026-10-05", "2026-10-07", { evidence: "수강철회 10. 5. ~ 10. 7." }),
  ev("2026-2-midterm", "중간고사", "exam", "2026-10-19", "2026-10-23", { evidence: "중간시험 10. 19.(월) ~ 10. 23.(금)" }),
  ev("2026-2-winter", "동계 계절학기 수강신청", "register", "2026-11-23", "2026-11-25", { reminders: [3, 1] }),
  ev("2026-2-final", "기말고사", "exam", "2026-12-14", "2026-12-18", { evidence: "기말시험 12. 14.(월) ~ 12. 18.(금)" }),
  ev("2026-2-end", "2학기 종강", "semester", "2026-12-19", null),
  // 확인 필요 — 공지에서 추출했고 신뢰도가 낮다
  ev("2027-1-leave", "2027학년도 1학기 휴·복학 신청", "leave", "2026-12-28", "2027-01-08", {
    status: "review",
    source: "학사공지",
    sourceUrl: NOTICE,
    evidence: "2027-1학기 휴·복학 신청은 12월 28일부터 1월 8일까지 받습니다",
    confidence: 0.62,
    appliesToMe: null,
  }),
  ev("2026-2-double-major", "복수전공 신청", "register", "2026-11-09T09:00", "2026-11-13T18:00", {
    status: "review",
    source: "학사공지",
    sourceUrl: NOTICE,
    evidence: "복수(부)전공 신청: 11. 9.(월) 09:00 ~ 11. 13.(금) 18:00",
    confidence: 0.71,
  }),
  ev("2026-2-teaching", "교직과정 이수 예정자 신청", "etc", "2026-10-12", "2026-10-16", {
    status: "review",
    source: "학사공지",
    sourceUrl: NOTICE,
    evidence: "교직과정 이수예정자 선발 신청 (10월 중순 예정)",
    confidence: 0.41,
    appliesToMe: null,
  }),
  // 숨김
  ev("2026-2-grad-thesis", "학위청구논문 제출", "etc", "2026-11-02", "2026-11-06", {
    status: "hidden",
    target: "대학원생",
    appliesToMe: false,
  }),
  ev("2026-2-teacher-exam", "교원임용 설명회", "etc", "2026-09-17", null, { status: "hidden", appliesToMe: false }),
];
