"use client";

import { Modal } from "@/components/ui/Modal";
import { Banner } from "@/components/ui/Feedback";
import { CourseChip } from "@/components/ui/Chip";
import { Toggle } from "@/components/ui/Layout";
import type { CourseExamRef, CourseExamSetting, ExamPeriods } from "@/lib/exams";

// 과목별 시험 (2026-10-01) — 모든 과목은 중간·기말 2회를 본다고 두고, 시험을 안 보는 과목은 여기서 끈다.
// 일정이 아직 안 나온 시험은 학사일정 수업평가 기간 안의 그 과목 수업 요일로 임의로 잡힌다(서버 defaults.py).
// 퀴즈·발표는 여기서 다루지 않는다 — 공지에서 찾거나 '시험 추가'로 넣는다.

export function CourseExamsModal({
  open,
  rows,
  periods,
  hints,
  busy,
  loading,
  onClose,
  onChange,
}: {
  open: boolean;
  loading?: boolean;
  rows: CourseExamSetting[];
  periods: ExamPeriods | null;
  hints: string[];
  busy?: boolean;
  onClose: () => void;
  onChange: (courseId: string, body: { midterm?: boolean; final?: boolean }) => void;
}) {
  return (
    <Modal open={open} onClose={onClose} title="과목별 시험" size="lg">
      <div className="space-y-4 pt-1 text-[14px]">
        <p className="text-muted">
          모든 과목은 <b className="font-semibold text-text">중간고사·기말고사</b>를 본다고 둡니다. 시험이 없는 과목은 끄세요.
          일정이 아직 안 나온 시험은 학사일정의 수업평가 기간 안에서 <b className="font-semibold text-text">그 과목의 수업 요일</b>로
          임의로 잡고, 공지에서 일정이 나오면 그 자리가 바뀝니다. 기말고사는 그 과목의 중간고사가 끝나면 생깁니다.
        </p>
        {periods?.available && (
          <dl className="grid gap-2 rounded-xl border border-border px-3 py-2 text-[13px] sm:grid-cols-2">
            <div>
              <dt className="text-muted">중간고사를 잡는 기간</dt>
              <dd className="num font-semibold">{periods.midterm.label || "학사일정에 없음"}</dd>
            </div>
            <div>
              <dt className="text-muted">기말고사를 잡는 기간</dt>
              <dd className="num font-semibold">{periods.final.label || "학사일정에 없음"}</dd>
            </div>
          </dl>
        )}
        {hints.map((h) => (
          <Banner key={h} tone="warn">
            {h}
          </Banner>
        ))}

        <ul className="divide-y divide-border rounded-xl border border-border">
          {rows.length === 0 && (
            <li className="px-3 py-6 text-center text-muted">{loading ? "불러오는 중…" : "과목이 없습니다 — e클래스 동기화를 먼저 하세요"}</li>
          )}
          {rows.map((c) => (
            <li key={c.courseId} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3 py-3">
              <span className="min-w-[160px] flex-1">
                <CourseChip name={c.course} color={c.color} />
              </span>
              <ExamSwitch
                course={c.course}
                label="중간고사"
                on={c.midterm}
                exam={c.midtermExam}
                busy={busy}
                onChange={(v) => onChange(c.courseId, { midterm: v })}
              />
              <ExamSwitch course={c.course} label="기말고사" on={c.final} exam={c.finalExam} busy={busy} onChange={(v) => onChange(c.courseId, { final: v })} />
            </li>
          ))}
        </ul>
        <p className="hint">끄면 임의로 잡아 둔 일정만 치웁니다. 공지에서 찾았거나 직접 넣은 시험은 남깁니다.</p>
      </div>
    </Modal>
  );
}

function ExamSwitch({
  course,
  label,
  on,
  exam,
  busy,
  onChange,
}: {
  course: string;
  label: string;
  on: boolean;
  exam: CourseExamRef | null;
  busy?: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <span className="flex w-[200px] items-center gap-2">
      <Toggle checked={on} onChange={onChange} label={`${course} ${label} 봄`} disabled={busy} />
      <span className="min-w-0">
        <span className="block text-[13px] font-semibold">{label}</span>
        <span className="num block truncate text-[12px] text-muted">
          {exam
            ? `${exam.date.slice(5).replace("-", "/")}${exam.time ? ` ${exam.time}` : ""} · ${exam.sourceLabel}`
            : on
              ? label === "기말고사"
                ? "중간고사 뒤에 생깁니다"
                : "아직 없음"
              : "안 봄"}
        </span>
      </span>
    </span>
  );
}
