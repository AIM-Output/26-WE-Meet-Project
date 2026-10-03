"use client";

import { useMemo, useState } from "react";
import { Modal } from "@/components/ui/Modal";
import { Banner } from "@/components/ui/Feedback";
import { useAppData } from "@/components/app/AppData";
import type { Exam, ExamInput, ExamType } from "@/lib/exams";

// 시험 추가·수정 (F5-S03). 과목·유형·날짜·시각·장소·범위.
// 과목은 **수정할 수 없다**(서버가 422) — 잘못 넣었으면 지우고 새로 넣는다.

const TYPES: { key: ExamType; label: string }[] = [
  { key: "midterm", label: "중간고사" },
  { key: "final", label: "기말고사" },
  { key: "quiz", label: "퀴즈" },
  { key: "presentation", label: "발표" },
  { key: "etc", label: "기타" },
];

export interface ExamFormValue {
  courseId: string;
  type: ExamType;
  date: string;
  time: string;
  place: string;
  weeks: string; // '3-7' 또는 '3,4,5' — 사람이 쓰는 대로 받아 숫자로 바꾼다
  note: string;
}

const empty = (courseId = ""): ExamFormValue => ({ courseId, type: "midterm", date: "", time: "", place: "", weeks: "", note: "" });

function fromExam(e: Exam): ExamFormValue {
  return {
    courseId: e.courseId,
    type: e.type,
    date: e.date,
    time: e.time,
    place: e.place,
    weeks: e.scope.weeks.join(","),
    note: e.scope.note,
  };
}

/** '3-7' · '3,4,5' · '3~7주차' → [3,4,5,6,7] */
export function parseWeeks(raw: string): number[] {
  const out = new Set<number>();
  for (const part of raw.split(",")) {
    const m = part.trim().match(/^(\d{1,2})\s*[-~]\s*(\d{1,2})/);
    if (m) {
      const [a, b] = [Number(m[1]), Number(m[2])];
      if (a <= b) for (let i = a; i <= b; i++) out.add(i);
      continue;
    }
    const one = part.trim().match(/^(\d{1,2})/);
    if (one) out.add(Number(one[1]));
  }
  return [...out].filter((w) => w >= 1 && w <= 30).sort((a, b) => a - b);
}

export function ExamForm(props: {
  open: boolean;
  /** 있으면 수정, 없으면 추가 */
  exam?: Exam | null;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (body: ExamInput, id?: string) => Promise<boolean>;
}) {
  const { courses } = useAppData();
  const { exam, open, onClose } = props;
  return (
    <Modal open={open} onClose={onClose} title={exam ? `${exam.course} 시험 수정` : "시험 추가"}>
      {/* key 로 열릴 때마다 입력값을 새로 잡는다 (EventForm 과 같은 방식) — 효과 안에서 setState 하지 않는다.
          과목 목록은 나중에 도착할 수 있어 key 에 넣는다 — 그래야 첫 과목이 기본값으로 들어간다. */}
      <FormBody key={exam?.id ?? `new:${courses[0]?.id ?? ""}`} {...props} initial={exam ? fromExam(exam) : empty(courses[0]?.id ?? "")} />
    </Modal>
  );
}

function FormBody({
  exam,
  busy,
  onClose,
  onSubmit,
  initial,
}: {
  exam?: Exam | null;
  busy?: boolean;
  onClose: () => void;
  onSubmit: (body: ExamInput, id?: string) => Promise<boolean>;
  initial: ExamFormValue;
}) {
  const { courses } = useAppData();
  const [v, setV] = useState<ExamFormValue>(initial);
  const [error, setError] = useState<string | null>(null);
  const editing = !!exam;

  const set = <K extends keyof ExamFormValue>(k: K, value: ExamFormValue[K]) => setV((p) => ({ ...p, [k]: value }));
  const courseName = useMemo(() => courses.find((c) => c.id === v.courseId)?.short ?? exam?.course ?? "", [courses, v.courseId, exam]);

  const submit = async () => {
    if (!v.courseId) return setError("과목을 고르세요");
    if (!v.date) return setError("시험 날짜를 넣으세요");
    if (v.time && !/^([01]\d|2[0-3]):[0-5]\d$/.test(v.time)) return setError("시각은 HH:MM 으로 넣으세요 (비우면 그 과목 수업 시간으로 넣습니다)");
    const body: ExamInput = {
      courseId: v.courseId,
      type: v.type,
      date: v.date,
      time: v.time,
      place: v.place.trim(),
      scopeWeeks: parseWeeks(v.weeks),
      scopeNote: v.note.trim(),
    };
    if (editing) delete (body as Partial<ExamInput>).courseId; // 과목은 바꿀 수 없다
    if (await onSubmit(body, exam?.id)) onClose();
  };

  return (
    <form
      className="space-y-4 pt-1"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
        {error && <Banner tone="danger">{error}</Banner>}
        {editing && exam!.source === "notice" && (
          <Banner tone="info">공지에서 찾은 시험입니다 — 여기서 고치면 다음 수집이 덮어쓰지 않습니다.</Banner>
        )}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="ex-course">
              과목
            </label>
            {editing ? (
              <input id="ex-course" className="field" value={courseName} disabled readOnly />
            ) : (
              <select id="ex-course" data-autofocus className="field" value={v.courseId} onChange={(ev) => set("courseId", ev.target.value)}>
                {courses.length === 0 && <option value="">과목이 없습니다 — e클래스 동기화 먼저</option>}
                {courses.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.short}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="label" htmlFor="ex-type">
              유형
            </label>
            <select id="ex-type" className="field" value={v.type} onChange={(ev) => set("type", ev.target.value as ExamType)}>
              {TYPES.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.label}
                </option>
              ))}
            </select>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="ex-date">
              날짜
            </label>
            <input id="ex-date" type="date" className="field" value={v.date} onChange={(ev) => set("date", ev.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="ex-time">
              시각 <span className="font-normal text-faint">(비우면 수업 시간)</span>
            </label>
            <input id="ex-time" type="time" className="field" value={v.time} onChange={(ev) => set("time", ev.target.value)} />
          </div>
        </div>
        <div>
          <label className="label" htmlFor="ex-place">
            장소 <span className="font-normal text-faint">(선택)</span>
          </label>
          <input id="ex-place" className="field" placeholder="공7-223" value={v.place} onChange={(ev) => set("place", ev.target.value)} />
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label" htmlFor="ex-weeks">
              범위 주차 <span className="font-normal text-faint">(선택)</span>
            </label>
            <input id="ex-weeks" className="field" placeholder="3-7" value={v.weeks} onChange={(ev) => set("weeks", ev.target.value)} />
            <p className="mt-1 text-[12px] text-faint">주차를 넣으면 그 주 강의자료의 쪽수를 자동으로 셉니다.</p>
          </div>
          <div>
            <label className="label" htmlFor="ex-note">
              범위 메모 <span className="font-normal text-faint">(선택)</span>
            </label>
            <input
              id="ex-note"
              className="field"
              placeholder="10월 15일까지 강의한 내용"
              value={v.note}
              onChange={(ev) => set("note", ev.target.value)}
            />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t border-border pt-4">
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            취소
          </button>
          <button type="submit" className="btn btn-primary" disabled={busy}>
            {editing ? "저장" : "추가"}
          </button>
        </div>
    </form>
  );
}
