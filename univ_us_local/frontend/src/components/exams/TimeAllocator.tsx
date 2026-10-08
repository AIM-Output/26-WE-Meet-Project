"use client";

import { useState } from "react";
import { Check, Minus, Plus, RotateCcw, TriangleAlert } from "lucide-react";
import { clock, hm, parseClock, type PlanAdjustment, type PlanOptionsInput, type PlanPreview } from "@/lib/exams";

// 시간 배치 (2026-10-06 사용자 요청) — 분량·난이도로 나온 **총 공부 시간**을 학습일에 자유롭게 나눈다.
//
// 규칙(서버 plan.allocate 와 같다): 사용자가 손댄 날은 그 시간으로 **고정**되고, 손대지 않은 날(자동)이
// 남은 시간을 고르게 나눠 가진다 → 한 날을 바꾸면 나머지가 따라 움직이고 합계는 늘 총 시간과 같다.
// 모든 날을 고정했는데 모자라거나 넘치면 막대와 문구로 보여 주고, 한 번에 고치는 버튼을 준다.
//
// 서버 계산(250ms 뒤)이 오기 전에도 화면이 바로 따라오도록, 자동인 날은 '남은 시간 ÷ 자동인 날 수'로 먼저 그린다.

const STEP = 30; // ± 버튼 — 30분씩
const SLIDE = 10; // 슬라이더 — 10분 단위
const DAY_MAX = 24 * 60;
const WD = ["일", "월", "화", "수", "목", "금", "토"];

type Row = { date: string; label: string; minutes: number; pages: number; pinned: boolean; max: number };

