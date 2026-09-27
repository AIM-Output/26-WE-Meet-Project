// F11·F12·F13 기회 예시 — Frontend-Route 16·17절.
// 판정(시스템)과 진행 상태(사용자)는 서로 다른 축이다.

export type OppTab = "scholarship" | "activity" | "program" | "history";
export type Verdict = "해당" | "확인 필요" | "비해당" | "마감"; // F11
export type Grade = "맞음" | "관련 있음" | "아님"; // F12·F13
export type Progress = "초안 대기" | "승인" | "신청함" | "선정" | "탈락" | "관심 없음";

export interface MatchRow {
  condition: string;
  mine: string | null;
  result: "충족" | "미달" | "모름";
  quote: string;
  page?: string;
  sensitive?: "income" | "region" | "school";
}

export interface Opportunity {
  id: string;
  tab: Exclude<OppTab, "history">;
  title: string;
  org: string;
  amount?: string;
  deadline: string; // YYYY-MM-DD
  verdict?: Verdict;
  grade?: Grade;
  reasonChips?: string[]; // 걸린 태그·키워드, 또는 'LLM 판단'
  unknownReason?: string; // '소득구간 모름'
  progress?: Progress;
  flipped?: boolean; // 내가 바꿈
  saved?: boolean;
  board: string;
  url: string;
  match?: MatchRow[];
  otherConditions?: string[];
  documents?: string[];
  applyHow?: string;
}

const HOME = "https://www.jnu.ac.kr/WebApp/web/HOM/COM/Board/board.aspx?boardID=48";

