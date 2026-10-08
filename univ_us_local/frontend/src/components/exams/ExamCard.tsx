"use client";

import { Check, CircleCheck, ExternalLink, ListChecks, Pencil, RotateCcw, Target, Trash2, TriangleAlert } from "lucide-react";
import { Chip, CourseChip, StatusBadge } from "@/components/ui/Chip";
import { ProgressBar, StackedBar } from "@/components/ui/Progress";
import { navigateQuery } from "@/lib/useQueryState";
import { isPrep, pagesText, scopeText, TYPE_TONE, type Exam } from "@/lib/exams";

// 시험 카드 (Frontend-Route 10-3) — D-day · 과목 · 범위 · 진도 · 근거.
// 공지에서 온 시험은 **근거 원문 링크**를 늘 보여 준다 (F5 9절 '신뢰').
// 2026-10-06: 공부 진도 그래프 = 서비스 밖에서 공부했다고 **체크한 자료** + 계획에서 **완료한 블록** (범위 자료 대비).
// 범위를 정하지 않은 시험은 e클래스에 올라온 강의자료 전체가 범위다.
// 2026-10-06: **발표**는 범위·진도 그래프·자료 체크·계획 만들기 없이 '준비 완료' 버튼 하나만 둔다.

export function ExamCard({
  e,
  active,
  busy,
  onConfirm,
  onReady,
  onEdit,
  onDelete,
}: {
  e: Exam;
  active?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  /** 발표 준비 완료 체크·해제 */
  onReady: (ready: boolean) => void;
  onEdit: () => void;
  onDelete: () => void;
}) {
  const prep = isPrep(e);
  const plan = prep ? null : e.plan;
  const st = e.study && e.study.total > 0 ? e.study : null;
  const unit = st?.unit === "files" ? "개" : "쪽";
  const scopeLine = scopeText(e);
  const open = (step: "options" | "preview" | "progress") => navigateQuery({ exam: e.id, step }, "push");

  return (
    <article className={`card p-4 md:p-5 ${active ? "border-primary ring-1 ring-primary" : ""}`}>
      <div className="flex flex-wrap items-start gap-4">
        <div
          className={`num grid w-16 flex-none place-items-center rounded-xl py-2 text-center ${
            e.past ? "bg-surface-3 text-faint" : prep && e.ready ? "bg-ok-soft text-ok-text" : e.soon ? "bg-accent-soft text-accent-text" : "bg-surface-3 text-muted"
          }`}
        >
          <span className="text-[20px] leading-tight font-bold">{e.ddayLabel}</span>
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[16px] font-bold">{e.course}</h3>
            <Chip tone={TYPE_TONE[e.type]} square>
              {e.typeLabel}
            </Chip>
            {prep && e.title && e.title !== e.typeLabel && <span className="text-[14px] text-muted">{e.title}</span>}
            {prep && e.ready && (
              <Chip tone="ok" icon={<CircleCheck aria-hidden />}>
                준비 완료
              </Chip>
            )}
            {e.needsReview && <StatusBadge tone="warn">확인 필요</StatusBadge>}
            {e.isAuto && (
              <Chip dashed title={e.note}>
                임의 일정
              </Chip>
            )}
            {e.changed &&
              (e.changed.kind === "confirmed" ? (
                <Chip tone="ok" square title={`임의로 잡아 둔 ${e.changed.from} 대신 공지의 일정이 들어왔습니다`}>
                  일정 확정
                </Chip>
              ) : (
                <Chip tone="accent" square title={`공지에서 ${e.changed.from} → ${e.changed.to} 로 바뀌었습니다`}>
                  날짜 변경됨
                </Chip>
              ))}
          </div>
          <p className="num mt-1 text-[14px] text-muted">
            {e.date.slice(5).replace("-", "/")}({e.weekday}){" "}
            {e.timeUnknown ? <span className="text-faint">시각 미정</span> : e.time}
            {e.timeFromClass && <span className="text-faint"> (수업 시간)</span>}
            {e.place && ` · ${e.place}`}
          </p>
          {!prep && (
            <p className="mt-1 text-[14px]">
              범위 {scopeLine === "미지정" ? <span className="text-faint">미지정</span> : scopeLine} ·{" "}
              <span className={(e.scope.scopePages ?? e.scope.pages) ? "" : "text-faint"}>{pagesText(e)}</span>
            </p>
          )}
          {e.isAuto && e.note && (
            <p className="mt-2 rounded-lg border border-dashed border-border-strong px-3 py-2 text-[13px] text-muted">
              {e.note}. 공지에서 일정이 나오면 바뀌고, 직접 고칠 수도 있습니다.
            </p>
          )}
          {e.needsReview && e.evidence[0] && (
            <p className="mt-2 rounded-lg bg-surface-2 px-3 py-2 text-[13px] text-muted">
              공지 원문: “{e.evidence[0].quote}”
            </p>
          )}
          {prep ? null : st ? (
            <div className="mt-3 space-y-1.5">
              <div className="flex items-center gap-3">
                <div className="min-w-[160px] flex-1">
                  <StackedBar
                    max={st.total}
                    segments={[
                      { value: st.checked, tone: "primary" },
                      { value: st.planned, tone: plan?.behind ? "accent" : "study" },
                    ]}
                    label={`${e.course} 공부 진도`}
                  />
                </div>
                <span className="num w-10 flex-none text-right text-[13px] font-semibold">{st.percent}%</span>
              </div>
              <p className="num flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
                <span>
                  공부 <b className="font-semibold text-text">{st.done}</b>/{st.total}
                  {unit}
                </span>
                {st.checked > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <i className="size-2 rounded-full bg-primary" aria-hidden />
                    직접 체크 {st.checked}
                    {unit}
                  </span>
                )}
                {st.planned > 0 && (
                  <span className="inline-flex items-center gap-1">
                    <i className={`size-2 rounded-full ${plan?.behind ? "bg-accent" : "bg-study"}`} aria-hidden />
                    계획 {st.planned}
                    {unit}
                  </span>
                )}
                {plan && plan.state === "active" && (
                  <span>
                    계획 진도 {plan.progress.donePages}/{plan.progress.plannedPages}쪽
                  </span>
                )}
                {plan?.behind && (
                  <Chip tone="accent" icon={<TriangleAlert aria-hidden />}>
                    {plan.progress.behindDays ? `${plan.progress.behindDays}일 밀림` : `${plan.progress.behindPages}쪽 밀림`}
                  </Chip>
                )}
                {plan?.state === "done" && (
                  <Chip tone="ok" icon={<Check aria-hidden />}>
                    계획 완료
                  </Chip>
                )}
              </p>
            </div>
          ) : plan && (
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <div className="min-w-[160px] flex-1">
                <ProgressBar
                  value={plan.progress.donePages}
                  max={plan.progress.plannedPages}
                  tone={plan.behind ? "accent" : "study"}
                  label="공부 진도"
                />
              </div>
              <span className="num text-[13px] text-muted">
                진도 {plan.progress.donePages}/{plan.progress.plannedPages}쪽
              </span>
              {plan.behind && (
                <Chip tone="accent" icon={<TriangleAlert aria-hidden />}>
                  {plan.progress.behindDays ? `${plan.progress.behindDays}일 밀림` : `${plan.progress.behindPages}쪽 밀림`}
                </Chip>
              )}
              {plan.state === "done" && (
                <Chip tone="ok" icon={<Check aria-hidden />}>
                  계획 완료
                </Chip>
              )}
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-border pt-3">
        {e.noticeUrl ? (
          <a
            href={e.noticeUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="mr-auto inline-flex items-center gap-1 text-[13px] font-semibold text-primary hover:underline"
          >
            공지 원문 보기
            <ExternalLink className="size-3.5" aria-hidden />
          </a>
        ) : (
          // 임의 일정은 위의 점선 칩이 이미 말한다 — 같은 말을 두 번 하지 않는다
          <span className="mr-auto text-[13px] text-faint">{e.isAuto ? "" : e.sourceLabel}</span>
        )}
        {!prep && (e.scope.files ?? 0) > 0 && (
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => navigateQuery({ study: e.id }, "push")}
            title="서비스 밖에서 공부한 강의자료를 체크합니다"
          >
            <ListChecks aria-hidden />
            자료 체크
          </button>
        )}
        <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="시험 수정" onClick={onEdit} disabled={busy}>
          <Pencil aria-hidden />
        </button>
        <button type="button" className="btn btn-ghost btn-icon btn-sm btn-danger" aria-label="시험 삭제" onClick={onDelete} disabled={busy}>
          <Trash2 aria-hidden />
        </button>
        {e.needsReview ? (
          <button type="button" className="btn btn-primary btn-sm" onClick={onConfirm} disabled={busy}>
            <Check aria-hidden />
            맞아요
          </button>
        ) : prep ? (
          e.ready ? (
            <button type="button" className="btn btn-sm" onClick={() => onReady(false)} disabled={busy} title="준비 완료를 풉니다">
              <RotateCcw aria-hidden />
              준비 완료 취소
            </button>
          ) : e.past ? (
            <span className="text-[13px] text-faint">지난 발표</span>
          ) : (
            <button type="button" className="btn btn-primary btn-sm" onClick={() => onReady(true)} disabled={busy}>
              <Check aria-hidden />
              준비 완료
            </button>
          )
        ) : plan && plan.state === "active" ? (
          <>
            {plan.behind && (
              <button type="button" className="btn btn-sm" onClick={() => open("preview")}>
                재조정
              </button>
            )}
            <button type="button" className="btn btn-primary btn-sm" onClick={() => open("progress")}>
              진도
            </button>
          </>
        ) : e.past ? (
          <span className="text-[13px] text-faint">지난 시험</span>
        ) : (
          <button type="button" className="btn btn-primary btn-sm" onClick={() => open("options")} disabled={busy}>
            <Target aria-hidden />
            계획 만들기
          </button>
        )}
      </div>
    </article>
  );
}

/** 대시보드·목록 위의 '오늘 공부' 한 줄 (F5-S09) */
export function TodayLine({ course, color, text }: { course: string; color: string; text: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <CourseChip name={course} color={color} />
      <span className="num text-[14px]">{text}</span>
    </span>
  );
}
