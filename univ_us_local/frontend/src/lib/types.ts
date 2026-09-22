// 백엔드(/api) 와 주고받는 형태. 백엔드 app/main.py 의 Pydantic 모델과 짝이다.

export type CategoryKey = "personal" | "study" | "team" | "etc";

export interface CategoryInfo {
  label: string;
  color: string;
}

export interface Course {
  id: string;
  name: string;
  short: string;
  code: string;
  section: string;
  url: string;
  color: string;
  activityCount: number;
}

export interface DeadlineProps {
  kind: "deadline";
  type: string; // 과제 · 동영상 …
  source: string; // assign · calendar
  due: string; // ISO (로컬)
  course: string;
  courseShort: string;
  courseCode: string;
  courseColor: string;
  status: string;
  submitted: boolean;
  graded: string;
  description: string;
  attachmentCount: number;
  url: string;
}

export interface UserProps {
  kind: "user";
  category: CategoryKey;
  categoryLabel: string;
  color: string;
  memo: string;
  isTodo: boolean; // 할 일 — To Do List 에서 완료 체크
  done: boolean;
}

export interface CalEvent {
  id: string;
  title: string;
  start: string; // ISO (로컬) 또는 YYYY-MM-DD (종일)
  end: string | null; // 종일이면 exclusive 날짜
  allDay: boolean;
  editable: boolean;
  extendedProps: DeadlineProps | UserProps;
}

export interface UserEventInput {
  title: string;
  start: string;
  end: string | null;
  all_day: boolean;
  category: CategoryKey;
  memo: string;
  is_todo: boolean;
  done: boolean;
}

export interface SyncState {
  running: boolean;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null; // 0 성공 · 2 세션 만료 · 3 다른 실행이 진행 중이라 건너뜀 · -1 시간 초과
  source: "button" | "external" | null; // button = 이 서버가 띄움, external = 예약 작업(작업 스케줄러)·수동 실행
  pid: number | null;
  already_running?: boolean; // POST /api/sync: 이미 돌고 있어서 새로 띄우지 않음
  error?: string;
}

export interface Status {
  updated_at: string | null;
  sync: SyncState;
  counts: { courses: number; deadlines: number; userEvents: number; todos: number; todosDone: number };
  categories: Record<CategoryKey, CategoryInfo>;
  eclassDataDir: string;
  log: string[];
}