export function TimeAllocator({
  value,
  preview,
  onChange,
}: {
  value: PlanOptionsInput;
  preview: PlanPreview | null;
  onChange: (patch: PlanOptionsInput) => void;
}) {
  const al = preview?.allocation;
  if (!preview || !al) {
    return <p className="text-[12px] text-faint">{preview ? "이 서버는 시간 배치를 지원하지 않습니다 — 서버를 다시 켜 주세요." : "총 공부 시간을 계산하는 중…"}</p>;
  }
  const dates = preview.studyDates;
  if (!dates.length) return <p className="text-[12px] text-faint">학습일을 먼저 정하세요.</p>;

  const need = al.needMinutes;
  const pm = preview.unit === "pages" ? preview.pageMinutes : 0;
  const inDates = new Set(dates);
  const pins: Record<string, number> = Object.fromEntries(Object.entries(value.dayMinutes ?? {}).filter(([d]) => inDates.has(d)));
  const served = preview.dayMinutes ?? {};
  // 화면의 고정 값과 서버가 계산에 쓴 값이 같으면 서버 숫자(쪽수 포함)를 그대로 쓴다
  const synced = Object.keys(pins).length === Object.keys(served).length && Object.entries(pins).every(([d, m]) => served[d] === m);
  const pinnedSum = Object.values(pins).reduce((a, b) => a + b, 0);
  const autoCount = dates.filter((d) => !(d in pins)).length;
  const estimate = autoCount ? Math.max(0, need - pinnedSum) / autoCount : 0;
  const server = Object.fromEntries(preview.days.filter((d) => d.kind === "study" && !d.done).map((d) => [d.date, d]));

  const rows: Row[] = dates.map((d) => {
    const pinned = d in pins;
    const minutes = pinned ? pins[d] : synced ? (server[d]?.minutes ?? 0) : Math.round(estimate);
    const pages = synced ? (server[d]?.pages ?? 0) : pm ? Math.round(minutes / pm) : 0;
    // 다른 자동인 날이 남아 있으면 그 날들을 0 까지만 밀어낸다(총 시간을 넘길 수 없다). 모두 고정이면 하루 24시간까지.
    const others = pinnedSum - (pins[d] ?? 0);
    const otherAuto = autoCount - (pinned ? 0 : 1);
    const max = otherAuto > 0 ? Math.max(0, need - others) : DAY_MAX;
    return { date: d, label: md(d), minutes, pages, pinned, max: Math.min(max, DAY_MAX) };
  });
  const assigned = rows.reduce((a, r) => a + r.minutes, 0);

  // 상태 — 서버 값이 있으면 서버 판정을, 아직이면 화면 값으로 어림한다(쪽 반올림 오차는 날마다 쪽당 시간만큼 봐준다)
  const slack = pm * rows.length;
  const gap = need - assigned;
  const state: "ok" | "short" | "over" = synced
    ? al.unassignedMinutes > 0
      ? "short"
      : al.overMinutes > 0
        ? "over"
        : "ok"
    : !autoCount && gap > slack
      ? "short"
      : gap < -slack
        ? "over"
        : "ok";
  const fixes: PlanAdjustment[] = synced ? al.fixes : [];

  const set = (r: Row, minutes: number) => {
    const m = Math.min(r.max, Math.max(0, Math.round(minutes)));
    onChange({ dayMinutes: { ...pins, [r.date]: m } });
  };
  const unpin = (d: string) => {
    const next = { ...pins };
    delete next[d];
    onChange({ dayMinutes: next });
  };

  const scale = Math.max(need, assigned, 1);
  // 슬라이더는 모든 줄이 같은 눈금 — 줄끼리 길이를 견줄 수 있게(총 공부 시간이 꽉 찬 끝). 넘는 값은 set 이 잘라 낸다
  const sliderMax = Math.max(need, ...rows.map((r) => r.minutes), SLIDE);
  // ± 는 30분 눈금에 맞춘다 — 2:33 에서 + 는 3:00, − 는 2:30
  const up = (m: number) => (Math.floor(m / STEP) + 1) * STEP;
  const down = (m: number) => Math.max(0, (Math.ceil(m / STEP) - 1) * STEP);

  return (
    <div className="space-y-3">
      {/* 예산 막대 — 날마다 한 칸, 진한 칸 = 직접 정한 날, 옅은 칸 = 자동 */}
      <div>
        <div className="relative flex h-8 w-full overflow-hidden rounded-lg bg-surface-3" role="img" aria-label={`총 ${hm(need)} 중 ${hm(assigned)} 배치`}>
          {rows.map((r) => {
            const w = (r.minutes / scale) * 100;
            if (w <= 0) return null;
            return (
              <div
                key={r.date}
                className={`num flex h-full min-w-0 items-center justify-center overflow-hidden border-r-2 border-surface text-[11px] font-semibold transition-[width] duration-200 ${
                  r.pinned ? "bg-study text-on-study" : "bg-study-soft text-study"
                }`}
                style={{ width: `${w}%` }}
                title={`${r.label} ${hm(r.minutes)}${r.pinned ? " (직접)" : " (자동)"}`}
              >
                {w > 11 && <span className="truncate px-1">{r.label.replace(/\(.\)/, "")}</span>}
              </div>
            );
          })}
          {state === "short" && gap > 0 && (
            <div
              className="num flex h-full items-center justify-center border-2 border-dashed border-warn text-[11px] font-semibold text-warn-text"
              style={{ width: `${(gap / scale) * 100}%` }}
            >
              {gap / scale > 0.12 && "남음"}
            </div>
          )}
          {state === "over" && (
            <span className="absolute top-0 h-full w-0.5 bg-danger" style={{ left: `${(need / scale) * 100}%` }} aria-hidden />
          )}
        </div>
        <p className={`num mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] ${state === "ok" ? "text-muted" : "font-semibold text-warn-text"}`}>
          {state === "ok" ? (
            <>
              <Check className="size-3.5 text-ok-text" aria-hidden />
              배치 {hm(assigned)} / 총 {hm(need)}
            </>
          ) : state === "short" ? (
            <>
              <TriangleAlert className="size-3.5" aria-hidden />
              {hm(synced ? al.unassignedMinutes : gap)}이 남았습니다 — 어느 날에 더하거나 고르게 나누세요
            </>
          ) : (
            <>
              <TriangleAlert className="size-3.5" aria-hidden />
              총 {hm(need)}보다 {hm(synced ? al.overMinutes : -gap)} 많습니다 — 분량이 다 찬 뒤의 시간은 비워 둡니다
            </>
          )}
        </p>
        {fixes.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {fixes.map((f) => (
              <button key={f.key} type="button" className="btn btn-sm" title={f.detail} onClick={() => onChange(f.apply)}>
                {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <ul className="divide-y divide-border rounded-xl border border-border bg-surface" aria-label="날짜별 공부 시간">
        {rows.map((r) => (
          <li key={r.date} className="px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="num text-[13px] font-semibold">{r.label}</span>
              {pm > 0 && <span className="num text-[12px] text-muted">{r.pages}쪽</span>}
              <span className="ml-auto">
                {r.pinned ? (
                  <button
                    type="button"
                    className="chip bg-study text-on-study"
                    title="자동으로 되돌리기 — 남은 시간을 다른 날과 나눠 가집니다"
                    aria-label={`${r.label} 직접 정한 시간 풀기`}
                    onClick={() => unpin(r.date)}
                  >
                    직접
                    <RotateCcw className="size-3" aria-hidden />
                  </button>
                ) : (
                  <span className="text-[12px] text-faint">자동</span>
                )}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={sliderMax}
                step={SLIDE}
                value={r.minutes}
                onChange={(e) => set(r, Number(e.target.value))}
                aria-label={`${r.label} 공부 시간`}
                aria-valuetext={hm(r.minutes)}
                className={`h-2 min-w-0 flex-1 cursor-pointer ${r.pinned ? "accent-[var(--study)]" : "accent-[var(--faint)]"}`}
              />
              <span className="flex flex-none items-center">
                <button
                  type="button"
                  className="btn btn-ghost btn-icon btn-sm"
                  aria-label={`${r.label} ${STEP}분 줄이기`}
                  disabled={r.minutes <= 0}
                  onClick={() => set(r, down(r.minutes))}
                >
                  <Minus aria-hidden />
                </button>
                <ClockField key={`${r.date}:${r.minutes}`} label={r.label} minutes={r.minutes} pinned={r.pinned} onCommit={(m) => set(r, m)} />
                <button
                  type="button"
                  className="btn btn-ghost btn-icon btn-sm"
                  aria-label={`${r.label} ${STEP}분 늘리기`}
                  disabled={r.minutes >= r.max}
                  onClick={() => set(r, up(r.minutes))}
                >
                  <Plus aria-hidden />
                </button>
              </span>
            </div>
          </li>
        ))}
        {preview.days
          .filter((d) => d.kind === "review")
          .map((d) => (
            <li key={d.date} className="flex flex-wrap items-center gap-2 bg-surface-2/60 px-3 py-2 text-[13px] text-muted">
              <span className="num font-semibold">{md(d.date)}</span>
              <span>마무리 복습{d.quiz ? ` + 문제 ${d.quiz}개` : ""}</span>
              <span className="num ml-auto">{hm(d.minutes)}</span>
              <span className="text-[12px] text-faint">· 분량에 따라</span>
            </li>
          ))}
      </ul>
    </div>
  );
}

/** 'h:mm' 칸 — 치는 동안은 글자 그대로, Enter·칸을 떠날 때 읽는다. 못 읽거나 비우면 원래 값으로 */
function ClockField({ label, minutes, pinned, onCommit }: { label: string; minutes: number; pinned: boolean; onCommit: (m: number) => void }) {
  const [draft, setDraft] = useState<string | null>(null);
  const commit = () => {
    if (draft === null) return;
    const m = parseClock(draft);
    setDraft(null);
    if (m !== null && m !== minutes) onCommit(m);
  };
  return (
    <input
      type="text"
      inputMode="decimal"
      className={`field field-sm num w-[58px] px-1 text-center ${pinned ? "font-semibold" : "text-muted"}`}
      aria-label={`${label} 공부 시간 (시:분)`}
      title="3 · 2.5 · 3:30 · 90분 처럼 넣을 수 있습니다"
      value={draft ?? clock(minutes)}
      onFocus={(e) => e.currentTarget.select()}
      onChange={(e) => setDraft(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
        if (e.key === "Escape") {
          setDraft(null);
          e.currentTarget.blur();
        }
      }}
    />
  );
}

function md(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return `${m}/${d}(${WD[new Date(y, m - 1, d).getDay()]})`;
}
