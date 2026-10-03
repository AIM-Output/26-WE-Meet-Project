import type { AcademicEvent, AcademicOverview, AcademicPatch } from "./academic";
import type { AssignmentList, AssignmentView, EclassSource, FeedItem, FeedList, FeedSettings, FeedSummary, LoginJob, ReminderSettings } from "./assignments";
import type {
  AttAlert,
  AttCourse,
  Attendance,
  AttendanceOverview,
  AttSession,
  CourseSettings,
  Meeting,
  MutationResult,
  PeriodView,
  SemesterInfo,
  SessionPatch,
  TimetableImportState,
} from "./attendance";
import type {
  Assumptions,
  CategoryView,
  CertState,
  CourseInput,
  CoursePatch,
  CurriculumState,
  GradCert,
  GradImportState,
  GraduationStatus,
  Plan,
  RulesetDoc,
  RulesetListItem,
  RulesetView,
  SimSide,
} from "./graduation";
import type {
  CourseExamSetting,
  DayDetail,
  Difficulty,
  Exam,
  ExamPeriods,
  ExamDetail,
  ExamInput,
  ExamsOverview,
  PlanDay,
  PlanOptionsInput,
  PlanPreview,
  StudyPlan,
  SyncNotices,
  TodayBlock,
} from "./exams";
import type { MaterialDetail, MaterialItem, MaterialKind, MaterialsOverview, MaterialsStatus, MaterialScan } from "./materials";
import type { DeptEntry, ImportState, JobState, MasterSummary, ProfileDoc, ProfilePatch } from "./profile";
import type { AcademicSchedule, AcademicSync, CalEvent, Course, NotificationList, SourceRowApi, SourcesResponse, Status, SyncState, UserEventInput } from "./types";

