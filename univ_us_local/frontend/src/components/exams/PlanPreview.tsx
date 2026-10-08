"use client";

import { BookOpen, CalendarPlus, Check } from "lucide-react";
import { Banner } from "@/components/ui/Feedback";
import { Chip } from "@/components/ui/Chip";
import { dayText, hm, type PlanAdjustment, type PlanOptionsInput, type PlanPreview as Preview } from "@/lib/exams";

// 계획 미리보기 (F5-S05 · Frontend-Route 10-4) — **이 화면이 이 기능의 신뢰도를 만든다**.
// 날짜별 분량 표 + 합계 + 경고 + 조정안. 등록하기를 누를 때만 캘린더가 바뀐다 (F5 D3).
// 경고는 색만으로 표시하지 않는다 — 서버가 준 문구를 그대로 쓴다 (F5 9절 '접근성').

const LEVEL_TONE = { error: "danger", warn: "warn", info: "neutral" } as const;

export function PlanPreviewPanel({
  preview,
  registering,
  onAdjust,
  onBack,
  onRegister,
}: {
  preview: Preview;
  registering?: boolean;
  onAdjust: (apply: PlanOptionsInput, adj: PlanAdjustment) => void;
  onBack: () => void;
  onRegister: () => void;
}) {
  const p = preview;
  const rebalancing = !!p.rebalanceOf;
  // 날마다 시간을 직접 정했으면(2026-10-06) 하루 분량이 날마다 다르다 — 범위로 보여 준다
  const r = p.dayRange;
  const uneven = !!r && r.minMinutes !== r.maxMinutes;

  return (
    <div className="space-y-3">
      {p.warnings.map((w) => (
        <Banner key={w.code} tone={LEVEL_TONE[w.level]}>
          {w.message}
        </Banner>
      ))}

      {p.adjustments.length > 0 && (
        <div className="rounded-xl border border-border bg-surface-2 p-3">
          <p className="mb-2 text-[13px] font-semibold text-muted">조정안 — 하나를 고르면 다시 계산합니다</p>
          <ul className="space-y-1.5">
            {p.adjustments.map((a) => (
              <li key={a.key} className="flex flex-wrap items-center gap-2 text-[13px]">
                <button type="button" className="btn btn-sm" onClick={() => onAdjust(a.apply, a)}>
                  {a.label}
                </button>
                <span className="min-w-0 text-muted">{a.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      <dl className="grid grid-cols-2 gap-2 rounded-xl border border-border px-3 py-2 text-[13px] sm:grid-cols-4">
        <Stat label="학습일" value={`${p.studyDays}일`} />
        <Stat
          label="하루 분량"
          value={
            p.unit === "pages"
              ? uneven && r
                ? `${r.minPages}~${r.maxPages}쪽`
                : `${p.dailyPages}쪽`
              : uneven && r
                ? `${hm(r.minMinutes)}~${hm(r.maxMinutes)}`
                : hm(p.dailyMinutes)
          }
        />
        <Stat label="하루 시간" value={uneven && r ? `${hm(r.minMinutes)}~${hm(r.maxMinutes)}` : hm(p.dailyMinutes)} />
        <Stat label="마무리 복습" value={p.reviewDays ? `${p.reviewDays}일` : "없음"} />
      </dl>

      {rebalancing && p.carried.pages > 0 && (
        <p className="text-[13px] text-muted">
          이미 마친 <b className="num font-semibold text-text">{p.carried.pages}쪽</b>은 빼고 남은 분량만 다시 나눴습니다.
        </p>
      )}

      <ul className="divide-y divide-border rounded-xl border border-border" aria-label="날짜별 분량">
        {p.days.map((d) => (
          <li
            key={d.date}
            className={`flex items-center gap-3 px-3 py-2 text-[14px] ${d.kind === "excluded" ? "text-faint" : ""} ${d.done ? "opacity-60" : ""}`}
          >
            <span className="num w-[68px] flex-none font-semibold">
              {d.date.slice(5).replace("-", "/")}({d.weekday})
            </span>
            <span className="flex min-w-0 flex-1 items-center gap-1.5 truncate">
              {d.kind === "review" && <BookOpen className="size-3.5 flex-none text-study" aria-hidden />}
              <span className={d.done ? "line-through" : ""}>{dayText(d)}</span>
              {d.done && <Check className="size-3.5 flex-none text-ok-text" aria-label="완료" />}
              {d.moved && (
                <Chip tone="neutral" square>
                  옮김
                </Chip>
              )}
              {d.pinned && (
                <Chip tone="study" square title="이 날의 공부 시간을 직접 정했습니다">
                  직접
                </Chip>
              )}
            </span>
            {d.kind !== "excluded" && <span className="num flex-none text-muted">{hm(d.minutes)}</span>}
          </li>
        ))}
      </ul>

      <p className="num text-right text-[14px] font-semibold">
        합계 {p.totals.pages > 0 && `${p.totals.pages}쪽 · `}
        {hm(p.totals.minutes)}
        {p.totals.quiz > 0 && ` · 문제 ${p.totals.quiz}개`}
      </p>

      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" className="btn btn-sm" onClick={onBack}>
          다시 계산
        </button>
        <button type="button" className="btn btn-primary btn-sm" onClick={onRegister} disabled={!p.canRegister || registering}>
          <CalendarPlus aria-hidden />
          {registering ? "등록 중…" : rebalancing ? "재조정 적용" : "등록하기"}
        </button>
      </div>
      {p.canRegister && (
        <p className="text-right text-[12px] text-faint">날마다의 분량은 저녁 시간대(기본 19:00~24:00)에 공부 캘린더로 놓입니다.</p>
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
