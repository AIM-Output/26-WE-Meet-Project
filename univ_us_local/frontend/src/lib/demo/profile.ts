// C2 프로필·학과 마스터 예시. 실제 마스터는 교육과정검색 크롤링 결과(departments.json, 61개 단과대).

export interface Department {
  college: string;
  dept: string;
  major: string | null; // 전공 트랙이 없는 학과는 null
  code: string;
}

export const demoDepartments: Department[] = [
  { college: "AI융합대학", dept: "인공지능학부", major: "인공지능전공", code: "30001267" },
  { college: "AI융합대학", dept: "인공지능학부", major: "빅데이터전공", code: "30001268" },
  { college: "AI융합대학", dept: "소프트웨어공학과", major: null, code: "30001270" },
  { college: "공과대학", dept: "전자컴퓨터공학부", major: "컴퓨터정보통신공학전공", code: "30000411" },
  { college: "공과대학", dept: "전자컴퓨터공학부", major: "전자공학전공", code: "30000412" },
  { college: "공과대학", dept: "기계공학부", major: null, code: "30000420" },
  { college: "공과대학", dept: "화학공학부", major: null, code: "30000430" },
  { college: "공과대학", dept: "건축학부", major: "건축공학전공", code: "30000441" },
  { college: "자연과학대학", dept: "수학과", major: null, code: "30000210" },
  { college: "자연과학대학", dept: "통계학과", major: null, code: "30000220" },
  { college: "자연과학대학", dept: "물리학과", major: null, code: "30000230" },
  { college: "경영대학", dept: "경영학부", major: "경영학전공", code: "30000610" },
  { college: "경영대학", dept: "경제학부", major: null, code: "30000620" },
  { college: "인문대학", dept: "국어국문학과", major: null, code: "30000110" },
  { college: "인문대학", dept: "영어영문학과", major: null, code: "30000120" },
  { college: "사회과학대학", dept: "심리학과", major: null, code: "30000710" },
  { college: "사회과학대학", dept: "정치외교학과", major: null, code: "30000720" },
  { college: "생활과학대학", dept: "식품영양과학부", major: null, code: "30000810" },
  { college: "사범대학", dept: "컴퓨터교육과", major: null, code: "30000930" },
  { college: "예술대학", dept: "디자인학과", major: "시각디자인전공", code: "30001010" },
];

export const deptPath = (d: Department) => [d.college, d.dept, d.major].filter(Boolean).join(" › ");

export type Track = "single" | "double" | "minor";
export const TRACK_LABEL: Record<Track, string> = { single: "단일전공", double: "복수전공", minor: "부전공" };

export interface Profile {
  deptCode: string | null;
  admissionYear: number | null;
  track: Track | null;
  grade: number | null; // 학년
  enrollment: "재학" | "휴학" | "졸업유예" | null;
  gpa: number | null;
  credits: number | null;
  semesters: number | null;
  auto: string[]; // 학사시스템에서 자동으로 채운 필드
  edited: string[]; // 자동값을 사용자가 고친 필드
  sensitive: { income: string; region: string; school: string };
  onboardingSkipped: boolean;
}

export const emptyProfile: Profile = {
  deptCode: null,
  admissionYear: null,
  track: null,
  grade: null,
  enrollment: null,
  gpa: null,
  credits: null,
  semesters: null,
  auto: [],
  edited: [],
  sensitive: { income: "", region: "", school: "" },
  onboardingSkipped: false,
};

/** 학사정보시스템 가져오기(로컬 SSO) 예시 결과 */
export const demoImported = { grade: 3, enrollment: "재학" as const, gpa: 3.42, credits: 98, semesters: 5 };

export const isProfileComplete = (p: Profile) => !!(p.deptCode && p.admissionYear && p.track);