// 개발 중에는 next.config.ts 의 rewrites 가 /api → 127.0.0.1:8000 으로 넘기고,
// 정적 export 를 FastAPI 가 서빙할 때는 같은 origin 이라 그대로 /api 가 통한다.
const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : `${res.status} ${JSON.stringify(detail)}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const enc = encodeURIComponent;
const json = (method: string, body?: unknown): RequestInit => ({ method, body: body === undefined ? undefined : JSON.stringify(body) });

export const api = {
  events: () => req<CalEvent[]>("/events"),
  courses: () => req<Course[]>("/courses"),
  status: () => req<Status>("/status"),
  createEvent: (body: UserEventInput) => req<CalEvent>("/events", json("POST", body)),
  updateEvent: (id: string, body: Partial<UserEventInput>) => req<CalEvent>(`/events/${enc(id)}`, json("PATCH", body)),
  deleteEvent: (id: string) => req<void>(`/events/${enc(id)}`, { method: "DELETE" }),
  startSync: () => req<SyncState>("/sync", { method: "POST" }),

  // F6 과제·마감 (Frontend-Route 11-8) — 목록은 /api/events 의 deadline 을 그대로 쓰고, 바꾸는 요청만 여기로.
  assignments: (tab?: "open" | "done" | "past") => req<AssignmentList>(`/assignments${tab ? `?tab=${tab}` : ""}`),
  assignment: (id: string) => req<AssignmentView>(`/assignments/${enc(id)}`),
  /** userDone = 내가 체크함 · estimatedHours = 소요시간(null 이면 기본값으로) */
  patchAssignment: (id: string, body: { userDone?: boolean; estimatedHours?: number | null }) =>
    req<{ assignment: AssignmentView; event: CalEvent | null }>(`/assignments/${enc(id)}`, json("PATCH", body)),
  migrateAssignments: (body: { userDone: Record<string, boolean>; estimates: Record<string, number> }) =>
    req<{ userDone: number; estimates: number; unmatched: number }>("/assignments/legacy", json("POST", body)),
  reminderSettings: () => req<ReminderSettings>("/assignments/settings"),
  putReminderSettings: (reminders: string[]) => req<ReminderSettings>("/assignments/settings", json("PUT", { reminders })),
  eclassSource: () => req<EclassSource>("/sources/eclass"),
  /** intervalHours = 주기(작업 스케줄러 재등록) · scheduled = 예약 켜기/끄기 */
  patchEclassSource: (body: { intervalHours?: number; scheduled?: boolean }) => req<EclassSource>("/sources/eclass", json("PATCH", body)),
  /** 로그인 창(C3) — 이 PC 화면에 브라우저 창이 뜬다. 로그인되면 바로 수집한다. */
  startLogin: () => req<LoginJob>("/sync/login", json("POST", { thenSync: true })),
  // E클래스 새 글·자료 (공지 · 자료실 글 · 강의자료) — 수집기가 받아 둔 것에서 만든다
  eclassFeed: () => req<FeedList>("/eclass/feed"),
  eclassFeedItem: (id: string) => req<FeedItem>(`/eclass/feed/${enc(id)}`),
  readFeed: (body: { ids?: string[]; read?: boolean; all?: boolean }) => req<FeedSummary & { updated: number }>("/eclass/feed/read", json("POST", body)),
  feedSettings: () => req<FeedSettings>("/eclass/feed/settings"),
  putFeedSettings: (body: Partial<FeedSettings>) => req<FeedSettings>("/eclass/feed/settings", json("PUT", body)),

  // F1 학사일정 (Frontend-Route 6-9)
  academic: () => req<AcademicOverview>("/academic/events"),
  updateAcademic: (id: string, body: AcademicPatch) => req<AcademicEvent>(`/academic/events/${enc(id)}`, json("PATCH", body)),
  academicSettings: () => req<{ alertTime: string; defaults: Record<string, string[]> }>("/academic/settings"),
  putAcademicSettings: (alertTime: string) =>
    req<{ alertTime: string; defaults: Record<string, string[]> }>("/academic/settings", json("PUT", { alertTime })),

  // 학사 수집 원천 4곳 — key=academic 이면 켜진 원천 전부
  sources: () => req<SourcesResponse>("/sources"),
  syncSource: (key: string) => req<AcademicSync>(`/sources/${enc(key)}/sync`, { method: "POST" }),
  /** 예약 수집(매일 08:00 + 실패 재시도) 켜고 끄기 — 작업 스케줄러 등록/해제 */
  setAcademicSchedule: (enabled: boolean) => req<AcademicSchedule>("/sources/academic/schedule", json("POST", { enabled })),
  /** 신규 묶음 '전체 확인' → 날짜순 목록으로 */
  ackNewAcademic: () => req<{ ok: boolean }>("/academic/new/ack", { method: "POST" }),
  /** enabled = 켜고 끄기 · overrideUrl = ③·④ 게시판 직접 지정 (null 이면 자동으로) */
  patchSource: (key: string, body: { enabled?: boolean; overrideUrl?: string | null }) =>
    req<SourceRowApi>(`/sources/${enc(key)}`, json("PATCH", body)),

  // 알림 (헤더 종)
  notifications: () => req<NotificationList>("/notifications"),
  readNotification: (id: string) => req<{ updated: boolean }>(`/notifications/${enc(id)}/read`, { method: "POST" }),
  readAllNotifications: () => req<{ updated: number }>("/notifications/read-all", { method: "POST" }),

  // C2 프로필·학과 마스터 (Frontend-Route 5-6)
  profile: () => req<ProfileDoc>("/profile"),
  patchProfile: (p: ProfilePatch) => req<ProfileDoc>("/profile", json("PATCH", p)),
  deleteProfile: () => req<void>("/profile", { method: "DELETE" }),
  deleteSensitive: () => req<ProfileDoc>("/profile/sensitive", { method: "DELETE" }),
  migrateProfile: (legacy: unknown) => req<ProfileDoc & { migration: { migrated: boolean; dropped?: string[] } }>("/profile/legacy", json("POST", legacy)),
  importState: () => req<ImportState>("/profile/import"),
  /** 학사정보시스템 가져오기 시작. 로그인 기록이 없으면 409 → { conflict } */
  startImport: async (interactive = false): Promise<ImportState | { conflict: string; needLogin: boolean }> => {
    const res = await fetch(`${BASE}/profile/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interactive }),
      cache: "no-store",
    });
    const body = await res.json().catch(() => ({}));
    if (res.status === 409) return { conflict: body.detail ?? "가져올 수 없습니다", needLogin: !!body.needLogin };
    if (!res.ok) throw new Error(body.detail ?? res.statusText);
    return body as ImportState;
  },
  // F2 졸업요건 (Frontend-Route 7-7) — 계산은 전부 백엔드. 바꾸는 요청은 다시 계산한 status 를 같이 돌려준다.
  graduation: (track?: string) => req<GraduationStatus>(`/graduation/status${track ? `?track=${enc(track)}` : ""}`),
  addGradCourse: (body: CourseInput, track?: string) =>
    req<{ id: string; status: GraduationStatus }>(`/graduation/courses${track ? `?track=${enc(track)}` : ""}`, json("POST", body)),
  patchGradCourse: (id: string, body: CoursePatch, track?: string) =>
    req<{ source: string; mapped: { raw: string; area: string } | null; status: GraduationStatus }>(
      `/graduation/courses/${enc(id)}${track ? `?track=${enc(track)}` : ""}`,
      json("PATCH", body),
    ),
  deleteGradCourse: (id: string) => req<void>(`/graduation/courses/${enc(id)}`, { method: "DELETE" }),
  gradImportState: () => req<GradImportState>("/graduation/sync"),
  /** 기이수성적 가져오기 시작. 로그인 기록이 없으면 409 → { conflict } */
  startGradImport: async (interactive = false): Promise<GradImportState | { conflict: string; needLogin: boolean }> => {
    const res = await fetch(`${BASE}/graduation/sync`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ interactive }),
      cache: "no-store",
    });
    const body = await res.json().catch(() => ({}));
    if (res.status === 409) return { conflict: body.detail ?? "가져올 수 없습니다", needLogin: !!body.needLogin };
    if (!res.ok) throw new Error(body.detail ?? res.statusText);
    return body as GradImportState;
  },
  simulate: (track: string, assumptions: Assumptions) =>
    req<{ current: SimSide; assumed: SimSide; assumptions: Assumptions }>("/graduation/simulate", json("POST", { track, assumptions })),
  ruleset: (q: { year?: number | null; track?: string } = {}) => {
    const p = new URLSearchParams();
    if (q.year) p.set("year", String(q.year));
    if (q.track) p.set("track", q.track);
    const qs = p.toString();
    return req<RulesetView>(`/graduation/ruleset${qs ? `?${qs}` : ""}`);
  },
  putRuleset: (ruleset: RulesetDoc, target: { admissionYear?: number | null; track: string }) =>
    req<RulesetView>("/graduation/ruleset", json("PUT", { ruleset, track: target.track, target: { admissionYear: target.admissionYear, track: target.track } })),
  resetRuleset: (q: { year?: number | null; track?: string }) => {
    const p = new URLSearchParams();
    if (q.year) p.set("year", String(q.year));
    if (q.track) p.set("track", q.track);
    return req<RulesetView>(`/graduation/ruleset?${p.toString()}`, { method: "DELETE" });
  },
  rulesets: () => req<RulesetListItem[]>("/graduation/rulesets"),
  rulesetById: (id: string) => req<RulesetDoc>(`/graduation/rulesets/${enc(id)}`),
  categories: () => req<CategoryView>("/graduation/categories"),
  putCategory: (raw: string, area: string | null) => req<CategoryView>("/graduation/categories", json("PUT", { raw, area })),
  setCert: (key: string, body: { state?: CertState; memo?: string }) => req<Pick<GradCert, "key" | "state" | "memo" | "updatedAt">>(`/graduation/certifications/${enc(key)}`, json("PATCH", body)),
  plans: () => req<Plan[]>("/graduation/plans"),
  savePlan: (body: { name: string; track: string; assumptions: Assumptions }) => req<Plan>("/graduation/plans", json("POST", body)),
  deletePlan: (id: string) => req<void>(`/graduation/plans/${enc(id)}`, { method: "DELETE" }),
  curriculum: () => req<CurriculumState>("/graduation/curriculum"),
  syncCurriculum: () => req<CurriculumState["sync"]>("/graduation/curriculum/sync", { method: "POST" }),

  // F4 강의자료 (Frontend-Route 9-8) — 1차는 자료 목록·원문 열기까지. 파일은 서버가 스트림으로 준다(밖으로 안 나간다).
  materials: (q: { course?: string | null; kind?: MaterialKind | null; q?: string; force?: boolean } = {}) => {
    const p = new URLSearchParams();
    if (q.course) p.set("course", q.course);
    if (q.kind) p.set("kind", q.kind);
    if (q.q) p.set("q", q.q);
    if (q.force) p.set("force", "1");
    const qs = p.toString();
    return req<MaterialsOverview>(`/materials${qs ? `?${qs}` : ""}`);
  },
  materialsStatus: () => req<MaterialsStatus & { scan: MaterialScan; source: MaterialsOverview["source"] }>("/materials/status"),
  /** 수집 폴더를 다시 훑는다. force = 쪽수·해시까지 다시 읽기 (파일을 밖에서 바꿨을 때) */
  rescanMaterials: (force = false) => req<MaterialsOverview>(`/materials/scan${force ? "?force=1" : ""}`, { method: "POST" }),
  material: (id: string) => req<MaterialDetail>(`/materials/${enc(id)}`),
  deleteMaterial: (id: string) => req<{ deleted: string; title: string; updatedAt: string | null }>(`/materials/${enc(id)}`, { method: "DELETE" }),
  /** 직접 추가 — 본문이 파일 그대로다(백엔드에 python-multipart 를 깔지 않으려고, F4 api.py 머리 주석) */
  uploadMaterial: async (courseId: string, file: File): Promise<MaterialItem> => {
    const res = await fetch(`${BASE}/materials?course=${enc(courseId)}&name=${enc(file.name)}`, {
      method: "POST",
      body: file,
      headers: { "Content-Type": file.type || "application/octet-stream" },
      cache: "no-store",
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(body.detail ?? res.statusText);
    return (body as { material: MaterialItem }).material;
  },

  // F3 출결 (Frontend-Route 8-7) — 바꾸는 요청은 다시 계산한 과목(course)과 새로 생긴 경고(alerts)를 같이 돌려준다.
  attendance: (semester?: string) => req<AttendanceOverview>(`/attendance/summary${semester ? `?semester=${enc(semester)}` : ""}`),
  patchSession: (id: string, body: SessionPatch & { memo?: string }) =>
    req<MutationResult & { session: AttSession | null }>(`/attendance/sessions/${enc(id)}`, json("PATCH", body)),
  bulkAttendance: (items: { id: string; attendance: Attendance }[]) =>
    req<{ updated: number; skipped: { id: string; reason: string }[]; courses: AttCourse[]; alerts: AttAlert[]; updatedAt: string | null }>(
      "/attendance/sessions/bulk",
      json("POST", { items }),
    ),
  addMakeup: (body: { courseId: string; date: string; periods: number[]; memo?: string }, semester?: string) =>
    req<MutationResult & { id: string }>(`/attendance/sessions${semester ? `?semester=${enc(semester)}` : ""}`, json("POST", body)),
  deleteMakeup: (id: string) => req<{ course: AttCourse; updatedAt: string | null }>(`/attendance/sessions/${enc(id)}`, { method: "DELETE" }),
  patchAttCourse: (
    id: string,
    body: Partial<CourseSettings> & { adjust?: { absent?: number; late?: number }; excluded?: boolean; name?: string; code?: string; section?: string },
    semester?: string,
  ) => req<MutationResult>(`/attendance/courses/${enc(id)}${semester ? `?semester=${enc(semester)}` : ""}`, json("PATCH", body)),
  addAttCourse: (body: { name: string; code?: string; section?: string; meetings?: Meeting[] }, semester?: string) =>
    req<{ id: string; course: AttCourse }>(`/attendance/courses${semester ? `?semester=${enc(semester)}` : ""}`, json("POST", body)),
  deleteAttCourse: (id: string, semester?: string) =>
    req<void>(`/attendance/courses/${enc(id)}${semester ? `?semester=${enc(semester)}` : ""}`, { method: "DELETE" }),
  putTimetable: (body: { semester?: string; validFrom?: string | null; courses: { courseId: string; meetings: Meeting[] }[] }) =>
    req<{
      generated: { courseId: string; name: string; sessions: number; total: number; orphans: number; text: string }[];
      courses: AttCourse[];
      alerts: AttAlert[];
      updatedAt: string | null;
    }>("/attendance/timetable", json("PUT", body)),
  revertTimetable: (courseId: string, semester?: string) =>
    req<{ courses: AttCourse[] }>(`/attendance/timetable/${enc(courseId)}${semester ? `?semester=${enc(semester)}` : ""}`, { method: "DELETE" }),
  startTimetableImport: (semester?: string) => req<TimetableImportState>("/attendance/timetable/import", json("POST", { semester })),
  timetableImportState: () => req<TimetableImportState>("/attendance/timetable/import"),
  putAttSemester: (body: { semester: string; start?: string | null; end?: string | null; holidays?: { date: string; name: string }[] }) =>
    req<SemesterInfo>("/attendance/semester", json("PUT", body)),
  putPeriods: (body: { mwf?: Record<string, [string, string]>; tt?: Record<string, [string, string]> }) => req<PeriodView>("/attendance/periods", json("PUT", body)),
  resetPeriods: () => req<PeriodView>("/attendance/periods", { method: "DELETE" }),

  // F5 시험 공부 일정 (Frontend-Route 10-7) — 미리보기와 등록을 나눈다: preview 는 계산만, 등록만 캘린더를 바꾼다.
  exams: (q: { semester?: string | null; sync?: boolean } = {}) => {
    const p = new URLSearchParams();
    if (q.semester) p.set("semester", q.semester);
    if (q.sync) p.set("sync", "1");
    const qs = p.toString();
    return req<ExamsOverview>(`/exams${qs ? `?${qs}` : ""}`);
  },
  exam: (id: string) => req<ExamDetail>(`/exams/${enc(id)}`),
  examsToday: () => req<TodayBlock>("/exams/today"),
  /** 난이도 시간 설정 (2026-10-02) — 쪽당 분. 값이 null 이면 기본값으로 */
  putExamSettings: (difficulty: Partial<Record<Difficulty, number | null>>) =>
    req<{ difficulties: ExamsOverview["difficulties"]; updatedAt: string | null }>("/exams/settings", json("PUT", { difficulty })),
  /** 과목별 시험 유무 — 모든 과목은 중간·기말을 본다고 둔다. 안 보는 과목은 끈다 */
  examCourses: () => req<{ courses: CourseExamSetting[]; periods: ExamPeriods; hints: string[]; updatedAt: string | null }>("/exams/courses"),
  patchExamCourse: (courseId: string, body: { midterm?: boolean; final?: boolean }) =>
    req<{
      course: CourseExamSetting | null;
      setting: { midterm: boolean; final: boolean };
      created: { label: string; date: string; time: string }[];
      removed: { label: string }[];
      updatedAt: string | null;
    }>(`/exams/courses/${enc(courseId)}`, json("PATCH", body)),
  /** e클래스 공지에서 시험 다시 찾기 (F5-R01). 파일을 새로 받지는 않는다 — 수집은 F6 */
  syncExams: () => req<SyncNotices>("/exams/sync", { method: "POST" }),
  addExam: (body: ExamInput) => req<{ exam: Exam; updatedAt: string | null }>("/exams", json("POST", body)),
  /** 승인·수정 — 손대면 재수집이 덮어쓰지 않는다 (F5-R03) */
  patchExam: (id: string, body: Partial<ExamInput> & { status?: "confirmed" | "review" }) =>
    req<{ exam: Exam; updatedAt: string | null }>(`/exams/${enc(id)}`, json("PATCH", body)),
  deleteExam: (id: string) =>
    req<{ deleted: string; plansRemoved: number; note: string; updatedAt: string | null }>(`/exams/${enc(id)}`, { method: "DELETE" }),
  /** 계획 계산만 — 저장하지 않는다 (F5-R30). 조정안은 `apply` 를 그대로 넘겨 다시 부른다 */
  previewPlan: (examId: string, options: PlanOptionsInput & { apply?: PlanOptionsInput } = {}) =>
    req<PlanPreview>("/study-plans/preview", json("POST", { examId, ...options })),
  /** 미리보기를 캘린더에 등록 — 학습 블록(kind=study)이 생긴다 (F5-R31) */
  createPlan: (examId: string, options: PlanOptionsInput & { keepDone?: boolean } = {}) =>
    req<{ plan: StudyPlan; exam: Exam; verdict: string; verdictLabel: string; warnings: PlanPreview["warnings"]; message: string; updatedAt: string | null }>(
      "/study-plans",
      json("POST", { examId, ...options }),
    ),
  plan: (id: string) => req<StudyPlan & { exam: Exam; materials: DayDetail["materials"] }>(`/study-plans/${enc(id)}`),
  /** 완료 체크 {done} · 다른 날로 옮기기 {date} (F5-R32·R33) */
  patchPlanDay: (planId: string, date: string, body: { done?: boolean; date?: string }) =>
    req<{ plan: StudyPlan; day: PlanDay | null; exam: Exam; updatedAt: string | null }>(
      `/study-plans/${enc(planId)}/days/${enc(date)}`,
      json("PATCH", body),
    ),
  planDay: (planId: string, date: string) => req<DayDetail>(`/study-plans/${enc(planId)}/days/${enc(date)}`),
  /** 재조정 — 미리보기만 돌려준다. 확인해야 캘린더가 바뀐다 (F5-R34) */
  rebalancePlan: (planId: string, options: PlanOptionsInput = {}) =>
    req<PlanPreview>(`/study-plans/${enc(planId)}/rebalance`, json("POST", options)),
  /** 계획 취소 — 미완료 블록만 지운다 (F5-R35) */
  cancelPlan: (planId: string) =>
    req<{ canceled: string; blocksRemoved: number; blocksKept: number; message: string; updatedAt: string | null }>(
      `/study-plans/${enc(planId)}`,
      { method: "DELETE" },
    ),

  departments: () => req<MasterSummary & { entries: DeptEntry[] }>("/master/departments"),
  syncDepartments: () => req<JobState>("/master/departments/sync", { method: "POST" }),
  masterStatus: () => req<MasterSummary & { sync: JobState & { result: { colleges: number; count: number; year: number } | null } }>("/master/status"),
};