export const demoOpportunities: Opportunity[] = [
  {
    id: "jnu_home_scholarship:70193",
    tab: "scholarship",
    title: "두을장학재단 제29기 두을장학생",
    org: "두을장학재단",
    amount: "300만원",
    deadline: "2026-10-02",
    verdict: "해당",
    progress: "초안 대기",
    board: "전남대 홈페이지 › 장학안내",
    url: HOME,
    match: [
      { condition: "학년 2~3학년", mine: "3학년", result: "충족", quote: "3학년 이상 재학생", page: "공고문 1쪽" },
      { condition: "평점 3.0 이상", mine: "3.42/4.5", result: "충족", quote: "직전학기 평점 3.0 이상", page: "공고문 1쪽" },
      { condition: "이수 12학점 이상", mine: "18학점", result: "충족", quote: "직전학기 12학점 이상", page: "공고문 1쪽" },
      { condition: "소득구간 8 이하", mine: null, result: "모름", quote: "학자금 지원 8구간 이하", page: "공고문 2쪽", sensitive: "income" },
    ],
    otherConditions: ["타 장학금과 중복 수혜 불가"],
    documents: ["재학증명서", "성적증명서", "신청서(초안 사용)"],
    applyHow: "학사정보시스템 → 장학 → 신청",
  },
  {
    id: "jnu_ai_scholarship:1182",
    tab: "scholarship",
    title: "AI융합대학 성적우수장학",
    org: "AI융합대학",
    amount: "150만원",
    deadline: "2026-10-09",
    verdict: "해당",
    board: "AI융합대학 공지",
    url: HOME,
    match: [
      { condition: "AI융합대학 재학생", mine: "인공지능학부", result: "충족", quote: "본 대학 재학생" },
      { condition: "평점 3.3 이상", mine: "3.42/4.5", result: "충족", quote: "직전학기 평점평균 3.3 이상" },
    ],
    documents: ["신청서"],
    applyHow: "학과 사무실 방문 제출",
  },
  {
    id: "kosaf:2026-2-work",
    tab: "scholarship",
    title: "국가근로장학 2학기",
    org: "한국장학재단",
    deadline: "2026-09-30",
    verdict: "확인 필요",
    unknownReason: "소득구간 모름",
    board: "전남대 홈페이지 › 장학안내",
    url: HOME,
    match: [{ condition: "소득구간 8 이하", mine: null, result: "모름", quote: "학자금 지원구간 8구간 이하", sensitive: "income" }],
  },
  {
    id: "jnu_home_scholarship:70110",
    tab: "scholarship",
    title: "지역인재 육성 장학",
    org: "광주광역시",
    amount: "200만원",
    deadline: "2026-10-15",
    verdict: "확인 필요",
    unknownReason: "거주지역 모름",
    board: "전남대 홈페이지 › 장학안내",
    url: HOME,
    match: [{ condition: "광주 거주 3년 이상", mine: null, result: "모름", quote: "광주광역시 3년 이상 거주자", sensitive: "region" }],
  },
  { id: "s5", tab: "scholarship", title: "의과대학 발전기금 장학", org: "의과대학", deadline: "2026-10-05", verdict: "비해당", board: "전남대 홈페이지 › 장학안내", url: HOME },
  { id: "s6", tab: "scholarship", title: "2026 하계 교환학생 장학", org: "국제협력본부", deadline: "2026-09-10", verdict: "마감", board: "전남대 홈페이지 › 장학안내", url: HOME },
  // F12 대외활동
  { id: "a1", tab: "activity", title: "2026 AI 아이디어 경진대회", org: "AICOSS사업단", deadline: "2026-10-06", grade: "맞음", reasonChips: ["AI·SW", "\"공모전\""], board: "AICOSS 사업단", url: HOME },
  { id: "a2", tab: "activity", title: "SW 해커톤 참가자 모집", org: "정보전산원", deadline: "2026-10-01", grade: "맞음", reasonChips: ["AI·SW"], saved: true, board: "전남대 홈페이지", url: HOME },
  { id: "a3", tab: "activity", title: "창의융합 캠프 수강생 모집", org: "교육혁신본부", deadline: "2026-10-09", grade: "관련 있음", reasonChips: ["LLM 판단"], board: "전남대 홈페이지", url: HOME },
  { id: "a4", tab: "activity", title: "해외 봉사단 단원 모집", org: "학생처", deadline: "2026-10-20", grade: "아님", board: "전남대 홈페이지", url: HOME },
  // F13 사업단
  { id: "p1", tab: "program", title: "AICOSS 산학 프로젝트 참여 학생 모집", org: "AICOSS사업단", deadline: "2026-10-12", grade: "맞음", reasonChips: ["AI·SW", "\"산학\""], board: "AICOSS 사업단", url: HOME },
  { id: "p2", tab: "program", title: "반도체 공정실습 교육생 모집", org: "반도체특성화사업단", deadline: "2026-10-04", grade: "관련 있음", reasonChips: ["\"공정실습\""], board: "우리 학과 산학협력단", url: HOME },
];

export const demoHistory = {
  summary: "2026-1학기 · 신청 5 · 선정 2 · 450만원",
  items: [
    { title: "교내 성적우수장학 (2026-1)", state: "선정" as Progress, amount: "250만원" },
    { title: "두을장학재단 제28기", state: "탈락" as Progress },
    { title: "지역인재 장학 (2026-1)", state: "선정" as Progress, amount: "200만원" },
    { title: "의과대학 발전기금 장학", state: "관심 없음" as Progress },
  ],
};

export const INTEREST_TAGS = ["AI·SW", "공모전·경진대회", "해외연수", "창업", "인턴·채용", "봉사", "자격증·교육", "연구·학회", "문화·예술", "체육"] as const;

export const demoDraft = `## 1. 기본 정보
이름 {{이름}} · 학번 {{학번}} · AI융합대학 인공지능학부 3학년

## 2. 자격 정리
- 직전학기 평점 3.42/4.5, 이수 18학점

## 3. 지원 동기
임베디드 AI 분야 대학원 진학을 목표로 하고 있습니다. 교내 AI 경진대회에 참가하며 {{구체적인 성과}}를 경험했고, …

## 4. 학업 계획
{{다음 학기 학업 계획}}

## 5. 제출 서류
재학증명서, 성적증명서, 신청서
`;
