// F4 강의자료 예시 — Frontend-Route 9절. 요약·문제·답변은 모두 citations(근거 쪽수)를 달고 온다.

export type MaterialState = "ready" | "indexing" | "queued" | "failed" | "notext";

export interface Material {
  id: string; // mt:…
  courseId: string;
  name: string;
  pages: number | null;
  origin: "eclass" | "upload";
  state: MaterialState;
  progress?: [number, number];
  week: number;
}

export interface Citation {
  file: string;
  fileName: string;
  page: number;
  quote?: string;
}

export interface SummaryCard {
  fileId: string;
  fileName: string;
  sections: { heading: string; points: { text: string; cites: Citation[] }[] }[];
  meta: string;
}

export interface Question {
  id: string;
  n: number;
  type: "객관식" | "단답" | "서술";
  text: string;
  choices?: string[];
  answer: string;
  explain: string;
  cites: Citation[];
}

const SE = "74261";
const c = (file: string, fileName: string, page: number, quote?: string): Citation => ({ file, fileName, page, quote });

export const demoMaterials: Material[] = [
  { id: "mt:se11", courseId: SE, name: "1-1 Course Introduction.pdf", pages: 13, origin: "eclass", state: "ready", week: 1 },
  { id: "mt:se12", courseId: SE, name: "1-2 SE Overview.pdf", pages: 35, origin: "eclass", state: "ready", week: 1 },
  { id: "mt:se21", courseId: SE, name: "2-1 소프트웨어품질1.pdf", pages: 38, origin: "eclass", state: "ready", week: 2 },
  { id: "mt:se22", courseId: SE, name: "2-2 소프트웨어품질2.pdf", pages: 48, origin: "eclass", state: "indexing", progress: [2, 7], week: 2 },
  { id: "mt:se31", courseId: SE, name: "3-1 전통적인 개발 프로세스.pdf", pages: 65, origin: "eclass", state: "queued", week: 3 },
  { id: "mt:se-up1", courseId: SE, name: "3주차 보충자료.pdf", pages: 21, origin: "upload", state: "ready", week: 3 },
  { id: "mt:se-up2", courseId: SE, name: "스캔본_필기.pdf", pages: null, origin: "upload", state: "notext", week: 3 },
];

/** 과목별 자료 수 (목록 화면용 예시) */
export const demoMaterialCounts: Record<string, { files: number; ready: number }> = {
  "74245": { files: 4, ready: 4 },
  "74259": { files: 5, ready: 3 },
  "74261": { files: 7, ready: 4 },
  "74926": { files: 0, ready: 0 },
  "75381": { files: 4, ready: 2 },
  "78566": { files: 0, ready: 0 },
  "78570": { files: 1, ready: 1 },
};

export const demoSummaries: SummaryCard[] = [
  {
    fileId: "mt:se21",
    fileName: "2-1 소프트웨어품질1",
    meta: "모델 · 프롬프트 v1 · 9/25",
    sections: [
      {
        heading: "소프트웨어 품질의 정의",
        points: [
          { text: "품질은 명세 충족도와 사용자 기대의 교집합이다", cites: [c("mt:se21", "2-1 소프트웨어품질1", 4), c("mt:se21", "2-1 소프트웨어품질1", 6)] },
          { text: "ISO 9126 은 6가지 품질 특성을 정의한다", cites: [c("mt:se21", "2-1 소프트웨어품질1", 11, "기능성, 신뢰성, 사용성, 효율성, 유지보수성, 이식성")] },
        ],
      },
      {
        heading: "핵심 용어",
        points: [
          { text: "검증(Verification) — 제품을 올바르게 만들고 있는가", cites: [c("mt:se21", "2-1 소프트웨어품질1", 18)] },
          { text: "확인(Validation) — 올바른 제품을 만들고 있는가", cites: [c("mt:se21", "2-1 소프트웨어품질1", 18)] },
        ],
      },
    ],
  },
];

export const demoQuestions: Question[] = [
  {
    id: "q1",
    n: 1,
    type: "객관식",
    text: "ISO 9126 이 정의한 품질 특성이 아닌 것은?",
    choices: ["기능성", "신뢰성", "확장성", "이식성"],
    answer: "③ 확장성",
    explain: "ISO 9126 의 6가지 특성은 기능성·신뢰성·사용성·효율성·유지보수성·이식성이다.",
    cites: [c("mt:se21", "2-1 소프트웨어품질1", 11)],
  },
  {
    id: "q2",
    n: 2,
    type: "단답",
    text: "'올바른 제품을 만들고 있는가'를 묻는 활동의 이름은?",
    answer: "확인(Validation)",
    explain: "검증은 명세 대비, 확인은 사용자 요구 대비다.",
    cites: [c("mt:se21", "2-1 소프트웨어품질1", 18)],
  },
  {
    id: "q3",
    n: 3,
    type: "서술",
    text: "품질을 '명세 충족도'로만 정의할 때의 한계를 설명하시오.",
    answer: "명세 자체가 사용자 기대를 놓치면 명세를 모두 충족해도 쓸모없는 제품이 될 수 있다.",
    explain: "서술형은 채점하지 않고 모범답안과 비교만 보여 준다.",
    cites: [c("mt:se21", "2-1 소프트웨어품질1", 6)],
  },
];

export const demoAskThread = [
  { role: "user" as const, text: "ISO 9126 품질 특성 6가지가 뭐야?" },
  {
    role: "assistant" as const,
    text: "기능성, 신뢰성, 사용성, 효율성, 유지보수성, 이식성입니다.",
    cites: [c("mt:se21", "2-1 소프트웨어품질1", 11, "기능성, 신뢰성, 사용성, 효율성, 유지보수성, 이식성")],
  },
  { role: "user" as const, text: "이번 주 퀴즈 범위 알려줘" },
  { role: "assistant" as const, text: "자료에서 찾지 못했습니다.", cites: [] },
];
