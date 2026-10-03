"use client";

import { BookOpen, Check, RotateCcw, Trash2 } from "lucide-react";
import { Banner } from "@/components/ui/Feedback";
import { Chip } from "@/components/ui/Chip";
import { ProgressBar } from "@/components/ui/Progress";
import { dayText, hm, type PlanDay, type StudyPlan } from "@/lib/exams";

// 진도 화면 (F5-S07 · Frontend-Route 10-5) — 계획 대비 완료율 + 밀림 배너 + 재조정 · 계획 취소.
// 재조정은 **미리보기를 다시 열어** 보여 주고, 확인해야 캘린더가 바뀐다 (자동 변경 없음).

export function ProgressPanel({
  plan,
  busy,
  onToggleDay,
  onRebalance,
  onCancel,
}: {
  plan: StudyPlan;
  busy?: boolean;
  onToggleDay: (d: PlanDay) => void;
  onRebalance: () => void;
  onCancel: () => void;
}) {
  const pr = plan.progress;
  const today = new Date().toISOString().slice(0, 10);
  // '오늘까지 계획' 기준선 — 막대 위 세로선으로 그린다
  const marker = pr.plannedPages > 0 ? Math.min(1, (pr.donePages + pr.behindPages) / pr.plannedPages) : undefined;

  return (
    <div className="space-y-3 text-[14px]">
      <ProgressBar
        value={pr.donePages}
        max={pr.plannedPages}
        tone={plan.behind ? "accent" : plan.state === "done" ? "ok" : "study"}
        marker={marker}
        label="공부 진도"
        height={10}
      />
      <p className="num flex flex-wrap items-center gap-x-3 gap-y-1">
        <span>
          완료 <b className="font-semibold">{pr.donePages}</b> / 계획 {pr.plannedPages}쪽 ({pr.percent}%)
        </span>
        <span className="text-muted">
          {pr.doneDays}/{pr.totalDays}일 · 남은 {pr.remainingPages}쪽
        </span>
        {plan.state !== "active" && <Chip tone={plan.state === "done" ? "ok" : "neutral"}>{plan.stateLabel}</Chip>}
      </p>

      {plan.behind && (
        <Banner
          tone="warn"
          action={
            <button type="button" className="btn btn-sm" onClick={onRebalance} disabled={busy}>
              <RotateCcw aria-hidden />
              재조정하기
            </button>
          }
        >
          {plan.behindMessage}
        </Banner>
      )}
      {plan.state === "done" && !plan.behind && <Banner tone="info">이 계획을 다 끝냈습니다 — 예상 문제로 마무리해 보세요.</Banner>}

      <ul className="divide-y divide-border rounded-xl border border-border" aria-label="날짜별 분량과 완료 체크">
        {plan.days.map((d) => {
          const overdue = !d.done && d.date < today;
          return (
            <li key={d.date} className={`flex items-center gap-3 px-3 py-2 ${d.done ? "opacity-60" : ""}`}>
              <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2.5">
                <input
                  type="checkbox"
                  className="size-4 flex-none accent-[var(--study)]"
                  checked={d.done}
                  disabled={busy}
                  onChange={() => onToggleDay(d)}
                  aria-label={`${d.date} ${dayText(d)} 완료`}
                />
                <span className={`num w-[68px] flex-none font-semibold ${overdue ? "text-accent-text" : ""}`}>
                  {d.date.slice(5).replace("-", "/")}({d.weekday})
                </span>
                <span className="flex min-w-0 items-center gap-1.5 truncate">
                  {d.kind === "review" && <BookOpen className="size-3.5 flex-none text-study" aria-hidden />}
                  <span className={d.done ? "line-through" : ""}>{dayText(d)}</span>
                  {d.done && <Check className="size-3.5 flex-none text-ok-text" aria-hidden />}
                  {d.moved && (
                    <Chip tone="neutral" square>
                      옮김
                    </Chip>
                  )}
                  {overdue && (
                    <Chip tone="accent" square>
                      밀림
                    </Chip>
                  )}
                </span>
              </label>
              <span className="num flex-none text-[13px] text-muted">{hm(d.minutes)}</span>
            </li>
          );
        })}
      </ul>

      <dl className="grid grid-cols-3 gap-2 rounded-xl border border-border px-3 py-2 text-[13px]">
        <Stat label="난이도" value={`${plan.difficultyLabel} (${plan.pageMinutes}분/쪽)`} />
        <Stat label="마무리 복습" value={plan.reviewDays ? `${plan.reviewDays}일` : "없음"} />
        <Stat label="제외일" value={plan.excludedDates.length ? `${plan.excludedDates.length}일` : "없음"} />
      </dl>

      {plan.state === "active" && (
        <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
          <button type="button" className="btn btn-sm" onClick={onRebalance} disabled={busy}>
            <RotateCcw aria-hidden />
            남은 날로 다시 나누기
          </button>
          <button type="button" className="btn btn-ghost btn-danger btn-sm" onClick={onCancel} disabled={busy}>
            <Trash2 aria-hidden />
            계획 취소 (완료분은 남김)
          </button>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{label}</dt>
      <dd className="num font-semibold">{value}</dd>
    </div>
  );
}
