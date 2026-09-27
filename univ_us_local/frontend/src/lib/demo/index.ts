// 예시 데이터 — 백엔드 API 가 아직 없는 화면(학사일정·알림·프로필·졸업요건·출결·강의자료·시험·기회·팀플·대화·설정)을
// 확인하기 위한 값이다. 화면에는 <DemoNotice /> 띠로 "예시 데이터"임을 늘 표시한다.
// 백엔드가 생기면 lib/api.ts 에 같은 모양의 함수를 만들고, 이 파일을 쓰는 곳을 그쪽으로 바꾼다.
// 문구는 요구사항정의서·Frontend-Route 의 예시 문장을 그대로 따른다.

export * from "./academic";
export * from "./notifications";
export * from "./profile";
export * from "./graduation";
export * from "./attendance";
export * from "./courses";
export * from "./exams";
export * from "./briefing";
export * from "./opportunities";
export * from "./team";
export * from "./chat";
export * from "./sources";
